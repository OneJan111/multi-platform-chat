"""Read-only browser source for the live chat overlay (local by default; see OVERLAY_HOST)."""
from __future__ import annotations

import html
import json
import re
import socket
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

from src import chat_avatars, emotes, overlay_feeds, reading
from src.config import OVERLAY_HOST, OVERLAY_PORT

PORT = OVERLAY_PORT
MAX_MESSAGES = 50
DEFAULT_CHANNEL = "main"
MAX_CHANNELS = 50
# A standalone URL mirrors an open dashboard reading the same rooms; the dashboard republishes
# every few seconds, so a snapshot older than this means the dashboard was closed.
MIRROR_TTL = 20
_EMPTY = {"messages": [], "paid": [], "custom_text": ""}
_CHANNEL_RE = re.compile(r"[^A-Za-z0-9_-]")
SITES = ("youtube", "bilibili", "missevan")
SITE_ALIASES = {
    "youtube": "youtube", "yt": "youtube",
    "bilibili": "bilibili", "bili": "bilibili",
    "missevan": "missevan", "me": "missevan", "maoer": "missevan",
}
# Streamlit re-imports edited modules, so module globals would forget the running
# server; keep the singleton on `sys`, which survives reloads.
_STATE = sys.__dict__.setdefault("_multi_platform_chat_overlay", {"lock": threading.Lock(), "server": None})
_STATE.setdefault("history_sources", {})


def register_history_source(
    key: "overlay_feeds.FeedKey", get_snapshot: Callable[[], dict],
) -> None:
    """Share a server-lifetime history with overlays, without requiring an open dashboard."""
    with _STATE["lock"]:
        _STATE["history_sources"][key] = get_snapshot


def _history_snapshot(key: "overlay_feeds.FeedKey") -> dict | None:
    with _STATE["lock"]:
        sources = _STATE["history_sources"]
        provider = sources.get(key)
        if provider is None:
            provider = next((
                callback for source, callback in sources.items()
                if all(not wanted or wanted == configured for wanted, configured in zip(key, source))
            ), None)
    return provider() if provider is not None else None


def clean_channel(name: str) -> str:
    """Overlay channel name: letters, digits, '-' and '_' only (max 40); empty means the default."""
    return _CHANNEL_RE.sub("", name or "")[:40] or DEFAULT_CHANNEL


def is_superchat(msg: dict) -> bool:
    """Bilibili/MissEvan 'superchat', YouTube 'superChatEvent' / 'superStickerEvent'."""
    return "super" in str(msg.get("type", "")).lower() and bool(msg.get("text"))


def order_key(msg: dict) -> int:
    """When a message arrived (ns), to merge Super Chats / gifts with chat in time order.

    Prefers the local arrival stamp; falls back to the platform timestamp (epoch seconds or ISO 8601)."""
    arrived = msg.get("_arrived", msg.get("_simple_arrived"))
    if isinstance(arrived, int):
        return arrived
    ts = str(msg.get("timestamp") or "").strip()
    if ts.isdigit():
        n = int(ts)
        return n * 1_000_000 if n > 10**11 else n * 1_000_000_000  # epoch ms or s
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1_000_000_000)
    except ValueError:
        return 0


def _text_parts(text: str, codes) -> list[str]:
    """`text` split around emote codes (longest first), the same way the overlay page splits it."""
    codes = sorted((c for c in codes if isinstance(c, str) and c and c in text), key=len, reverse=True)
    if not codes:
        return [text] if text else []
    return [p for p in re.split("(" + "|".join(map(re.escape, codes)) + ")", text) if p]


def _reading_mode_for(lang: str, mode: str) -> str:
    """A translation's language is known: furigana for Japanese, pinyin for Chinese."""
    if mode == "off":
        return "off"
    return "hiragana" if lang.startswith("ja") else "pinyin" if lang.startswith("zh") else mode


