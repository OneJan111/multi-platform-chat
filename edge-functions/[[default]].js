const CHAT_KEY = "chat_state";
const SETTINGS_KEY = "app_settings";
const TRANSCRIPTS_KEY = "transcript_state";
const MAX_CHAT_MESSAGES = 120;
const MAX_TRANSCRIPTS = 100;
const ALLOWED_LANGUAGES = new Set(["ja", "zh"]);

function jsonResponse(status, value) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function constantTimeEqual(left, right) {
  if (typeof left !== "string" || typeof right !== "string") return false;
  let difference = left.length ^ right.length;
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return difference === 0;
}

function hasBearer(request, secret) {
  if (typeof secret !== "string" || secret.length < 32 || /[\r\n]/.test(secret)) {
    return false;
  }
  const authorization = request.headers.get("Authorization") || "";
  return constantTimeEqual(authorization, "Bearer " + secret);
}

async function parseJSON(request) {
  try {
    const body = await request.json();
    return body && typeof body === "object" && !Array.isArray(body) ? body : null;
  } catch {
    return null;
  }
}

function requireKV(env) {
  const kv = env.CHAT_KV;
  if (!kv || typeof kv.get !== "function" || typeof kv.put !== "function") {
    throw new Error("EdgeOne KV binding CHAT_KV is unavailable");
  }
  return kv;
}

async function getJSON(kv, key, fallback) {
  const value = await kv.get(key, { type: "json" });
  return value && typeof value === "object" ? value : fallback;
}

function enabledByEnvironment(env) {
  return String(env.EDGEONE_TRANSCRIPTION_ENABLED || "false").toLowerCase() === "true";
}

async function getSettings(kv, env) {
  const saved = await getJSON(kv, SETTINGS_KEY, {});
  return {
    chatTarget: ALLOWED_LANGUAGES.has(saved.chatTarget) ? saved.chatTarget : "ja",
    audioLanguage: ALLOWED_LANGUAGES.has(saved.audioLanguage) ? saved.audioLanguage : "ja",
    transcriptionEnabled: enabledByEnvironment(env)
      && saved.transcriptionEnabled !== false,
  };
}

function hex(bytes) {
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sha256(value) {
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

async function hmac(keyBytes, value) {
  const key = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value)));
}

async function tencentRequest(service, action, version, region, payload, env) {
  const secretId = env.TENCENT_SECRET_ID;
  const secretKey = env.TENCENT_SECRET_KEY;
  if (!secretId || !secretKey) {
    throw new Error("Tencent Cloud credentials are not configured");
  }

  const host = `${service}.tencentcloudapi.com`;
  const contentType = "application/json; charset=utf-8";
  const body = JSON.stringify(payload);
  const timestamp = Math.floor(Date.now() / 1000);
  const date = new Date(timestamp * 1000).toISOString().slice(0, 10);
  const scope = `${date}/${service}/tc3_request`;
  const canonicalRequest = [
    "POST",
    "/",
    "",
    `content-type:${contentType}\nhost:${host}\n`,
    "content-type;host",
    await sha256(body),
  ].join("\n");
  const stringToSign = [
    "TC3-HMAC-SHA256",
    String(timestamp),
    scope,
    await sha256(canonicalRequest),
  ].join("\n");
  const secretDate = await hmac(new TextEncoder().encode(`TC3${secretKey}`), date);
  const secretService = await hmac(secretDate, service);
  const signingKey = await hmac(secretService, "tc3_request");
  const signature = hex(await hmac(signingKey, stringToSign));

  const response = await fetch(`https://${host}/`, {
    method: "POST",
    headers: {
      Authorization: `TC3-HMAC-SHA256 Credential=${secretId}/${scope}, SignedHeaders=content-type;host, Signature=${signature}`,
      "Content-Type": contentType,
      "X-TC-Action": action,
      "X-TC-Region": region || "ap-shanghai",
      "X-TC-Timestamp": String(timestamp),
      "X-TC-Version": version,
    },
    body,
  });
  const result = await response.json();
  if (!response.ok || result.Response?.Error) {
    const message = result.Response?.Error?.Message || `Tencent ${service} request failed`;
    throw new Error(message);
  }
  return result.Response || {};
}

async function translateText(text, target, env, kv) {
  const normalized = String(text || "").trim();
  if (!normalized || normalized.length > 2000) {
    throw new Error("Translation text must contain 1 to 2000 characters");
  }
  if (!ALLOWED_LANGUAGES.has(target)) {
    throw new Error("Translation target must be ja or zh");
  }

  const cacheKey = `translation_${await sha256(`${target}\n${normalized}`)}`;
  const cached = await kv.get(cacheKey);
  if (typeof cached === "string" && cached) return cached;

  const response = await tencentRequest(
    "tmt",
    "TextTranslate",
    "2018-03-21",
    env.TENCENT_REGION,
    {
      ProjectId: 0,
      Source: "auto",
      SourceText: normalized,
      Target: target,
    },
    env,
  );
  const translated = response.TargetText;
  if (typeof translated !== "string" || !translated) {
    throw new Error("Tencent TMT returned no translation");
  }
  await kv.put(cacheKey, translated);
  return translated;
}

