import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../edge-functions/[[default]].js", import.meta.url), "utf8");
const { onRequest } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

const APP_TOKEN = "app-token-".padEnd(40, "a");
const COLLECTOR_TOKEN = "collector-token-".padEnd(40, "b");

function createKV() {
  const entries = new Map();
  return {
    entries,
    async get(key, options) {
      const value = entries.get(key);
      if (value === undefined) return null;
      return options?.type === "json" ? JSON.parse(value) : value;
    },
    async put(key, value) {
      entries.set(key, String(value));
    },
  };
}

function createEnv(extra = {}) {
  return {
    CHAT_KV: createKV(),
    APP_ACCESS_TOKEN: APP_TOKEN,
    COLLECTOR_TOKEN,
    EDGEONE_TRANSCRIPTION_ENABLED: "true",
    TENCENT_SECRET_ID: "test-id",
    TENCENT_SECRET_KEY: "test-secret",
    TENCENT_REGION: "ap-shanghai",
    ...extra,
  };
}

function request(path, { method = "GET", token = APP_TOKEN, body } = {}) {
  return new Request(`https://edge.example.com${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
}

async function call(path, env, options = {}) {
  const response = await onRequest({ request: request(path, options), env });
  return { response, body: await response.json() };
}

test("collector ingestion is authenticated and state translates chat to the selected language", async () => {
  const env = createEnv();
  const originalFetch = globalThis.fetch;
  const actions = [];
  globalThis.fetch = async (_url, options) => {
    actions.push(options.headers["X-TC-Action"]);
    return Response.json({ Response: { TargetText: "こんにちは" } });
  };

  try {
    const unauthorized = await call("/api/collector/ingest", env, {
      method: "POST",
      token: APP_TOKEN,
      body: { messages: [] },
    });
    assert.equal(unauthorized.response.status, 401);

    const ingest = await onRequest({
      request: request("/api/collector/ingest", {
        method: "POST",
        token: COLLECTOR_TOKEN,
        body: {
          activeSource: "bilibili",
          live: { bilibili: true },
          messages: [{
            id: "m1",
            platform: "bilibili",
            author: "viewer",
            text: "你好",
          }],
        },
      }),
      env,
    });
    assert.equal(ingest.status, 200);

    const state = await call("/api/state?target=ja", env);
    assert.equal(state.response.status, 200);
    assert.equal(state.body.messages[0].translation, "こんにちは");
    assert.equal(state.body.activeSource, "bilibili");
    assert.deepEqual(actions, ["TextTranslate"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("collector message dedupe is platform-scoped and input size is bounded", async () => {
  const env = createEnv();
  for (const platform of ["youtube", "bilibili"]) {
    const response = await onRequest({
      request: request("/api/collector/ingest", {
        method: "POST",
        token: COLLECTOR_TOKEN,
        body: {
          messages: [{ id: "same-id", platform, text: `hello ${platform}` }],
        },
      }),
      env,
    });
    assert.equal(response.status, 200);
  }
  const state = await onRequest({
    request: request("/api/state?target=ja"),
    env: { ...env, TENCENT_SECRET_ID: "", TENCENT_SECRET_KEY: "" },
  });
  assert.equal(state.status, 200);

  const tooMany = await onRequest({
    request: request("/api/collector/ingest", {
      method: "POST",
      token: COLLECTOR_TOKEN,
      body: { messages: Array.from({ length: 101 }, () => ({ text: "hi" })) },
    }),
    env,
  });
  assert.equal(tooMany.status, 400);
});

test("settings toggle cannot override the environment transcription kill switch", async () => {
  const env = createEnv({ EDGEONE_TRANSCRIPTION_ENABLED: "false" });
  const update = await onRequest({
    request: request("/api/settings", {
      method: "POST",
      body: {
        chatTarget: "zh",
        audioLanguage: "ja",
        transcriptionEnabled: true,
      },
    }),
    env,
  });
  const settings = await update.json();
  assert.equal(update.status, 200);
  assert.equal(settings.transcriptionEnabled, false);

  const config = await onRequest({
    request: request("/api/collector/config", { token: COLLECTOR_TOKEN }),
    env,
  });
  assert.equal((await config.json()).transcriptionEnabled, false);
  const state = await call("/api/state", env);
  assert.equal(state.body.chatTarget, "zh");

  const transcription = await onRequest({
    request: request("/api/transcribe", {
      method: "POST",
      token: COLLECTOR_TOKEN,
      body: {
        original: "こんにちは",
        audioDuration: 8,
        sourceLanguage: "ja",
        platform: "bilibili",
      },
    }),
    env,
  });
  assert.equal(transcription.status, 409);
});

test("Japanese realtime ASR results are translated to Chinese and persisted", async () => {
  const env = createEnv({
    TRANSCRIPT_STORE: {
      saved: [],
      async setJSON(key, value) {
        this.saved.push({ key, value });
      },
    },
  });
  const originalFetch = globalThis.fetch;
  const actions = [];
  globalThis.fetch = async (_url, options) => {
    const action = options.headers["X-TC-Action"];
    actions.push(action);
    return Response.json({ Response: { TargetText: "早上好" } });
  };
  try {
    const response = await onRequest({
      request: request("/api/transcribe", {
        method: "POST",
        token: COLLECTOR_TOKEN,
        body: {
          original: "おはよう",
          audioDuration: 8,
          sourceLanguage: "ja",
          platform: "youtube",
        },
      }),
      env,
    });
    const result = await response.json();
    assert.equal(response.status, 200);
    assert.equal(result.original, "おはよう");
    assert.equal(result.translated, "早上好");
    assert.equal(result.targetLanguage, "zh");
    assert.deepEqual(actions, ["TextTranslate"]);
    assert.equal(env.TRANSCRIPT_STORE.saved.length, 1);
    assert.equal(env.TRANSCRIPT_STORE.saved[0].key, "transcripts/recent.json");
    assert.equal(env.TRANSCRIPT_STORE.saved[0].value[0].original, "おはよう");
    assert.equal(env.CHAT_KV.entries.has("transcript_state"), true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Chinese realtime ASR results are translated to Japanese", async () => {
  const env = createEnv({
    TRANSCRIPT_STORE: {
      async setJSON() {},
    },
  });
  const originalFetch = globalThis.fetch;
  let translationRequest;
  globalThis.fetch = async (_url, options) => {
    translationRequest = JSON.parse(options.body);
    return Response.json({ Response: { TargetText: "ありがとう" } });
  };
  try {
    const response = await onRequest({
      request: request("/api/transcribe", {
        method: "POST",
        token: COLLECTOR_TOKEN,
        body: {
          original: "谢谢",
          audioDuration: 8,
          sourceLanguage: "zh",
          platform: "bilibili",
        },
      }),
      env,
    });
    const result = await response.json();
    assert.equal(response.status, 200);
    assert.equal(result.translated, "ありがとう");
    assert.equal(result.targetLanguage, "ja");
    assert.equal(translationRequest.Source, "auto");
    assert.equal(translationRequest.Target, "ja");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects invalid recognition results and unauthenticated state reads", async () => {
  const env = createEnv();
  const unauthenticated = await onRequest({
    request: request("/api/state", { token: "" }),
    env,
  });
  assert.equal(unauthenticated.status, 401);

  const invalidResult = await onRequest({
    request: request("/api/transcribe", {
      method: "POST",
      token: COLLECTOR_TOKEN,
      body: {
        original: "",
        audioDuration: 8,
        sourceLanguage: "ja",
        platform: "bilibili",
      },
    }),
    env,
  });
  assert.equal(invalidResult.status, 400);
});