def parse_reading(value: str) -> str:
    """URL ruby= value -> a reading.OVERLAY_MODES entry ("furigana" is accepted for "hiragana")."""
    value = (value or "").strip().lower()
    value = {"furigana": "hiragana", "1": "auto", "on": "auto", "true": "auto", "yes": "auto"}.get(value, value)
    return value if value in reading.OVERLAY_MODES else "off"


def snapshot(messages: list[dict], translate_enabled: bool, target: str,
             get_translation: Callable[[str, str], str | None],
             custom_text: str = "", show_username: bool = True, count: int = 5,
             paid_count: int = 3, paid_messages: list[dict] | None = None,
             reading_mode: str = "off") -> dict:
    """Only publish displayable fields, never raw platform events or credentials.

    `paid_messages` (gifts, Super Chats, memberships) is a separate list the dashboard never
    trims for chat volume, so busy regular chat can't push paid events off the overlay.
    `reading_mode` (a reading.OVERLAY_MODES entry) adds pinyin / furigana for the message text
    and translations as `ruby` / `translation_ruby` ([characters, reading] pairs).
    """
    from src import bilibili

    count = max(0, min(int(count), MAX_MESSAGES))
    paid_count = max(0, min(int(paid_count), MAX_MESSAGES))
    chat = _last_per_site([
        m for m in messages
        if m.get("type") in ("textMessageEvent", "danmaku") and m.get("text")
    ], count) if count else []
    if paid_messages is None:
        paid_messages = [m for m in messages if is_superchat(m)]
    # Up to `count` paid events too, so a single-chat link (n= without sc=) can be all gifts.
    paid = _last_per_site([m for m in paid_messages if m.get("text")],
                          max(paid_count, count)) if paid_count else []

    def item_for(msg: dict) -> dict:
        text = msg["text"]
        # Gift names are product names; translating them gives nonsense.
        translated = get_translation(text, target) if translate_enabled and msg.get("type") != "gift" else ""
        item = {
            "text": text,
            "translation": translated or "",
            "platform": msg.get("platform", ""),
            "at": order_key(msg),
        }
        if msg.get("type") == "gift":
            item["kind"] = "gift"
        if show_username:
            item["author"] = str(msg.get("author", ""))
        avatar = chat_avatars.message_avatar_url(
            msg, bilibili.get_user_avatar, emotes.safe_image_url, emotes.safe_badge_url
        )
        if avatar:
            item["avatar"] = avatar
        sticker = emotes.safe_chat_image_url(msg.get("sticker_url"))
        if sticker:
            item["sticker"] = sticker
            if msg.get("sticker_caption"):
                item["caption"] = True
        inline = {
            code: safe for code, raw in (msg.get("emotes") or {}).items()
            if isinstance(code, str) and code in text and (safe := emotes.safe_chat_image_url(raw))
        }
        if inline:
            item["emotes"] = inline
        if reading_mode != "off":
            # Keyed by the text pieces between emote codes, so codes like [妙啊] stay whole.
            parts = [text] if sticker else _text_parts(text, inline)
            ruby = {p: [list(s) for s in segs] for p in parts
                    if p not in inline and (segs := reading.segments(p, reading_mode))}
            if ruby:
                item["ruby"] = ruby
            if translated:
                segs = reading.segments(translated, _reading_mode_for(target, reading_mode))
                if segs:
                    item["translation_ruby"] = [list(s) for s in segs]
        return item

    return {
        "paid": [item_for(m) for m in paid],
        "messages": [item_for(m) for m in chat],
        "custom_text": custom_text,
        "count": count,
        "paid_count": paid_count,
    }


def _last_per_site(messages: list[dict], n: int) -> list[dict]:
    """The last `n` messages of each site, in their original order.

    Kept per site so an overlay showing only one site (?site=…) still gets `n` lines.
    """
    kept: dict[str, int] = {}
    out = []
    for msg in reversed(messages):
        site = msg.get("platform", "")
        if kept.get(site, 0) < n:
            kept[site] = kept.get(site, 0) + 1
            out.append(msg)
    out.reverse()
    return out


