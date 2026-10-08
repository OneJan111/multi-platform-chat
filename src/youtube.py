"""YouTube Live integration using YouTube Data API v3 with OAuth2."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse

# Google may return scopes in a different order/form than requested; don't treat that as an error.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src import youtube_web
from src.config import (
    TOKEN_FILE,
    YOUTUBE_API_KEY,
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REDIRECT_URI,
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CLIENT_CONFIG = {
    "web": {
        "client_id": YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "redirect_uris": [YOUTUBE_REDIRECT_URI],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


def _get_credentials() -> Optional[Credentials]:
    creds: Optional[Credentials] = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
        except Exception:
            creds = None

    return creds


def _save_credentials(creds: Credentials) -> None:
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


# Google redirects back into a *new* Streamlit session, so per-session state is lost.
# Keep pending flows at module level (shared by all sessions in this server process),
# keyed by the OAuth `state` parameter: state -> (PKCE code_verifier, created_at).
_PENDING_FLOWS: dict[str, tuple[str, float]] = {}
_PENDING_TTL_SECONDS = 600


def _new_flow(**kwargs) -> Flow:
    flow = Flow.from_client_config(CLIENT_CONFIG, SCOPES, **kwargs)
    flow.redirect_uri = YOUTUBE_REDIRECT_URI
    return flow


def start_oauth_flow() -> str:
    """Return the authorization URL for the user to visit."""
    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET:
        return ""
    now = time.time()
    for s, (_, created) in list(_PENDING_FLOWS.items()):
        if now - created > _PENDING_TTL_SECONDS:
            _PENDING_FLOWS.pop(s, None)
    flow = _new_flow()
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")
    _PENDING_FLOWS[state] = (flow.code_verifier, now)
    return auth_url


def parse_redirect(value: str) -> tuple[str, str]:
    """Accept a bare code or a full redirect URL; return (code, state)."""
    value = value.strip()
    if "code=" in value:
        query = parse_qs(urlparse(value).query or value.lstrip("?"))
        return query.get("code", [""])[0], query.get("state", [""])[0]
    return value, ""


def complete_oauth_flow(code: str, state: str = "") -> tuple[bool, str]:
    """Exchange the auth code for credentials and save them. Returns (ok, error message)."""
    if not code:
        return False, "No authorization code found."
    if not state and len(_PENDING_FLOWS) == 1:
        state = next(iter(_PENDING_FLOWS))
    pending = _PENDING_FLOWS.pop(state, None)
    if not pending:
        return False, (
            "This sign-in request is unknown or expired (the app may have restarted). "
            "Click “Start YouTube OAuth” and sign in again."
        )
    code_verifier, _ = pending
    try:
        flow = _new_flow(state=state, code_verifier=code_verifier)
        flow.fetch_token(code=code)
        _save_credentials(flow.credentials)
        return True, ""
    except Exception as exc:
        return False, f"Token exchange failed: {exc}"


def is_authenticated() -> bool:
    creds = _get_credentials()
    return creds is not None and creds.valid


def _build_service():
    creds = _get_credentials()
    if not creds:
        return None
    return build("youtube", "v3", credentials=creds)


def _api_key() -> str:
    # Ignore the placeholder shipped in .env.example.
    key = (YOUTUBE_API_KEY or "").strip()
    return "" if not key or key.lower().startswith("your_") else key


def _read_service():
    """Service for public reads: the signed-in account if available, else the API key."""
    service = _build_service()
    if not service and _api_key():
        service = build("youtube", "v3", developerKey=_api_key())
    return service


# Chat IDs with this prefix are read through youtube_web (no login / API key) using the video ID.
WEB_CHAT_PREFIX = "web:"


def is_web_chat(chat_id: str) -> bool:
    return chat_id.startswith(WEB_CHAT_PREFIX)


_api_chat_ids: dict[str, str] = {}


def _api_chat_id(chat_id: str) -> str:
    """Real liveChatId for API calls (send/ban). Web chat IDs are looked up once the user signs in."""
    if not is_web_chat(chat_id):
        return chat_id
    if chat_id in _api_chat_ids:
        return _api_chat_ids[chat_id]
    service = _build_service()
    if not service:
        return ""
    try:
        resp = service.videos().list(part="liveStreamingDetails", id=chat_id[len(WEB_CHAT_PREFIX):]).execute()
    except HttpError:
        return ""
    items = resp.get("items", [])
    real = items[0].get("liveStreamingDetails", {}).get("activeLiveChatId", "") if items else ""
    if real:
        _api_chat_ids[chat_id] = real
    return real


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
        # "live" | "upcoming" | "none" (ended streams and normal videos report "none")
        "broadcast": snippet.get("liveBroadcastContent", "none"),
        "is_stream": bool(details),
        "ended": bool(details.get("actualEndTime")),
        "viewers": int(details.get("concurrentViewers", 0) or 0),
        "actual_start": details.get("actualStartTime", ""),
        "scheduled_start": details.get("scheduledStartTime", ""),
        "thumbnail": (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
    }


# ── Stream status ──────────────────────────────────────────────────────────────

def get_live_broadcasts() -> list[dict]:
    """Return current/upcoming live broadcasts for the authenticated channel."""
    service = _build_service()
    if not service:
        return []
    try:
        resp = (
            service.liveBroadcasts()
            .list(part="snippet,status,contentDetails", broadcastStatus="active")
            .execute()
        )
        items = resp.get("items", [])
        broadcasts = []
        for item in items:
            snippet = item.get("snippet", {})
            status = item.get("status", {})
            content = item.get("contentDetails", {})
            broadcasts.append(
                {
                    "id": item["id"],
                    "title": snippet.get("title", ""),
                    "status": status.get("lifeCycleStatus", ""),
                    "live_chat_id": content.get("activeLiveChatId", ""),
                    "scheduled_start": snippet.get("scheduledStartTime", ""),
                    "actual_start": snippet.get("actualStartTime", ""),
                    "concurrent_viewers": snippet.get("liveBroadcastContent", ""),
                    "thumbnail": snippet.get("thumbnails", {})
                    .get("default", {})
                    .get("url", ""),
                }
            )
        return broadcasts
    except HttpError:
        return []


def get_stream_details(broadcast_id: str) -> dict:
    """Return bound stream health for a given broadcast id."""
    service = _build_service()
    if not service:
        return {}
    try:
        resp = (
            service.liveStreams()
            .list(part="snippet,status,cdn", mine=True)
            .execute()
        )
        for item in resp.get("items", []):
            return {
                "stream_id": item["id"],
                "title": item.get("snippet", {}).get("title", ""),
                "status": item.get("status", {}).get("streamStatus", ""),
                "health": item.get("status", {}).get("healthStatus", {}).get("status", ""),
                "ingestion_address": item.get("cdn", {})
                .get("ingestionInfo", {})
                .get("ingestionAddress", ""),
            }
        return {}
    except HttpError:
        return {}


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
            if msg_type == "superChatEvent":
                sc = snippet.get("superChatDetails", {})
                # amountDisplayString already includes the currency symbol (e.g. "$5.00", "¥500").
                text = f"[Super Chat {sc.get('amountDisplayString','')}] {sc.get('userComment','')}"
            elif msg_type == "memberMilestoneChatEvent":
                mm = snippet.get("memberMilestoneChatDetails", {})
                text = f"[Member] {mm.get('userComment','')}"
            messages.append(
                {
                    "id": item["id"],
                    "platform": "youtube",
                    "author": author.get("displayName", ""),
                    "author_id": author.get("channelId", ""),
                    "is_owner": author.get("isChatOwner", False),
                    "is_moderator": author.get("isChatModerator", False),
                    "is_verified": author.get("isVerified", False),
                    "text": text,
                    "type": msg_type,
                    "timestamp": snippet.get("publishedAt", ""),
                    "avatar": author.get("profileImageUrl", ""),
                }
            )
        return messages, next_token, polling_ms
    except HttpError:
        return [], "", 5000


def send_chat_message(live_chat_id: str, message: str) -> bool:
    """Send a message to a YouTube live chat."""
    service = _build_service()
    live_chat_id = _api_chat_id(live_chat_id) if service else ""
    if not service or not live_chat_id:
        return False
    try:
        service.liveChatMessages().insert(
            part="snippet",
            body={
                "snippet": {
                    "liveChatId": live_chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {"messageText": message},
                }
            },
        ).execute()
        return True
    except HttpError:
        return False


def send_chat(live_chat_id: str, video_id: str, message: str) -> tuple[bool, str]:
    """Send via OAuth sign-in if available, else via imported browser cookies. Returns (ok, error)."""
    if is_authenticated() and send_chat_message(live_chat_id, message):
        return True, ""
    if youtube_web.has_login():
        if not video_id and is_web_chat(live_chat_id):
            video_id = live_chat_id[len(WEB_CHAT_PREFIX):]
        if not video_id:
            return False, "Cookie login needs the stream URL or video ID (not a raw live chat ID)."
        return youtube_web.send_message(video_id, message)
    if is_authenticated():
        return False, "YouTube API rejected the message."
    return False, "Not signed in to YouTube — sign in (sidebar) or import YouTube cookies in the 🍪 Cookies tab."


def delete_chat_message(message_id: str) -> bool:
    """Delete a chat message by ID."""
    service = _build_service()
    if not service:
        return False
    try:
        service.liveChatMessages().delete(id=message_id).execute()
        return True
    except HttpError:
        return False


def ban_user(live_chat_id: str, channel_id: str, ban_duration_seconds: int = 0) -> bool:
    """Ban (permanent if 0) or timeout a user from live chat."""
    service = _build_service()
    live_chat_id = _api_chat_id(live_chat_id) if service else ""
    if not service or not live_chat_id:
        return False
    try:
        body: dict = {
            "snippet": {
                "liveChatId": live_chat_id,
                "type": "permanent" if ban_duration_seconds == 0 else "temporary",
                "bannedUserDetails": {"channelId": channel_id},
            }
        }
        if ban_duration_seconds > 0:
            body["snippet"]["banDurationSeconds"] = ban_duration_seconds
        service.liveChatBans().insert(part="snippet", body=body).execute()
        return True
    except HttpError:
        return False


def get_channel_stats() -> dict:
    """Return basic channel statistics using API key (no auth needed)."""
    if not YOUTUBE_API_KEY:
        return {}
    try:
        service = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        resp = service.channels().list(part="statistics,snippet", mine=True).execute()
        items = resp.get("items", [])
        if not items:
            return {}
        stats = items[0].get("statistics", {})
        snippet = items[0].get("snippet", {})
        return {
            "name": snippet.get("title", ""),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "total_views": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
        }
    except HttpError:
        return {}
