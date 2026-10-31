"""Read YouTube live chat without signing in or an API key.

Uses the same internal endpoints as the youtube.com chat window (live_chat page +
youtubei get_live_chat). No quota, but these are unofficial and YouTube may change them.
Messages are returned in the same dict shape as the Data API reader in youtube.py.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from html import unescape
from urllib.parse import unquote, urlparse

import requests

from src import emotes, gifts, user_login
from src.config import (
    YOUTUBE_ACCOUNT_MENU_URL,
    YOUTUBE_ACCOUNTS_LIST_URL,
    YOUTUBE_CHAT_PAGE_URL,
    YOUTUBE_GET_LIVE_CHAT_URL,
    YOUTUBE_WEB_ORIGIN,
    YOUTUBE_SEND_CHAT_URL,
    YOUTUBE_WATCH_PAGE_URL,
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
_TIMEOUT = 10

_session = requests.Session()
_session.headers.update({"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"})
# Skips the EU cookie-consent interstitial.
_session.cookies.set("SOCS", "CAI", domain=".youtube.com")

_lock = threading.Lock()
_client_version: dict[str, str] = {}  # video_id -> innertube client version
_seen: dict[str, OrderedDict] = {}  # video_id -> recently returned message ids (dedupe)
_MAX_SEEN = 2000


class ChatUnavailable(Exception):
    """The video has no readable live chat (offline, ended, disabled, or not found)."""


def _initial_data(html: str, var: str) -> dict:
    m = re.search(r'(?:window\["%s"\]|var %s)\s*=\s*\{' % (var, var), html)
    if not m:
        return {}
    try:
        # raw_decode stops at the end of the object, whatever script follows it.
        obj, _ = json.JSONDecoder().raw_decode(html, m.end() - 1)
        return obj if isinstance(obj, dict) else {}
    except ValueError:
        return {}


def _runs_text(obj: dict) -> str:
    if not obj:
        return ""
    if "simpleText" in obj:
        return obj["simpleText"]
    out = []
    for run in obj.get("runs", []):
        if "text" in run:
            out.append(run["text"])
        elif "emoji" in run:
            emoji = run["emoji"]
            # Custom channel emotes use the :name: shortcut; standard emoji use the character.
            if emoji.get("isCustomEmoji"):
                out.append((emoji.get("shortcuts") or [""])[0])
            else:
                out.append(emoji.get("emojiId", ""))
    return "".join(out)


def _custom_emotes(obj: dict) -> dict[str, str]:
    """{":shortcut:": image URL} for the channel's custom emojis (member stamps) in a message."""
    found = {}
    for run in (obj or {}).get("runs", []):
        emoji = run.get("emoji") or {}
        if not emoji.get("isCustomEmoji"):
            continue
        code = (emoji.get("shortcuts") or [""])[0]
        thumbs = emoji.get("image", {}).get("thumbnails", [])
        url = emotes.safe_chat_image_url(thumbs[-1].get("url", "")) if thumbs else ""
        if code and url:
            found[code] = url
    return found


_emoji_lock = threading.Lock()
_channel_emojis: dict[str, OrderedDict] = {}  # video_id -> emojiId -> emoji entry (this channel's stamps)
_picker_fetched: set[str] = set()  # video_ids whose logged-in picker has been read
_MAX_EMOJIS = 500
_YT_CODE_RE = re.compile(r":_[^:\s]+:")


def _emoji_entry(emoji: dict) -> dict | None:
    emoji_id = emoji.get("emojiId", "")
    # Channel stamps have ids like "UCxxxx/yyyy"; standard emoji use the character itself.
    if not (emoji.get("isCustomEmoji") or "/" in emoji_id) or not emoji_id:
        return None
    shortcuts = [s for s in emoji.get("shortcuts") or [] if isinstance(s, str) and s]
    thumbs = emoji.get("image", {}).get("thumbnails", [])
    url = emotes.safe_chat_image_url(thumbs[-1].get("url", "")) if thumbs else ""
    if not shortcuts or not url:
        return None
    label = emoji.get("image", {}).get("accessibility", {}).get("accessibilityData", {}).get("label", "")
    return {"id": emoji_id, "code": shortcuts[0], "shortcuts": shortcuts, "name": label or shortcuts[0].strip(":_"),
            "url": url, "locked": bool(emoji["isLocked"]) if "isLocked" in emoji else None}