def parse_sites(values: list[str]) -> set[str]:
    """`?site=youtube,bili&site=me` -> {"youtube", "bilibili", "missevan"}; empty = every site."""
    sites = set()
    for value in values:
        for part in value.lower().split(","):
            if (site := SITE_ALIASES.get(part.strip())):
                sites.add(site)
    return sites


def view(data: dict, sites: set[str], count: int | None = None, paid_count: int | None = None,
         single: bool = False) -> dict:
    """What one overlay URL shows: only `sites` (all when empty), trimmed to the configured counts.
    `count` / `paid_count` (the URL's n= / sc=) can lower them further; 0 turns that section off, so
    one OBS screen can show only Super Chats and another only chat. With both on, Super Chats / gifts
    and chat are shown together in one list, in the order they arrived (paid rows keep their highlight).
    `single` (n= without sc=): one chat of the last `count` messages, Super Chats and gifts included."""
    def pick(items: list[dict], n: int) -> list[dict]:
        if sites:
            items = [m for m in items if m.get("platform") in sites]
        return items[-n:] if n else []

    count = data.get("count", MAX_MESSAGES) if count is None else min(count, data.get("count", MAX_MESSAGES))
    if single and count:
        # Paid events are still hidden when the dashboard set them to 0.
        paid = pick(data.get("paid", []), MAX_MESSAGES) if data.get("paid_count", MAX_MESSAGES) else []
        merged = [{**m, "paid": True} for m in paid] + pick(data.get("messages", []), MAX_MESSAGES)
        merged.sort(key=lambda m: m.get("at") or 0)
        return {"paid": [], "messages": merged[-count:], "custom_text": data.get("custom_text", ""),
                "layout": "mixed"}
    paid_count = (data.get("paid_count", MAX_MESSAGES) if paid_count is None
                  else min(paid_count, data.get("paid_count", MAX_MESSAGES)))
    paid = pick(data.get("paid", []), paid_count)
    messages = pick(data.get("messages", []), count)
    if count and paid_count:
        # Copies: `data` is a shared snapshot served to every overlay URL.
        merged = [{**m, "paid": True} for m in paid] + messages
        merged.sort(key=lambda m: m.get("at") or 0)  # stable: equal times keep paid-before-chat
        return {"paid": [], "messages": merged, "custom_text": data.get("custom_text", ""), "layout": "mixed"}
    return {
        "paid": paid,
        "messages": messages,
        "custom_text": data.get("custom_text", ""),
        "layout": "only-chat" if not paid_count else "only-paid" if not count else "",
    }


_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?$")


def _int_param(query: dict, name: str, default: int) -> int:
    try:
        return int((query.get(name) or [default])[0])
    except (TypeError, ValueError):
        return default


def feed_snapshot(key: "overlay_feeds.FeedKey", query: dict) -> dict:
    """Snapshot of a standalone feed (?youtube=…&bilibili=…&missevan=…), shaped by URL options:
    n (chat lines, default 5), sc (paid events, default 3), names=0 (hide usernames),
    tr=<lang> (add translations), text=<custom message>, ruby=auto|pinyin|furigana (reading aid)."""
    feed = overlay_feeds.get(key)
    if feed is None:
        return dict(_EMPTY, custom_text="Overlay server is busy — too many different overlays open.")
    chat, paid = feed.messages()
    target = (query.get("tr") or query.get("translate") or [""])[0].strip()
    if not _LANG_RE.match(target):
        target = ""
    get_translation = lambda *_: ""
    if target:
        from src import translate
        translate.prefetch([m["text"] for m in chat[-MAX_MESSAGES:] + paid[-MAX_MESSAGES:]
                            if m.get("type") != "gift"], target)
        get_translation = translate.get_translation
    return snapshot(
        chat, bool(target), target, get_translation,
        custom_text=(query.get("text") or [""])[0][:300],
        show_username=(query.get("names") or ["1"])[0].lower() not in ("0", "false", "no", "off"),
        count=_int_param(query, "n", 5),
        paid_count=_int_param(query, "sc", 3),
        paid_messages=paid,
        reading_mode=parse_reading((query.get("ruby") or [""])[0]),
    )