function cleanMessage(message) {
  if (!message || typeof message !== "object") return null;
  const text = String(message.text || "").slice(0, 2000);
  if (!text.trim()) return null;
  return {
    id: String(message.id || "").slice(0, 160),
    platform: ["youtube", "bilibili", "missevan"].includes(message.platform)
      ? message.platform
      : "",
    author: String(message.author || "").slice(0, 120),
    text,
    timestamp: String(message.timestamp || message._simple_arrived || "").slice(0, 80),
    paid: Boolean(message.paid || message.is_paid || message.type === "gift"),
  };
}

async function stateResponse(request, env) {
  if (!hasBearer(request, env.APP_ACCESS_TOKEN)) {
    return jsonResponse(401, { error: "Unauthorized" });
  }
  const kv = requireKV(env);
  const url = new URL(request.url);
  const settings = await getSettings(kv, env);
  const chatState = await getJSON(kv, CHAT_KEY, {
    activeSource: "",
    live: {},
    updatedAt: "",
    messages: [],
  });
  const transcriptState = await getJSON(kv, TRANSCRIPTS_KEY, { items: [] });
  const chatTarget = ALLOWED_LANGUAGES.has(url.searchParams.get("target"))
    ? url.searchParams.get("target")
    : settings.chatTarget;
  const messages = Array.isArray(chatState.messages) ? chatState.messages.slice(-30) : [];
  const translated = [];
  for (let index = 0; index < messages.length; index += 5) {
    const batch = messages.slice(index, index + 5);
    translated.push(...await Promise.all(batch.map(async (message) => {
      try {
        return {
          ...message,
          translation: await translateText(message.text, chatTarget, env, kv),
        };
      } catch (error) {
        console.error("Chat translation failed", String(error));
        return { ...message, translation: "", translationError: true };
      }
    })));
  }

  return jsonResponse(200, {
    activeSource: chatState.activeSource || "",
    live: chatState.live || {},
    updatedAt: chatState.updatedAt || "",
    chatTarget,
    audioLanguage: settings.audioLanguage,
    transcriptionEnabled: settings.transcriptionEnabled,
    transcriptionEnabledByEnvironment: enabledByEnvironment(env),
    messages: translated,
    transcripts: Array.isArray(transcriptState.items)
      ? transcriptState.items.slice(-30).reverse()
      : [],
  });
}

async function updateSettings(request, env) {
  if (!hasBearer(request, env.APP_ACCESS_TOKEN)) {
    return jsonResponse(401, { error: "Unauthorized" });
  }
  const body = await parseJSON(request);
  if (!body) return jsonResponse(400, { error: "Request body must be a JSON object" });
  const current = await getSettings(requireKV(env), env);
  const chatTarget = body.chatTarget ?? current.chatTarget;
  const audioLanguage = body.audioLanguage ?? current.audioLanguage;
  if (!ALLOWED_LANGUAGES.has(chatTarget) || !ALLOWED_LANGUAGES.has(audioLanguage)) {
    return jsonResponse(400, { error: "Language must be ja or zh" });
  }
  const transcriptionEnabled = body.transcriptionEnabled ?? current.transcriptionEnabled;
  if (typeof transcriptionEnabled !== "boolean") {
    return jsonResponse(400, { error: "transcriptionEnabled must be boolean" });
  }

  const settings = {
    chatTarget,
    audioLanguage,
    transcriptionEnabled: enabledByEnvironment(env) && transcriptionEnabled,
  };
  await requireKV(env).put(SETTINGS_KEY, JSON.stringify(settings));
  return jsonResponse(200, {
    ...settings,
    transcriptionEnabledByEnvironment: enabledByEnvironment(env),
  });
}

async function collectorConfig(request, env) {
  if (!hasBearer(request, env.COLLECTOR_TOKEN)) {
    return jsonResponse(401, { error: "Unauthorized" });
  }
  const settings = await getSettings(requireKV(env), env);
  return jsonResponse(200, {
    ...settings,
    transcriptionEnabledByEnvironment: enabledByEnvironment(env),
  });
}

