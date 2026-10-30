const OVERLAY_PATHS = new Set(["/overlay", "/overlay/data"]);

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function getOrigin(value) {
  if (!value) return null;

  let origin;
  try {
    origin = new URL(value);
  } catch {
    return null;
  }

  const isLocalHttp = origin.protocol === "http:"
    && ["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname);
  if (
    (origin.protocol !== "https:" && !isLocalHttp)
    || origin.username
    || origin.password
    || origin.pathname !== "/"
    || origin.search
    || origin.hash
  ) {
    return null;
  }

  return origin;
}

export async function onRequestGet(context) {
  const requestUrl = new URL(context.request.url);
  if (!OVERLAY_PATHS.has(requestUrl.pathname)) {
    return jsonResponse(404, { error: "Not found" });
  }

  const env = context.env || {};
  const origin = getOrigin(env.OVERLAY_ORIGIN);
  const token = env.OVERLAY_PROXY_TOKEN;
  if (!origin || typeof token !== "string" || token.length < 32 || /[\r\n]/.test(token)) {
    return jsonResponse(500, { error: "Overlay proxy is not configured" });
  }

  const target = new URL(requestUrl.pathname + requestUrl.search, origin);
  const headers = new Headers();
  const accept = context.request.headers.get("Accept");
  if (accept) headers.set("Accept", accept);
  headers.set("Authorization", `Bearer ${token}`);

  try {
    const upstream = await fetch(target, {
      method: "GET",
      headers,
      redirect: "error",
    });
    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    const contentType = upstream.headers.get("Content-Type");
    if (contentType) responseHeaders.set("Content-Type", contentType);

    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("EdgeOne overlay origin request failed", {
      path: requestUrl.pathname,
      message: String(error),
    });
    return jsonResponse(502, { error: "Overlay origin is unavailable" });
  }
}

export function onRequest(context) {
  if (context.request.method !== "GET") {
    return new Response(null, {
      status: 405,
      headers: {
        Allow: "GET",
        "Cache-Control": "no-store",
      },
    });
  }
  return onRequestGet(context);
}