_PAGE_CSS = """
  #paid, #chat { position: fixed; left: 20px; right: 20px; overflow: hidden;
                 font: 16px 'Segoe UI', sans-serif; color: white; z-index: 1000; }
  #paid { top: 20px; max-height: calc(50vh - 30px); }
  #chat { bottom: 20px; max-height: calc(50vh - 30px); display: flex; flex-direction: column; justify-content: flex-end; }
  .message { margin: 4px 0; text-shadow: 1px 1px 3px #000; overflow-wrap: anywhere; white-space: pre-wrap; }
  .author { font-weight: bold; }
  .message-row { display: flex; align-items: flex-start; gap: 8px; }
  .message-content { flex: 1; min-width: 0; }
  .avatar { display: block; flex: 0 0 32px; width: 32px; height: 32px; border-radius: 50%;
            object-fit: cover; background: rgba(128,128,128,.25); text-align: center; line-height: 32px; }
  .youtube { color: #ff6b6b; }
  .bilibili { color: #5bc8f5; }
  .missevan { color: #ffad74; }
  .translation { color: #9fd3ff; padding-left: 8px; }
  .emote { height: 1.6em; vertical-align: middle; }
  .sticker { height: 96px; vertical-align: middle; }
  #custom { color: #ffd700; font-weight: bold; white-space: pre-wrap; overflow-wrap: anywhere; }
  .paid-item { background: rgba(120, 0, 0, 0.75); border-left: 4px solid #ffd700; border-radius: 6px; padding: 4px 8px; }
  .paid-item.gift { background: rgba(80, 20, 110, 0.75); border-left-color: #ff8adf; }
  .message rt { font-size: 0.6em; color: #ffe08a; }
  .only-paid #paid, .only-chat #chat, .mixed #chat { max-height: calc(100vh - 40px); }
  .only-chat #paid, .mixed #paid { display: none; }
"""


def _html_image(url: str, alt: str, cls: str) -> str:
    alt = html.escape(alt, quote=True)
    return (f'<img src="{html.escape(url, quote=True)}" alt="{alt}" title="{alt}" class="{cls}" '
            f'referrerpolicy="no-referrer">')


def _html_ruby(segs) -> str:
    return "".join(
        f"<ruby>{html.escape(str(base))}<rt>{html.escape(str(rd))}</rt></ruby>" if rd else html.escape(str(base))
        for base, rd in segs
    )


def _html_plain(part: str, msg: dict) -> str:
    segs = (msg.get("ruby") or {}).get(part)
    return _html_ruby(segs) if segs else html.escape(part)


def _html_text(msg: dict) -> str:
    text = str(msg.get("text", ""))
    sticker = emotes.safe_chat_image_url(msg.get("sticker"))
    if sticker:
        caption = f"{_html_plain(text, msg)}<br>" if msg.get("caption") else ""
        return caption + _html_image(sticker, text, "sticker")
    out = []
    for part in _text_parts(text, msg.get("emotes") or {}):
        url = emotes.safe_chat_image_url(msg["emotes"].get(part)) if part in (msg.get("emotes") or {}) else ""
        out.append(_html_image(url, part, "emote") if url else _html_plain(part, msg))
    return "".join(out)


def _html_list(messages: list[dict], cls: str) -> str:
    rows = []
    for msg in messages or []:
        row_cls = cls + (" paid-item" if msg.get("paid") else "") + (" gift" if msg.get("kind") == "gift" else "")
        parts = []
        if msg.get("author"):
            site = msg.get("platform") if msg.get("platform") in SITES else ""
            parts.append(f'<div class="author {site}">{html.escape(str(msg["author"]))}</div>')
        parts.append(f'<div class="text">{_html_text(msg)}</div>')
        if msg.get("translation"):
            body = (_html_ruby(msg["translation_ruby"]) if msg.get("translation_ruby")
                    else html.escape(str(msg["translation"])))
            parts.append(f'<div class="translation">{body}</div>')
        avatar_url = emotes.safe_chat_image_url(msg.get("avatar"))
        avatar = (
            chat_avatars.avatar_html(msg, avatar_url, "avatar")
            if avatar_url or msg.get("author") else ""
        )
        rows.append(
            f'<div class="{row_cls}"><div class="message-row">{avatar}'
            f'<div class="message-content">{"".join(parts)}</div></div></div>'
        )
    return "".join(rows)


