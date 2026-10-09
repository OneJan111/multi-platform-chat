"""Local, read-only browser source for the live chat overlay."""
from __future__ import annotations

import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from src import emotes

PORT = 8502
MAX_MESSAGES = 50
# Streamlit re-imports edited modules, so module globals would forget the running
# server; keep the singleton on `sys`, which survives reloads.
_STATE = sys.__dict__.setdefault("_multi_platform_chat_overlay", {"lock": threading.Lock(), "server": None})


def is_superchat(msg: dict) -> bool:
    """Bilibili/MissEvan 'superchat', YouTube 'superChatEvent' / 'superStickerEvent'."""
    return "super" in str(msg.get("type", "")).lower() and bool(msg.get("text"))


def snapshot(messages: list[dict], translate_enabled: bool, target: str,
             get_translation: Callable[[str, str], str | None],
             custom_text: str = "", show_username: bool = True, count: int = 5,
             paid_count: int = 3, paid_messages: list[dict] | None = None) -> dict:
    """Only publish displayable fields, never raw platform events or credentials.

    `paid_messages` (gifts, Super Chats, memberships) is a separate list the dashboard never
    trims for chat volume, so busy regular chat can't push paid events off the overlay.
    """
    count = max(1, min(int(count), MAX_MESSAGES))
    paid_count = max(0, min(int(paid_count), MAX_MESSAGES))
    chat = [
        m for m in messages
        if m.get("type") in ("textMessageEvent", "danmaku") and m.get("text")
    ][-count:]
    if paid_messages is None:
        paid_messages = [m for m in messages if is_superchat(m)]
    paid = [m for m in paid_messages if m.get("text")][-paid_count:] if paid_count else []

    def item_for(msg: dict) -> dict:
        text = msg["text"]
        # Gift names are product names; translating them gives nonsense.
        translated = get_translation(text, target) if translate_enabled and msg.get("type") != "gift" else ""
        item = {
            "text": text,
            "translation": translated or "",
            "platform": msg.get("platform", ""),
        }
        if msg.get("type") == "gift":
            item["kind"] = "gift"
        if show_username:
            item["author"] = str(msg.get("author", ""))
        sticker = emotes.safe_image_url(msg.get("sticker_url"))
        if sticker:
            item["sticker"] = sticker
        inline = {
            code: safe for code, raw in (msg.get("emotes") or {}).items()
            if isinstance(code, str) and code in text and (safe := emotes.safe_image_url(raw))
        }
        if inline:
            item["emotes"] = inline
        return item

    return {
        "paid": [item_for(m) for m in paid],
        "messages": [item_for(m) for m in chat],
        "custom_text": custom_text,
    }


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin: 0; background: transparent; overflow: hidden; }
  body { font: 16px 'Segoe UI', sans-serif; color: white; }
  /* Paid events are pinned to the top and chat to the bottom, so neither can push the other. */
  #paid, #chat { position: fixed; left: 20px; width: min(420px, calc(100vw - 40px)); overflow: hidden; }
  #paid { top: 20px; max-height: calc(50vh - 30px); }
  #chat { bottom: 20px; max-height: calc(50vh - 30px); display: flex; flex-direction: column; justify-content: flex-end; }
  .message { margin: 4px 0; text-shadow: 1px 1px 3px #000; overflow-wrap: anywhere; white-space: pre-wrap; }
  .author { font-weight: bold; }
  .youtube { color: #ff6b6b; }
  .bilibili { color: #5bc8f5; }
  .missevan { color: #ffad74; }
  .translation { color: #9fd3ff; padding-left: 8px; }
  .emote { height: 1.6em; vertical-align: middle; }
  .sticker { height: 96px; vertical-align: middle; }
  #custom { color: #ffd700; font-weight: bold; white-space: pre-wrap; overflow-wrap: anywhere; }
  .paid-item { background: rgba(120, 0, 0, 0.75); border-left: 4px solid #ffd700; border-radius: 6px; padding: 4px 8px; }
  .paid-item.gift { background: rgba(80, 20, 110, 0.75); border-left-color: #ff8adf; }
</style>
</head>
<body>
<div id="paid"></div>
<div id="chat"><div id="messages"></div><div id="custom"></div></div>
<script>
function image(url, alt, cls) {
  const img = document.createElement("img");
  img.src = url;
  img.alt = img.title = alt;
  img.className = cls;
  img.referrerPolicy = "no-referrer";
  return img;
}
function appendText(row, msg) {
  if (msg.sticker) { row.append(image(msg.sticker, msg.text, "sticker")); return; }
  const codes = Object.keys(msg.emotes || {}).sort((a, b) => b.length - a.length);
  if (!codes.length) { row.append(document.createTextNode(msg.text)); return; }
  const pattern = new RegExp("(" + codes.map(c => c.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")).join("|") + ")");
  for (const part of msg.text.split(pattern)) {
    if (!part) continue;
    row.append(codes.includes(part) ? image(msg.emotes[part], part, "emote") : document.createTextNode(part));
  }
}
function renderList(id, messages, cls) {
  const list = document.getElementById(id);
  list.replaceChildren();
  for (const msg of messages || []) {
    const row = document.createElement("div");
    row.className = cls + (msg.kind === "gift" ? " gift" : "");
    if (msg.author) {
      const author = document.createElement("div");
      author.className = "author " + (["youtube", "bilibili", "missevan"].includes(msg.platform) ? msg.platform : "");
      author.textContent = msg.author;
      row.append(author);
    }
    const text = document.createElement("div");
    text.className = "text";
    appendText(text, msg);
    row.append(text);
    if (msg.translation) {
      const translated = document.createElement("div");
      translated.className = "translation";
      translated.textContent = msg.translation;
      row.append(translated);
    }
    list.append(row);
  }
}
async function refresh() {
  try {
    const response = await fetch("/overlay/data", {cache: "no-store"});
    if (!response.ok) throw new Error(`Overlay HTTP ${response.status}`);
    const data = await response.json();
    renderList("paid", data.paid, "message paid-item");
    renderList("messages", data.messages, "message");
    document.getElementById("custom").textContent = data.custom_text;
  } catch (error) {
    console.error("Could not refresh chat overlay", error);
  }
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>""".encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/overlay":
            body, content_type = _PAGE, "text/html; charset=utf-8"
        elif self.path == "/overlay/data":
            with self.server.snapshot_lock:
                body = json.dumps(self.server.data, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class OverlayServer(ThreadingHTTPServer):
    # Without exclusive binding, Windows lets a duplicate server share the port while
    # the stale one keeps answering OBS.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, port: int = PORT):
        super().__init__(("127.0.0.1", port), _Handler)
        self.snapshot_lock = threading.Lock()
        self.data: dict = {"messages": [], "custom_text": ""}

    def publish(self, data: dict) -> None:
        with self.snapshot_lock:
            self.data = data


def ensure_started() -> OverlayServer:
    """Keep one server alive across Streamlit reruns; propagate bind failures."""
    with _STATE["lock"]:
        if _STATE["server"] is None:
            server = OverlayServer()
            threading.Thread(target=server.serve_forever, name="chat-overlay", daemon=True).start()
            _STATE["server"] = server
        return _STATE["server"]
