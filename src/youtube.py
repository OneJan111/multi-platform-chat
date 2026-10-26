"""YouTube Live integration: public reads via the Data API v3 (optional API key) or youtube_web."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src import gifts, youtube_web
from src.config import YOUTUBE_API_KEY, YOUTUBE_API_SERVICE, YOUTUBE_API_VERSION


def _api_key() -> str:
    # Ignore the placeholder shipped in env.template.
    key = (YOUTUBE_API_KEY or "").strip()
    return "" if not key or key.lower().startswith(("your_", "your-")) else key


def _read_service():
    """Data API service for public reads when YOUTUBE_API_KEY is set, else None (use youtube_web)."""
    return build(YOUTUBE_API_SERVICE, YOUTUBE_API_VERSION, developerKey=_api_key()) if _api_key() else None


# Chat IDs with this prefix are read through youtube_web (no login / API key) using the video ID.
WEB_CHAT_PREFIX = "web:"


def is_web_chat(chat_id: str) -> bool:
    return chat_id.startswith(WEB_CHAT_PREFIX)


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(value: str) -> str:
    """Return the 11-char video ID from a YouTube URL or bare ID, or "" if none."""
    value = value.strip()
    if _VIDEO_ID_RE.match(value):
        return value
    if "://" not in value and ("youtube.com" in value or "youtu.be" in value):
        value = "https://" + value
    parsed = urlparse(value)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    parts = [p for p in parsed.path.split("/") if p]
    candidate = ""
    if host == "youtu.be" and parts:
        candidate = parts[0]
    elif host.endswith("youtube.com"):
        query_v = parse_qs(parsed.query).get("v", [""])[0]
        if query_v:
            candidate = query_v
        elif len(parts) >= 2 and parts[0] in ("live", "embed", "shorts", "v", "video"):
            # youtube.com/live/ID, /embed/ID, studio.youtube.com/video/ID/livestreaming
            candidate = parts[1]
    return candidate if _VIDEO_ID_RE.match(candidate) else ""


def resolve_live_chat_id(value: str) -> tuple[str, str]:
    """
    Accept a live stream URL, video ID, or raw liveChatId.
    Returns (live_chat_id, error message).
    """
    value = value.strip()
    if not value:
        return "", ""
    video_id = extract_video_id(value)
    if not video_id:
        if "/" in value or "." in value:
            return "", "Couldn't find a video ID in that URL. Use the stream's watch/live URL."
        return value, ""  # assume it's already a liveChatId

    service = _read_service()
    if service:
        try:
            resp = service.videos().list(part="liveStreamingDetails,snippet", id=video_id).execute()
        except HttpError:
            resp = None  # invalid key, quota exceeded, etc. — fall back to the web reader
        if resp is not None:
            items = resp.get("items", [])
            if not items:
                return "", f"Video {video_id} not found (private, deleted, or wrong ID)."
            details = items[0].get("liveStreamingDetails")
            if not details:
                return "", "That video is not a live stream."
            chat_id = details.get("activeLiveChatId", "")
            if not chat_id:
                if details.get("actualEndTime"):
                    return "", "That stream has ended, so its live chat is closed."
                return "", "No active live chat — the stream isn't live yet, or chat is disabled."
            return chat_id, ""

    # No sign-in / API key (or the API failed): read the chat the way youtube.com does.
    status = youtube_web.get_video_status(video_id)
    if status and not status["is_stream"]:
        return "", "That video is not a live stream."
    if status and status["ended"]:
        return "", "That stream has ended, so its live chat is closed."
    reason = youtube_web.check_chat(video_id)
    if reason:
        return "", reason
    return WEB_CHAT_PREFIX + video_id, ""


def get_video_live_status(video_id: str) -> dict:
    """Public live status of any video/stream (works for viewers, not just the owner)."""
    if not video_id:
        return {}
    service = _read_service()
    if not service:
        return youtube_web.get_video_status(video_id)
    try:
        resp = (
            service.videos()
            .list(part="snippet,liveStreamingDetails", id=video_id)
            .execute()
        )
    except HttpError:
        return youtube_web.get_video_status(video_id)
    items = resp.get("items", [])
    if not items:
        return {}
    snippet = items[0].get("snippet", {})
    details = items[0].get("liveStreamingDetails", {})
    thumbs = snippet.get("thumbnails", {})
    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "channel_id": snippet.get("channelId", ""),
        # "live" | "upcoming" | "none" (ended streams and normal videos report "none")
        "broadcast": snippet.get("liveBroadcastContent", "none"),
        "is_stream": bool(details),
        "ended": bool(details.get("actualEndTime")),
        "viewers": int(details.get("concurrentViewers", 0) or 0),
        "actual_start": details.get("actualStartTime", ""),
        "scheduled_start": details.get("scheduledStartTime", ""),
        "thumbnail": (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
    }


# ── Live chat ──────────────────────────────────────────────────────────────────

def get_chat_messages(live_chat_id: str, page_token: str = "") -> tuple[list[dict], str, int]:
    """
    Fetch live chat messages.
    Returns (messages, nextPageToken, pollingIntervalMillis).
    """
    if is_web_chat(live_chat_id):
        return youtube_web.get_messages(live_chat_id[len(WEB_CHAT_PREFIX):], page_token)
    service = _read_service()
    if not service or not live_chat_id:
        return [], "", 5000
    try:
        kwargs: dict = {
            "liveChatId": live_chat_id,
            "part": "snippet,authorDetails",
            "maxResults": 200,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        resp = service.liveChatMessages().list(**kwargs).execute()
        next_token = resp.get("nextPageToken", "")
        polling_ms = resp.get("pollingIntervalMillis", 5000)
        messages = []
        for item in resp.get("items", []):
            snippet = item.get("snippet", {})
            author = item.get("authorDetails", {})
            msg_type = snippet.get("type", "textMessageEvent")
            text = snippet.get("displayMessage", "")
            extra = {}
            if msg_type == "superChatEvent":
                sc = snippet.get("superChatDetails", {})
                # amountDisplayString already includes the currency symbol (e.g. "$5.00", "¥500").
                text = f"[Super Chat {sc.get('amountDisplayString','')}] {sc.get('userComment','')}"
                gifts.set_value(extra, *gifts.parse_amount(sc.get("amountDisplayString", "")))
            elif msg_type == "superStickerEvent":
                gifts.set_value(extra, *gifts.parse_amount(
                    snippet.get("superStickerDetails", {}).get("amountDisplayString", "")))
            elif msg_type == "memberMilestoneChatEvent":
                mm = snippet.get("memberMilestoneChatDetails", {})
                text = f"[Member] {mm.get('userComment','')}"
            if msg_type == "membershipGiftingEvent":
                gd = snippet.get("membershipGiftingDetails", {})
                extra["gift_count"] = int(gd.get("giftMembershipsCount") or 1)
                text = f"[{text}]" if text else f"[Gifted {extra['gift_count']} memberships]"
            elif msg_type == "giftMembershipReceivedEvent":
                text = f"[Gift membership] {text}".strip()
                extra["free"] = True  # the gifter's purchase is the paid event
            messages.append(
                {
                    "id": item["id"],
                    "platform": "youtube",
                    "author": author.get("displayName", ""),
                    "author_id": author.get("channelId", ""),
                    "is_owner": author.get("isChatOwner", False),
                    "is_moderator": author.get("isChatModerator", False),
                    "is_verified": author.get("isVerified", False),
                    "membership": "Member" if author.get("isChatSponsor") else "",
                    "text": text,
                    "type": msg_type,
                    "timestamp": snippet.get("publishedAt", ""),
                    "avatar": author.get("profileImageUrl", ""),
                    **extra,
                }
            )
        return messages, next_token, polling_ms
    except HttpError:
        return [], "", 5000


def send_chat(live_chat_id: str, video_id: str, message: str) -> tuple[bool, str]:
    """Send via the imported browser-cookie login. Returns (ok, error)."""
    if not youtube_web.has_login():
        return False, "Not logged in to YouTube — import YouTube cookies in the 🍪 Cookies tab."
    if not video_id and is_web_chat(live_chat_id):
        video_id = live_chat_id[len(WEB_CHAT_PREFIX):]
    if not video_id:
        return False, "Cookie login needs the stream URL or video ID (not a raw live chat ID)."
    return youtube_web.send_message(video_id, message)
