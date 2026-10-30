import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const handlerSource = await readFile(
  new URL("../edge-functions/[[default]].js", import.meta.url),
  "utf8",
);
const { onRequest, onRequestGet } = await import(
  `data:text/javascript;base64,${Buffer.from(handlerSource).toString("base64")}`
);

const TOKEN = "t".repeat(32);
const env = {
  OVERLAY_ORIGIN: "https://origin.example.com",
  OVERLAY_PROXY_TOKEN: TOKEN,
};

test("forwards overlay routes, query parameters, and authorization", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl;
  let requestedHeaders;
  globalThis.fetch = async (url, options) => {
    requestedUrl = String(url);
    requestedHeaders = options.headers;
    return new Response("<html>overlay</html>", {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  };

  try {
    const response = await onRequestGet({
      request: new Request("https://edge.example.com/overlay?bilibili=123&n=5"),
      env,
    });
    assert.equal(response.status, 200);
    assert.equal(await response.text(), "<html>overlay</html>");
    assert.equal(requestedUrl, "https://origin.example.com/overlay?bilibili=123&n=5");
    assert.equal(requestedHeaders.get("Authorization"), `Bearer ${TOKEN}`);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    assert.equal(response.headers.get("Content-Type"), "text/html; charset=utf-8");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects paths outside the overlay API without contacting the origin", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    assert.fail("Unexpected origin request");
  };
  try {
    const response = await onRequestGet({
      request: new Request("https://edge.example.com/private"),
      env,
    });
    assert.equal(response.status, 404);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("requires a valid HTTPS origin and a strong proxy token", async () => {
  for (const invalidEnv of [
    { ...env, OVERLAY_ORIGIN: "http://origin.example.com" },
    { ...env, OVERLAY_PROXY_TOKEN: "short" },
  ]) {
    const response = await onRequestGet({
      request: new Request("https://edge.example.com/overlay"),
      env: invalidEnv,
    });
    assert.equal(response.status, 500);
  }
});

test("returns a generic gateway error if the origin cannot be reached", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("private origin detail");
  };
  try {
    const response = await onRequestGet({
      request: new Request("https://edge.example.com/overlay/data?site=youtube"),
      env,
    });
    assert.equal(response.status, 502);
    assert.deepEqual(await response.json(), {
      error: "Overlay origin is unavailable",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("allows only GET requests", async () => {
  const response = onRequest({
    request: new Request("https://edge.example.com/overlay", { method: "POST" }),
    env,
  });
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("Allow"), "GET");
});
