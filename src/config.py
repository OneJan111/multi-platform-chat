"""Central configuration loaded from .env file."""
import os
from dotenv import load_dotenv

load_dotenv()

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