def _collect_emojis(node, found: dict) -> None:
    if isinstance(node, dict):
        entry = _emoji_entry(node) if "emojiId" in node else None
        if entry:
            found[entry["id"]] = entry
        for value in node.values():
            if isinstance(value, (dict, list)):
                _collect_emojis(value, found)
    elif isinstance(node, list):
        for value in node:
            _collect_emojis(value, found)


def _remember_emojis(video_id: str, node) -> None:
    found: dict = {}
    _collect_emojis(node, found)
    if not found:
        return
    with _emoji_lock:
        known = _channel_emojis.setdefault(video_id, OrderedDict())
        for emoji_id, entry in found.items():
            old = known.get(emoji_id)
            # Only the logged-in picker knows whether *you* can use a stamp; chat messages don't.
            if entry["locked"] is None:
                entry["locked"] = old["locked"] if old else None
            known[emoji_id] = entry
        while len(known) > _MAX_EMOJIS:
            known.popitem(last=False)


def channel_emojis(video_id: str, fetch: bool = False) -> list[dict]:
    """The stream channel's custom emojis (member stamps) seen so far.

    Chat messages reveal the stamps people use; with `fetch` and a login, the chat window's emoji
    picker adds the full set once per video and marks the ones this account can't use (`locked`).
    """
    if fetch and video_id and has_login() and video_id not in _picker_fetched:
        try:
            page = _auth_session(login_cookies()).get(
                YOUTUBE_CHAT_PAGE_URL, params={"is_popout": 1, "v": video_id}, timeout=_TIMEOUT).text
            _remember_emojis(video_id, _initial_data(page, "ytInitialData"))
        except requests.RequestException:
            pass
        finally:
            _picker_fetched.add(video_id)
    with _emoji_lock:
        return list(_channel_emojis.get(video_id, {}).values())


def message_segments(message: str, emojis: list[dict]) -> list[dict]:
    """Split a message into innertube text segments, turning known `:shortcut:` codes into emoji."""
    ids = {code: e["id"] for e in emojis for code in e.get("shortcuts") or [e["code"]]}
    if not ids:
        return [{"text": message}]
    pattern = re.compile("|".join(re.escape(code) for code in sorted(ids, key=len, reverse=True)))
    segments, pos = [], 0
    for m in pattern.finditer(message):
        if m.start() > pos:
            segments.append({"text": message[pos:m.start()]})
        segments.append({"emojiId": ids[m.group(0)]})
        pos = m.end()
    if pos < len(message):
        segments.append({"text": message[pos:]})
    return segments


def strip_emoji_codes(message: str, emojis: list[dict] = ()) -> str:
    """Remove YouTube-only stamp codes (e.g. for the same text sent to other sites)."""
    for code in sorted({c for e in emojis for c in e.get("shortcuts") or []}, key=len, reverse=True):
        message = message.replace(code, "")
    return re.sub(r"\s{2,}", " ", _YT_CODE_RE.sub("", message)).strip()


def _sticker_url(renderer: dict) -> str:
    thumbs = renderer.get("sticker", {}).get("thumbnails", [])
    return emotes.safe_chat_image_url(thumbs[-1].get("url", "")) if thumbs else ""


def _iso(usec: str) -> str:
    try:
        dt = datetime.fromtimestamp(int(usec) / 1_000_000, tz=timezone.utc)
    except (TypeError, ValueError):
        return ""
    return dt.isoformat().replace("+00:00", "Z")


def _badges(renderer: dict) -> set[str]:
    kinds = set()
    for badge in renderer.get("authorBadges", []):
        icon = badge.get("liveChatAuthorBadgeRenderer", {}).get("icon", {}).get("iconType", "")
        if icon:
            kinds.add(icon)
    return kinds