async function ingestChat(request, env) {
  if (!hasBearer(request, env.COLLECTOR_TOKEN)) {
    return jsonResponse(401, { error: "Unauthorized" });
  }
  const body = await parseJSON(request);
  if (!body) return jsonResponse(400, { error: "Request body must be a JSON object" });
  if (!Array.isArray(body.messages) || body.messages.length > 100) {
    return jsonResponse(400, { error: "messages must be an array of at most 100 items" });
  }

  const kv = requireKV(env);
  const state = await getJSON(kv, CHAT_KEY, { messages: [] });
  const existing = Array.isArray(state.messages) ? state.messages : [];
  const ids = new Set(existing.map((item) => `${item.platform}_${item.id}`).filter(Boolean));
  const incoming = body.messages.map(cleanMessage).filter(Boolean);
  let accepted = 0;
  for (const message of incoming) {
    const dedupeKey = `${message.platform}_${message.id}`;
    if (message.id && ids.has(dedupeKey)) continue;
    existing.push(message);
    accepted += 1;
    if (message.id) ids.add(dedupeKey);
  }
  const next = {
    activeSource: ["youtube", "bilibili", "missevan"].includes(body.activeSource)
      ? body.activeSource
      : "",
    live: body.live && typeof body.live === "object" ? body.live : {},
    updatedAt: new Date().toISOString(),
    messages: existing.slice(-MAX_CHAT_MESSAGES),
  };
  await kv.put(CHAT_KEY, JSON.stringify(next));
  return jsonResponse(200, { accepted, stored: next.messages.length });
}

async function saveTranscript(env, record) {
  const kv = requireKV(env);
  const current = await getJSON(kv, TRANSCRIPTS_KEY, { items: [] });
  const items = Array.isArray(current.items) ? current.items : [];
  if (items.some((item) => item.id === record.id)) return;

  let store = env.TRANSCRIPT_STORE;
  if (!store) {
    const { getStore } = await import("@edgeone/pages-blob");
    store = getStore("streaming-transcripts");
  }
  const blobKey = "transcripts/recent.json";
  const records = items.map(({ blobKey: _blobKey, ...item }) => item);
  const retained = [...records, record].slice(-MAX_TRANSCRIPTS);
  await store.setJSON(blobKey, retained);
  await kv.put(
    TRANSCRIPTS_KEY,
    JSON.stringify({ items: retained.map((item) => ({ ...item, blobKey })) }),
  );
}

async function transcribe(request, env) {
  if (!hasBearer(request, env.COLLECTOR_TOKEN)) {
    return jsonResponse(401, { error: "Unauthorized" });
  }
  const kv = requireKV(env);
  const settings = await getSettings(kv, env);
  if (!settings.transcriptionEnabled) {
    return jsonResponse(409, { error: "Transcription is disabled" });
  }

  const body = await parseJSON(request);
  if (!body) return jsonResponse(400, { error: "Request body must be a JSON object" });
  const sourceLanguage = body.sourceLanguage;
  if (!ALLOWED_LANGUAGES.has(sourceLanguage)) {
    return jsonResponse(400, { error: "sourceLanguage must be ja or zh" });
  }
  const original = String(body.original || "").trim();
  if (!original || original.length > 2000) {
    return jsonResponse(400, { error: "original must contain 1 to 2000 characters" });
  }
  const audioDuration = Number(body.audioDuration);
  if (!Number.isFinite(audioDuration) || audioDuration <= 0 || audioDuration > 60) {
    return jsonResponse(400, { error: "audioDuration must be between 0 and 60 seconds" });
  }

  const target = sourceLanguage === "ja" ? "zh" : "ja";
  const translated = await translateText(original, target, env, kv);
  const record = {
    id: crypto.randomUUID(),
    time: new Date().toISOString(),
    platform: ["youtube", "bilibili", "missevan"].includes(body.platform)
      ? body.platform
      : "",
    original,
    translated,
    sourceLanguage,
    targetLanguage: target,
    audioDuration,
  };
  await saveTranscript(env, record);
  return jsonResponse(200, record);
}

export async function onRequest({ request, env = {} }) {
  const url = new URL(request.url);
  try {
    if (request.method === "GET" && url.pathname === "/api/state") {
      return await stateResponse(request, env);
    }
    if (request.method === "GET" && url.pathname === "/api/collector/config") {
      return await collectorConfig(request, env);
    }
    if (request.method === "POST" && url.pathname === "/api/collector/ingest") {
      return await ingestChat(request, env);
    }
    if (request.method === "POST" && url.pathname === "/api/settings") {
      return await updateSettings(request, env);
    }
    if (request.method === "POST" && url.pathname === "/api/transcribe") {
      return await transcribe(request, env);
    }
  } catch (error) {
    const message = String(error);
    console.error("EdgeOne API request failed", message);
    if (message.includes("KV binding") || message.includes("credentials are not configured")) {
      return jsonResponse(503, { error: "A required backend service is not configured" });
    }
    return jsonResponse(502, { error: "Backend request failed" });
  }
  return jsonResponse(404, { error: "Not found" });
}
