"""Central configuration loaded from .env file."""
import os
from dotenv import load_dotenv

load_dotenv()

# External API endpoints
YOUTUBE_API_SERVICE: str = "youtube"
YOUTUBE_API_VERSION: str = "v3"
YOUTUBE_WEB_ORIGIN: str = "https://www.youtube.com"
YOUTUBE_CHAT_PAGE_URL: str = f"{YOUTUBE_WEB_ORIGIN}/live_chat"
YOUTUBE_WATCH_PAGE_URL: str = f"{YOUTUBE_WEB_ORIGIN}/watch"
YOUTUBE_GET_LIVE_CHAT_URL: str = f"{YOUTUBE_WEB_ORIGIN}/youtubei/v1/live_chat/get_live_chat"
YOUTUBE_SEND_CHAT_URL: str = f"{YOUTUBE_WEB_ORIGIN}/youtubei/v1/live_chat/send_message"
YOUTUBE_ACCOUNT_MENU_URL: str = f"{YOUTUBE_WEB_ORIGIN}/youtubei/v1/account/account_menu"
YOUTUBE_ACCOUNTS_LIST_URL: str = f"{YOUTUBE_WEB_ORIGIN}/youtubei/v1/account/accounts_list"

BILIBILI_API_ORIGIN: str = "https://api.bilibili.com"
BILIBILI_LIVE_API_ORIGIN: str = "https://api.live.bilibili.com"
BILIBILI_WEB_ORIGIN: str = "https://www.bilibili.com"
BILIBILI_LIVE_ORIGIN: str = "https://live.bilibili.com"
BILIBILI_SHORT_LINK_ORIGIN: str = "https://b23.tv"
BILIBILI_LOGIN_INFO_URL: str = f"{BILIBILI_API_ORIGIN}/x/web-interface/nav"
BILIBILI_GARB_SEARCH_URL: str = f"{BILIBILI_API_ORIGIN}/x/garb/v2/mall/home/search"
BILIBILI_POWER_RIGHTS_URL: str = f"{BILIBILI_API_ORIGIN}/x/upowerv2/gw/rights/index"
BILIBILI_MASTER_INFO_URL: str = f"{BILIBILI_LIVE_API_ORIGIN}/live_user/v1/Master/info"
BILIBILI_ANCHOR_INFO_URL: str = f"{BILIBILI_LIVE_API_ORIGIN}/live_user/v1/UserInfo/get_anchor_in_room"
BILIBILI_ROOM_INFO_URL: str = f"{BILIBILI_LIVE_API_ORIGIN}/room/v1/Room/get_info"
BILIBILI_GUARD_ICON_URL: str = (
    "https://i0.hdslb.com/bfs/activity-plat/static/20200716/"
    "1d0c5a1b042efb59f46d4ba1286c6727/icon-guard{}.png"
)

MISSEVAN_WEB_ORIGIN: str = "https://fm.missevan.com"
MISSEVAN_API_ORIGIN: str = f"{MISSEVAN_WEB_ORIGIN}/api"
MISSEVAN_WEBSOCKET_URL: str = "wss://im.missevan.com/ws?room_id={room_id}"
MISSEVAN_USER_INFO_URL: str = f"{MISSEVAN_API_ORIGIN}/user/info"
MISSEVAN_SEND_MESSAGE_URL: str = f"{MISSEVAN_API_ORIGIN}/chatroom/message/send"
MISSEVAN_ROOM_INFO_URL: str = f"{MISSEVAN_API_ORIGIN}/v2/live/{{room_id}}"
MISSEVAN_CHATROOM_META_URL: str = f"{MISSEVAN_API_ORIGIN}/v2/chatroom/meta"
MISSEVAN_CHAT_HISTORY_URL: str = f"{MISSEVAN_API_ORIGIN}/v2/chatroom/history/message"

GOOGLE_TRANSLATE_URL: str = "https://clients5.google.com/translate_a/t"
DEEPL_TRANSLATE_URL: str = os.getenv(
    "DEEPL_TRANSLATE_URL", "https://api-free.deepl.com/v2/translate"
).strip().rstrip("/")
DEEPL_API_KEY: str = os.getenv("DEEPL_API_KEY", "").strip()
TRANSLATION_PROVIDER: str = os.getenv("TRANSLATION_PROVIDER", "google").strip().lower()
if TRANSLATION_PROVIDER not in {"google", "deepl"}:
    raise ValueError("TRANSLATION_PROVIDER must be 'google' or 'deepl'.")
if TRANSLATION_PROVIDER == "deepl" and not DEEPL_API_KEY:
    raise ValueError("DEEPL_API_KEY is required when TRANSLATION_PROVIDER is 'deepl'.")

# YouTube
YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
# Pre-filled in the YouTube "Room ID or URL" box: a channel link (watched until it goes live) or a stream URL.
YOUTUBE_CHANNEL: str = os.getenv("YOUTUBE_CHANNEL", "")

# Bilibili (login cookies are per user — imported in the 🍪 Cookies tab, never read from .env)
BILIBILI_ROOM_ID: str = os.getenv("BILIBILI_ROOM_ID", "")

# MissEvan
MISSEVAN_ROOM_ID: str = os.getenv("MISSEVAN_ROOM_ID", "")

# OBS
OBS_HOST: str = os.getenv("OBS_HOST", "localhost")
OBS_PORT: int = int(os.getenv("OBS_PORT", "4455"))
OBS_PASSWORD: str = os.getenv("OBS_PASSWORD", "")

# Chat overlay browser source. 127.0.0.1 = this computer only; 0.0.0.0 = reachable from other machines.
OVERLAY_HOST: str = os.getenv("OVERLAY_HOST", "127.0.0.1").strip() or "127.0.0.1"
OVERLAY_PORT: int = int(os.getenv("OVERLAY_PORT", "8502"))
# Optional address shown in the dashboard for OBS, e.g. http://203.0.113.5:8502 or https://overlay.example.com
OVERLAY_PUBLIC_URL: str = os.getenv("OVERLAY_PUBLIC_URL", "").strip().rstrip("/")

# App
TTS_USE_GTTS: bool = os.getenv("TTS_USE_GTTS", "false").lower() == "true"
CHAT_POLL_INTERVAL: int = int(os.getenv("CHAT_POLL_INTERVAL", "5"))