def _membership(renderer: dict) -> tuple[str, str]:
    """(label, icon URL) of the channel-membership badge, e.g. ("Member (6 months)", "https://yt3.ggpht.com/…")."""
    for badge in renderer.get("authorBadges", []):
        b = badge.get("liveChatAuthorBadgeRenderer", {})
        thumbs = b.get("customThumbnail", {}).get("thumbnails", [])
        if b.get("customThumbnail"):
            label = b.get("tooltip") or b.get("accessibility", {}).get("accessibilityData", {}).get("label", "") or "Member"
            return label, thumbs[-1].get("url", "") if thumbs else ""
    return "", ""


def _parse_action(action: dict) -> dict | None:
    item = action.get("addChatItemAction", {}).get("item", {})
    if not item:
        ticker = action.get("addLiveChatTickerItemAction", {}).get("item", {})
        if not ticker:
            return None
        ticker_kind, ticker_renderer = next(iter(ticker.items()))
        if ticker_kind != "liveChatTickerPaidStickerItemRenderer":
            return None
        sticker_renderer = (
            ticker_renderer.get("showItemEndpoint", {})
            .get("showLiveChatItemEndpoint", {})
            .get("renderer", {})
            .get("liveChatPaidStickerRenderer", {})
        )
        if not sticker_renderer:
            return None
        item = {"liveChatPaidStickerRenderer": {
            **sticker_renderer,
            "id": ticker_renderer.get("id", sticker_renderer.get("id", "")),
            "authorExternalChannelId": ticker_renderer.get(
                "authorExternalChannelId", sticker_renderer.get("authorExternalChannelId", "")
            ),
            "authorPhoto": ticker_renderer.get("authorPhoto", sticker_renderer.get("authorPhoto", {})),
        }}
    kind, r = next(iter(item.items()))
    text = _runs_text(r.get("message", {}))
    extra: dict = {}
    if kind == "giftMessageViewModel":
        msg_type = "gift"
        text = r.get("text", {}).get("content", "")
        gift_name = r.get("giftImageA11yLabel") or r.get("imageA11yLabel") or ""
        extra["gift_name"] = gift_name
        extra["gift_count"] = 1
        extra["sticker_caption"] = True
        jewel_amount = re.search(r"([\d,]+)\s+Jewels?\b", text, re.IGNORECASE)
        if jewel_amount:
            gifts.set_value(extra, "Jewels", int(jewel_amount.group(1).replace(",", "")))
        gift_sources = r.get("giftImage", {}).get("sources", [])
        extra["sticker_url"] = (
            emotes.safe_chat_image_url(gift_sources[-1].get("url", ""))
            if gift_sources else ""
        )
        avatar_sources = (
            r.get("authorAvatar", {}).get("avatarViewModel", {})
            .get("image", {}).get("sources", [])
        )
        r = {
            **r,
            "authorName": {"simpleText": r.get("authorName", {}).get("content", "")},
            "authorPhoto": {"thumbnails": avatar_sources},
        }
        text = text or f"Sent {gift_name or 'a gift'}"
    elif kind == "liveChatTextMessageRenderer":
        msg_type = "textMessageEvent"
    elif kind == "liveChatPaidMessageRenderer":
        msg_type = "superChatEvent"
        amount = _runs_text(r.get("purchaseAmountText", {}))
        text = f"[Super Chat {amount}] {text}".rstrip()
        gifts.set_value(extra, *gifts.parse_amount(amount))
    elif kind == "liveChatPaidStickerRenderer":
        msg_type = "superStickerEvent"
        amount = _runs_text(r.get("purchaseAmountText", {}))
        text = f"[Super Sticker {amount}]"
        gifts.set_value(extra, *gifts.parse_amount(amount))
    elif kind == "liveChatMembershipItemRenderer":
        msg_type = "newSponsorEvent"
        header = _runs_text(r.get("headerSubtext", {})) or _runs_text(r.get("headerPrimaryText", {}))
        text = f"[Member] {header} {text}".strip()
    elif kind == "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer":
        # "Gifted 5 memberships": the author details live in the header renderer.
        msg_type = "membershipGiftingEvent"
        header = r.get("header", {}).get("liveChatSponsorshipsHeaderRenderer", {})
        primary = _runs_text(header.get("primaryText", {}))
        text = f"[{primary}]"
        count = re.search(r"\d[\d,]*", primary)
        extra["gift_count"] = int(count.group().replace(",", "")) if count else 1
        r = {**header, "id": r.get("id", ""), "authorExternalChannelId": r.get("authorExternalChannelId", ""),
             "timestampUsec": r.get("timestampUsec", "")}
    elif kind == "liveChatSponsorshipsGiftRedemptionAnnouncementRenderer":
        # "X received a gift membership by Y": the gifter is the bold run of the message.
        msg_type = "giftMembershipReceivedEvent"
        runs = r.get("message", {}).get("runs", [])
        bold = [run.get("text", "") for run in runs if run.get("bold")]
        extra["gifted_by"] = bold[-1].strip() if bold else ""
        text = f"[Gift membership] {text}".strip()
        extra["free"] = True  # the recipient paid nothing; the gifter's purchase is announced instead
    else:
        return None  # placeholders, system banners, polls
    badges = _badges(r)
    member_label, member_icon = _membership(r)
    photos = r.get("authorPhoto", {}).get("thumbnails", [])
    return {
        "id": r.get("id", ""),
        "platform": "youtube",
        "author": _runs_text(r.get("authorName", {})),
        "author_id": r.get("authorExternalChannelId", ""),
        "is_owner": "OWNER" in badges,
        "is_moderator": "MODERATOR" in badges,
        "is_verified": "VERIFIED" in badges,
        "membership": member_label,
        "membership_icon": member_icon,
        "text": text,
        "emotes": _custom_emotes(r.get("message", {})),
        "sticker_url": _sticker_url(r) if msg_type == "superStickerEvent" else "",
        "sticker_caption": msg_type == "superStickerEvent",
        "type": msg_type,
        "timestamp": _iso(r.get("timestampUsec", "")),
        "avatar": photos[-1]["url"] if photos else "",
        **extra,
    }