def render_html(data: dict) -> str:
    """The overlay body for `overlay_data()` output, as escaped HTML (for pages that can't run scripts)."""
    return (
        f'<div class="{html.escape(str(data.get("layout") or ""))}">'
        f'<div id="paid">{_html_list(data.get("paid"), "message paid-item")}</div>'
        f'<div id="chat"><div id="messages">{_html_list(data.get("messages"), "message")}</div>'
        f'<div id="custom">{html.escape(str(data.get("custom_text") or ""))}</div></div></div>'
    )


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin: 0; background: transparent; overflow: hidden; }
  body { font: 16px 'Segoe UI', sans-serif; color: white; }
  /* Paid events are pinned to the top and chat to the bottom, so neither can push the other. */
  #paid, #chat { position: fixed; left: 20px; right: 20px; overflow: hidden; }
  #paid { top: 20px; max-height: calc(50vh - 30px); }
  #chat { bottom: 20px; max-height: calc(50vh - 30px); display: flex; flex-direction: column; justify-content: flex-end; }
  .message { margin: 4px 0; text-shadow: 1px 1px 3px #000; overflow-wrap: anywhere; white-space: pre-wrap; }
  .author { font-weight: bold; }
  .message-row { display: flex; align-items: flex-start; gap: 8px; }
  .message-content { flex: 1; min-width: 0; }
  .avatar { display: block; flex: 0 0 32px; width: 32px; height: 32px; border-radius: 50%;
            object-fit: cover; background: rgba(128,128,128,.25); text-align: center; line-height: 32px; }
  .youtube { color: #ff6b6b; }
  .bilibili { color: #5bc8f5; }
  .missevan { color: #ffad74; }
  .translation { color: #9fd3ff; padding-left: 8px; }
  .emote { height: 1.6em; vertical-align: middle; }
  .sticker { height: 96px; vertical-align: middle; }
  #custom { color: #ffd700; font-weight: bold; white-space: pre-wrap; overflow-wrap: anywhere; }
  .paid-item { background: rgba(120, 0, 0, 0.75); border-left: 4px solid #ffd700; border-radius: 6px; padding: 4px 8px; }
  .paid-item.gift { background: rgba(80, 20, 110, 0.75); border-left-color: #ff8adf; }
  .message rt { font-size: 0.6em; color: #ffe08a; }
  /* n=0 / sc=0: one section only (e.g. separate OBS scenes for Super Chats and chat) gets the full height. */
  .only-paid #paid, .only-chat #chat { max-height: calc(100vh - 40px); }
  .only-chat #paid { display: none; }
  /* Both on: Super Chats, gifts and chat share one list in arrival order, using the full height. */
  .mixed #chat { max-height: calc(100vh - 40px); }
  .mixed #paid { display: none; }
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
function rubyText(row, segs) {
  for (const [base, reading] of segs) {
    if (!reading) { row.append(document.createTextNode(base)); continue; }
    const ruby = document.createElement("ruby");
    const rt = document.createElement("rt");
    rt.textContent = reading;
    ruby.append(document.createTextNode(base), rt);
    row.append(ruby);
  }
}
function plainText(row, part, msg) {
  const segs = msg.ruby && Object.prototype.hasOwnProperty.call(msg.ruby, part) ? msg.ruby[part] : null;
  if (segs) rubyText(row, segs); else row.append(document.createTextNode(part));
}
function appendText(row, msg) {
  if (msg.sticker) {
    if (msg.caption) { plainText(row, msg.text, msg); row.append(document.createElement("br")); }
    row.append(image(msg.sticker, msg.text, "sticker"));
    return;
  }
  const codes = Object.keys(msg.emotes || {}).sort((a, b) => b.length - a.length);
  if (!codes.length) { plainText(row, msg.text, msg); return; }
  const pattern = new RegExp("(" + codes.map(c => c.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")).join("|") + ")");
  for (const part of msg.text.split(pattern)) {
    if (!part) continue;
    if (codes.includes(part)) row.append(image(msg.emotes[part], part, "emote")); else plainText(row, part, msg);
  }
}
function renderList(id, messages, cls) {
  const list = document.getElementById(id);
  list.replaceChildren();
  for (const msg of messages || []) {
    const row = document.createElement("div");
    row.className = cls + (msg.paid ? " paid-item" : "") + (msg.kind === "gift" ? " gift" : "");
    const body = document.createElement("div");
    body.className = "message-row";
    let avatarUrl = "";
    if (msg.avatar) {
      try {
        const url = new URL(msg.avatar);
        const hosts = ["hdslb.com", "ggpht.com", "googleusercontent.com", "maoercdn.com", "ytimg.com"];
        if (url.protocol === "https:" && hosts.some(h => url.hostname === h || url.hostname.endsWith("." + h))) {
          avatarUrl = url.href;
        }
      } catch (error) {
        console.error("Invalid overlay avatar URL", error);
      }
    }
    if (avatarUrl) {
      body.append(image(avatarUrl, msg.author || "", "avatar"));
    } else if (msg.author) {
      const initial = document.createElement("span");
      initial.className = "avatar";
      initial.title = msg.author;
      initial.textContent = Array.from(msg.author)[0].toUpperCase();
      body.append(initial);
    }
    const content = document.createElement("div");
    content.className = "message-content";
    if (msg.author) {
      const author = document.createElement("div");
      author.className = "author " + (["youtube", "bilibili", "missevan"].includes(msg.platform) ? msg.platform : "");
      author.textContent = msg.author;
      content.append(author);
    }
    const text = document.createElement("div");
    text.className = "text";
    appendText(text, msg);
    content.append(text);
    if (msg.translation) {
      const translated = document.createElement("div");
      translated.className = "translation";
      if (msg.translation_ruby) rubyText(translated, msg.translation_ruby); else translated.textContent = msg.translation;
      content.append(translated);
    }
    body.append(content);
    row.append(body);
    list.append(row);
  }
}
let lastBody = null;
async function refresh() {
  try {
    const response = await fetch("/overlay/data" + location.search, {cache: "no-store"});
    if (!response.ok) throw new Error(`Overlay HTTP ${response.status}`);
    const body = await response.text();
    // Unchanged: keep the current rows, so images aren't recreated and animated emotes don't restart.
    if (body === lastBody) return;
    const data = JSON.parse(body);
    document.body.className = data.layout || "";
    renderList("paid", data.paid, "message paid-item");
    renderList("messages", data.messages, "message");
    document.getElementById("custom").textContent = data.custom_text;
    lastBody = body;
  } catch (error) {
    console.error("Could not refresh chat overlay", error);
  }
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>""".encode("utf-8")


def overlay_data(query: dict, server: "OverlayServer | None" = None) -> dict:
    """What an overlay URL shows. `query` is parse_qs-style ({name: [values]})."""
    sites = parse_sites(query.get("site", []))
    key = overlay_feeds.parse_key(query)
    if key:
        data = _history_snapshot(key)
        from_history = data is not None
        if data is not None:
            requested_sites = {site for site, value in key._asdict().items() if value}
            sites = sites & requested_sites if sites else requested_sites
            data = {
                **data,
                "messages": [m for m in data.get("messages", []) if m.get("platform") in requested_sites],
                "paid": [m for m in data.get("paid", []) if m.get("platform") in requested_sites],
            }
        else:
            data = server.mirror(key) if server is not None else None
        if data is None:
            data = feed_snapshot(key, query)
        elif not from_history:
            # Keep the feed warm so the overlay continues seamlessly if the dashboard closes.
            feed = overlay_feeds.get(key)
            if feed is not None:
                feed.last_used = time.time()
            if not sites:
                sites = {site for site, value in key._asdict().items() if value}
    elif server is not None:
        channel = clean_channel(query.get("ch", [""])[0])
        with server.snapshot_lock:
            data = server.channels.get(channel, _EMPTY)
    else:
        data = _EMPTY
    url_count = _int_param(query, "n", -1) if query.get("n") else None
    url_paid = _int_param(query, "sc", -1) if query.get("sc") else None
    return view(data, sites,
                None if url_count is None or url_count < 0 else url_count,
                None if url_paid is None or url_paid < 0 else url_paid,
                single=url_count is not None and url_count >= 0 and not query.get("sc"))


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/overlay":
            body, content_type = _PAGE, "text/html; charset=utf-8"
        elif url.path == "/overlay/data":
            data = overlay_data(parse_qs(url.query), self.server)
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
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

    def __init__(self, port: int = OVERLAY_PORT, host: str = "127.0.0.1"):
        super().__init__((host, port), _Handler)
        self.snapshot_lock = threading.Lock()
        # One snapshot per overlay channel, so several dashboards can each drive their own overlay.
        self.channels: dict[str, dict] = {}
        # Dashboard snapshots by the rooms they read, for standalone URLs: FeedKey -> (time, data).
        self.mirrors: dict = {}

    @property
    def data(self) -> dict:
        with self.snapshot_lock:
            return self.channels.get(DEFAULT_CHANNEL, _EMPTY)

    def publish(self, data: dict, channel: str = DEFAULT_CHANNEL,
                source: "overlay_feeds.FeedKey | None" = None) -> None:
        """`source` = the rooms the dashboard reads; standalone URLs for those rooms then show `data`."""
        channel = clean_channel(channel)
        with self.snapshot_lock:
            if channel not in self.channels and len(self.channels) >= MAX_CHANNELS:
                self.channels.pop(next(iter(self.channels)))
            self.channels[channel] = data
            if source:
                now = time.time()
                self.mirrors = {k: v for k, v in self.mirrors.items() if now - v[0] < MIRROR_TTL}
                self.mirrors[source] = (now, data)

    def mirror(self, key: "overlay_feeds.FeedKey") -> dict | None:
        """The live dashboard snapshot for these rooms, or None if no dashboard is reading them."""
        with self.snapshot_lock:
            entry = self.mirrors.get(key)
        if entry and time.time() - entry[0] < MIRROR_TTL:
            return entry[1]
        return None


def ensure_started() -> OverlayServer:
    """Keep one server alive across Streamlit reruns; propagate bind failures."""
    with _STATE["lock"]:
        old = _STATE["server"]
        if old is not None and isinstance(old, ThreadingHTTPServer) and (
            type(old) is not OverlayServer or old.server_address[0] != OVERLAY_HOST
        ):
            # Started by an older copy of this module (Streamlit re-imports edited modules, but the running
            # server keeps answering with the code it was started with) or another OVERLAY_HOST: replace it.
            old.shutdown()
            old.server_close()
            _STATE["server"] = None
        if _STATE["server"] is None:
            server = OverlayServer(OVERLAY_PORT, OVERLAY_HOST)
            threading.Thread(target=server.serve_forever, name="chat-overlay", daemon=True).start()
            _STATE["server"] = server
        return _STATE["server"]


def main() -> None:
    """Run only the overlay (no dashboard): python -m src.overlay_server"""
    server = OverlayServer(OVERLAY_PORT, OVERLAY_HOST)
    print(f"Chat overlay on http://{OVERLAY_HOST}:{OVERLAY_PORT}/overlay"
          "?youtube=@channel&bilibili=ROOM&missevan=ROOM  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        overlay_feeds.stop_all()
        server.server_close()


if __name__ == "__main__":
    main()