def _next_continuation(continuations: list) -> tuple[str, int]:
    for c in continuations:
        for data in c.values():
            if isinstance(data, dict) and data.get("continuation"):
                return data["continuation"], int(data.get("timeoutMs", 5000))
    return "", 5000


def _open(video_id: str) -> str:
    """Load the chat window page and return the continuation for the full "Live chat" view."""
    resp = _session.get(YOUTUBE_CHAT_PAGE_URL, params={"is_popout": 1, "v": video_id}, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise ChatUnavailable(f"YouTube returned HTTP {resp.status_code} for the chat page.")
    ver = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"', resp.text)
    data = _initial_data(resp.text, "ytInitialData")
    contents = data.get("contents", {})
    renderer = contents.get("liveChatRenderer")
    if not renderer or not ver:
        reason = _runs_text(contents.get("messageRenderer", {}).get("text", {}))
        raise ChatUnavailable(reason or "No live chat — the stream isn't live, has ended, or chat is disabled.")
    with _lock:
        _client_version[video_id] = ver.group(1)
    # The header menu offers "Top chat" (filtered) and "Live chat" (everything); use the last one.
    menu = (
        renderer.get("header", {}).get("liveChatHeaderRenderer", {}).get("viewSelector", {})
        .get("sortFilterSubMenuRenderer", {}).get("subMenuItems", [])
    )
    for entry in reversed(menu):
        cont = entry.get("continuation", {}).get("reloadContinuationData", {}).get("continuation")
        if cont:
            return cont
    cont, _ = _next_continuation(renderer.get("continuations", []))
    if not cont:
        raise ChatUnavailable("Could not find the live chat stream for this video.")
    return cont


def check_chat(video_id: str) -> str:
    """Return "" if the video's live chat can be read without login, else a reason."""
    try:
        _open(video_id)
        return ""
    except ChatUnavailable as exc:
        return str(exc)
    except requests.RequestException as exc:
        return f"Couldn't reach YouTube: {exc.__class__.__name__}"


def get_messages(video_id: str, continuation: str = "",
                 seen: OrderedDict | None = None) -> tuple[list[dict], str, int]:
    """
    Fetch new chat messages. Pass "" as continuation to start (returns recent history too).
    Returns (messages, next continuation, suggested poll interval in ms).
    `seen` lets an independent reader (e.g. the standalone overlay) dedupe on its own, so it
    doesn't hide messages from a dashboard reading the same stream.
    """
    try:
        if not continuation or video_id not in _client_version:
            continuation = _open(video_id)
        body = {
            "context": {"client": {"clientName": "WEB", "clientVersion": _client_version[video_id]}},
            "continuation": continuation,
        }
        resp = _session.post(YOUTUBE_GET_LIVE_CHAT_URL, params={"prettyPrint": "false"}, json=body, timeout=_TIMEOUT)
        data = resp.json()
    except ChatUnavailable:
        return [], "", 10000
    except (requests.RequestException, ValueError):
        return [], continuation, 5000  # transient; retry the same continuation

    chat = data.get("continuationContents", {}).get("liveChatContinuation")
    if not chat:
        return [], "", 10000  # chat closed or continuation expired; reopen next time
    next_cont, timeout_ms = _next_continuation(chat.get("continuations", []))
    _remember_emojis(video_id, chat.get("actions", []))

    messages = []
    with _lock:
        if seen is None:
            seen = _seen.setdefault(video_id, OrderedDict())
        for action in chat.get("actions", []):
            msg = _parse_action(action)
            if not msg or not msg["id"] or msg["id"] in seen:
                continue
            seen[msg["id"]] = None
            messages.append(msg)
        while len(seen) > _MAX_SEEN:
            seen.popitem(last=False)
    return messages, next_cont, timeout_ms


def get_video_status(video_id: str) -> dict:
    """Live status from the public watch page, in the same shape as youtube.get_video_live_status."""
    try:
        resp = _session.get(YOUTUBE_WATCH_PAGE_URL, params={"v": video_id}, timeout=_TIMEOUT)
    except requests.RequestException:
        return {}
    player = _initial_data(resp.text, "ytInitialPlayerResponse")
    details = player.get("videoDetails", {})
    if not details:
        return {}
    live = player.get("microformat", {}).get("playerMicroformatRenderer", {}).get("liveBroadcastDetails", {})
    is_stream = bool(details.get("isLiveContent") or live)
    if details.get("isLive") or live.get("isLiveNow"):
        broadcast = "live"
    elif details.get("isUpcoming"):
        broadcast = "upcoming"
    else:
        broadcast = "none"
    viewers = 0
    if broadcast == "live":
        m = re.search(r'"originalViewCount":"(\d+)"', resp.text)
        viewers = int(m.group(1)) if m else 0
    scheduled = ""
    upcoming = (
        player.get("playabilityStatus", {}).get("liveStreamability", {})
        .get("liveStreamabilityRenderer", {}).get("offlineSlate", {})
        .get("liveStreamOfflineSlateRenderer", {}).get("scheduledStartTime")
    )
    if upcoming:
        scheduled = _iso(str(int(upcoming) * 1_000_000))
    thumbs = details.get("thumbnail", {}).get("thumbnails", [])
    return {
        "video_id": video_id,
        "title": details.get("title", ""),
        "channel": details.get("author", ""),
        "channel_id": details.get("channelId", ""),
        "broadcast": broadcast,
        "is_stream": is_stream,
        "ended": bool(live.get("endTimestamp")),
        "viewers": viewers,
        "actual_start": live.get("startTimestamp", ""),
        "scheduled_start": scheduled,
        "thumbnail": thumbs[min(1, len(thumbs) - 1)]["url"] if thumbs else "",
    }


# ── Channel watcher (auto-join the channel's next live stream) ──────────────────

_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")
_HANDLE_RE = re.compile(r"^@[\w.\-·]{3,30}$")


def channel_url(value: str) -> str:
    """Normalise a channel link / @handle / UC… ID to https://www.youtube.com/<channel>, or "" if not a channel."""
    value = value.strip().rstrip("/")
    if _HANDLE_RE.match(value):
        return f"{YOUTUBE_WEB_ORIGIN}/{value}"
    if _CHANNEL_ID_RE.match(value):
        return f"{YOUTUBE_WEB_ORIGIN}/channel/{value}"
    if "://" not in value and "youtube.com" in value:
        value = "https://" + value
    parsed = urlparse(value)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    if host != "youtube.com":
        return ""
    parts = [unquote(p) for p in parsed.path.split("/") if p]
    if parts and parts[0].startswith("@"):
        return f"{YOUTUBE_WEB_ORIGIN}/{parts[0]}"
    if len(parts) >= 2 and parts[0] in ("channel", "c", "user"):
        return f"{YOUTUBE_WEB_ORIGIN}/{parts[0]}/{parts[1]}"
    return ""


def find_live_video(channel: str) -> dict:
    """
    Find the live stream or nearest scheduled stream via the public /live page.
    Returns {"video_id", "live", "upcoming", "title", "channel", "error"}; video_id is "" when offline.
    """
    result = {"video_id": "", "live": False, "upcoming": False, "title": "", "channel": "", "error": ""}
    try:
        resp = _session.get(channel + "/live", timeout=_TIMEOUT)
    except requests.RequestException as exc:
        result["error"] = f"Couldn't reach YouTube: {exc}"
        return result
    if resp.status_code == 404:
        result["error"] = "Channel not found."
        return result
    html = resp.text
    name = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    result["channel"] = unescape(name.group(1)) if name else ""
    # When the channel is live (or has a scheduled stream), /live serves that stream's watch page.
    canonical = re.search(
        rf'<link rel="canonical" href="{re.escape(YOUTUBE_WEB_ORIGIN)}/watch\?v=([\w-]{{11}})"', html)
    if not canonical:
        return result
    player = _initial_data(html, "ytInitialPlayerResponse")
    details = player.get("videoDetails", {})
    result["video_id"] = canonical.group(1)
    result["title"] = details.get("title", "")
    result["channel"] = details.get("author", "") or result["channel"]
    thumbs = details.get("thumbnail", {}).get("thumbnails", [])
    result["thumbnail"] = thumbs[min(1, len(thumbs) - 1)]["url"] if thumbs else ""
    result["live"] = bool(details.get("isLive"))
    result["upcoming"] = bool(details.get("isUpcoming"))
    scheduled_start = (
        player.get("playabilityStatus", {}).get("liveStreamability", {})
        .get("liveStreamabilityRenderer", {}).get("offlineSlate", {})
        .get("liveStreamOfflineSlateRenderer", {}).get("scheduledStartTime")
    )
    if scheduled_start:
        try:
            result["scheduled_start"] = _iso(str(int(scheduled_start) * 1_000_000))
        except (TypeError, ValueError):
            result["scheduled_start"] = ""
    return result


# ── Cookie login (send chat as the signed-in browser user) ──────────────────────
# youtube.com authenticates its own requests with the login cookies plus a
# SAPISIDHASH header (SHA-1 of "timestamp SAPISID origin"); this does the same.

_FALLBACK_CLIENT_VERSION = "2.20241001.00.00"


def parse_cookie_string(raw: str) -> dict[str, str]:
    cookies = {}
    for part in (raw or "").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            cookies[name.strip()] = value.strip()
    return cookies


def login_cookies() -> dict[str, str]:
    """The current user's YouTube cookies (per browser session, see user_login)."""
    return user_login.get("youtube")


def has_login(cookies: dict[str, str] | None = None) -> bool:
    c = login_cookies() if cookies is None else cookies
    return bool(c.get("SAPISID") or c.get("__Secure-3PAPISID"))


def save_login(cookies: dict[str, str]) -> None:
    """Use these cookies for the current user only."""
    user_login.set_site("youtube", cookies)


def _auth_session(cookies: dict[str, str]) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"})
    s.cookies.set("SOCS", "CAI", domain=".youtube.com")
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=".youtube.com")
    return s


def _auth_headers(cookies: dict[str, str]) -> dict[str, str]:
    ts = str(int(time.time()))

    def h(scheme: str, secret: str) -> str:
        return f"{scheme} {ts}_{hashlib.sha1(f'{ts} {secret} {YOUTUBE_WEB_ORIGIN}'.encode()).hexdigest()}"

    parts = []
    if cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID"):
        parts.append(h("SAPISIDHASH", cookies.get("SAPISID") or cookies["__Secure-3PAPISID"]))
    if cookies.get("__Secure-1PAPISID"):
        parts.append(h("SAPISID1PHASH", cookies["__Secure-1PAPISID"]))
    if cookies.get("__Secure-3PAPISID"):
        parts.append(h("SAPISID3PHASH", cookies["__Secure-3PAPISID"]))
    return {
        "Authorization": " ".join(parts),
        "Origin": YOUTUBE_WEB_ORIGIN,
        "X-Origin": YOUTUBE_WEB_ORIGIN,
        "X-Goog-AuthUser": "0",
        "Content-Type": "application/json",
        # Act as a secondary channel (brand account) of the same Google login; empty = the main channel.
        **({"X-Goog-PageId": page_id} if (page_id := selected_page_id()) else {}),
    }


def selected_page_id() -> str:
    return user_login.youtube_page_id()


def select_channel(page_id: str) -> None:
    """Choose which channel of the current user's Google login sends chat ("" = the main channel)."""
    user_login.set_youtube_page_id((page_id or "").strip())


def _find_account_items(node) -> list[dict]:
    if isinstance(node, dict):
        if "accountItem" in node:
            return [node["accountItem"]]
        return [i for v in node.values() for i in _find_account_items(v)]
    if isinstance(node, list):
        return [i for v in node for i in _find_account_items(v)]
    return []


def _account_display_name(node) -> str:
    if isinstance(node, dict):
        for key in ("accountName", "channelHandle"):
            value = node.get(key)
            if isinstance(value, dict):
                text = value.get("simpleText")
                if isinstance(text, str) and text.strip():
                    return text.strip()
                runs = value.get("runs")
                if isinstance(runs, list):
                    text = "".join(
                        run.get("text", "")
                        for run in runs
                        if isinstance(run, dict) and isinstance(run.get("text"), str)
                    )
                    if text.strip():
                        return text.strip()
        for value in node.values():
            name = _account_display_name(value)
            if name:
                return name
    elif isinstance(node, list):
        for value in node:
            name = _account_display_name(value)
            if name:
                return name
    return ""


def list_channels(cookies: dict[str, str] | None = None) -> dict:
    """Channels the cookie login can post as: {"channels": [{"name", "handle", "page_id", "selected"}]} (+ "error")."""
    cookies = login_cookies() if cookies is None else cookies
    if not (cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID")):
        return {"channels": []}
    try:
        s = _auth_session(cookies)
        headers = _auth_headers(cookies)
        headers.pop("X-Goog-PageId", None)  # list from the main account so every channel shows up
        body = {
            "context": {"client": {"clientName": "WEB", "clientVersion": _FALLBACK_CLIENT_VERSION, "hl": "en"}},
            "accountReadMask": {"returnOwner": True, "returnBrandAccounts": True, "returnPersonaAccounts": True},
        }
        resp = s.post(YOUTUBE_ACCOUNTS_LIST_URL, params={"prettyPrint": "false"}, json=body, headers=headers, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return {"channels": [], "error": f"HTTP {resp.status_code}"}
        channels, seen = [], set()
        for item in _find_account_items(resp.json()):
            tokens = item.get("serviceEndpoint", {}).get("selectActiveIdentityEndpoint", {}).get("supportedTokens", [])
            page_id = next((t["pageIdToken"].get("pageId", "") for t in tokens if "pageIdToken" in t), "")
            has_channel = next((t["accountStateToken"].get("hasChannel", True) for t in tokens if "accountStateToken" in t), True)
            if page_id in seen or not has_channel:
                continue
            seen.add(page_id)
            channels.append({
                "name": item.get("accountName", {}).get("simpleText", ""),
                "handle": item.get("channelHandle", {}).get("simpleText", "")
                          or item.get("accountByline", {}).get("simpleText", ""),
                "page_id": page_id,
                "selected": bool(item.get("isSelected")),
            })
        return {"channels": channels}
    except (requests.RequestException, ValueError) as exc:
        return {"channels": [], "error": str(exc)}


def verify_login(cookies: dict[str, str] | None = None) -> dict:
    """Who the cookies belong to: {"is_login", "name"} (+ "error" on failure)."""
    cookies = login_cookies() if cookies is None else cookies
    if not (cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID")):
        return {"is_login": False, "name": ""}
    try:
        s = _auth_session(cookies)
        body = {"context": {"client": {"clientName": "WEB", "clientVersion": _FALLBACK_CLIENT_VERSION, "hl": "en"}}}
        resp = s.post(
            YOUTUBE_ACCOUNT_MENU_URL,
            params={"prettyPrint": "false"},
            json=body,
            headers=_auth_headers(cookies),
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return {"is_login": False, "name": ""}
        try:
            name = _account_display_name(resp.json())
        except ValueError:
            name = ""
        if not name:
            m = (
                re.search(r'"accountName"\s*:\s*\{\s*"simpleText"\s*:\s*"((?:[^"\\]|\\.)*)"', resp.text)
                or re.search(
                    r'"channelHandle"\s*:\s*\{\s*"simpleText"\s*:\s*"((?:[^"\\]|\\.)*)"',
                    resp.text,
                )
            )
            name = json.loads(f'"{m.group(1)}"') if m else ""
        return {"is_login": bool(name), "name": name}
    except (requests.RequestException, ValueError) as exc:
        return {"is_login": False, "name": "", "error": str(exc)}


def send_message(video_id: str, message: str) -> tuple[bool, str]:
    """Post a chat message as the cookie-logged-in user. Returns (ok, error message)."""
    cookies = login_cookies()
    if not has_login(cookies):
        return False, "Not logged in to YouTube — import cookies in the 🍪 Cookies tab."
    try:
        s = _auth_session(cookies)
        page = s.get(YOUTUBE_CHAT_PAGE_URL, params={"is_popout": 1, "v": video_id}, timeout=_TIMEOUT).text
        if '"LOGGED_IN":true' not in page:
            return False, "YouTube says these cookies are signed out — re-import them in the 🍪 Cookies tab."
        _remember_emojis(video_id, _initial_data(page, "ytInitialData"))
        _picker_fetched.add(video_id)
        params = re.search(r'"sendLiveChatMessageEndpoint":\{"params":"([^"]+)"', page)
        if not params:
            data = _initial_data(page, "ytInitialData")
            contents = data.get("contents", {})
            panel = contents.get("liveChatRenderer", {}).get("actionPanel", {})
            reason = _runs_text(contents.get("messageRenderer", {}).get("text", {})) or _runs_text(
                panel.get("liveChatRestrictedParticipationRenderer", {}).get("message", {})
            ) or _runs_text(panel.get("liveChatMessageInputRenderer", {}).get("inputField", {}))
            return False, reason or "You can't chat in this stream (chat closed, members-only, or restricted)."
        ver = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"', page)
        body = {
            "context": {"client": {"clientName": "WEB", "clientVersion": ver.group(1) if ver else _FALLBACK_CLIENT_VERSION}},
            "params": params.group(1),
            "richMessage": {"textSegments": message_segments(message, channel_emojis(video_id))},
        }
        resp = s.post(YOUTUBE_SEND_CHAT_URL, params={"prettyPrint": "false"}, json=body, headers=_auth_headers(cookies), timeout=_TIMEOUT)
        data = resp.json()
        if resp.status_code == 200 and "error" not in data:
            # Blocked sends (slow mode, too long, ...) come back as a system message instead of the chat item.
            for action in data.get("actions", []):
                item = action.get("addChatItemAction", {}).get("item", {})
                if "liveChatViewerEngagementMessageRenderer" in item or "liveChatModeChangeMessageRenderer" in item:
                    r = next(iter(item.values()))
                    return False, _runs_text(r.get("message", {})) or "YouTube rejected the message."
            return True, ""
        return False, data.get("error", {}).get("message") or f"HTTP {resp.status_code}"
    except (requests.RequestException, ValueError) as exc:
        return False, str(exc)
