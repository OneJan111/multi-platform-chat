"""Central configuration loaded from .env file."""
import os
from dotenv import load_dotenv

load_dotenv()

# YouTube
YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
# Pre-filled in the YouTube "Room ID or URL" box: a channel link (watched until it goes live) or a stream URL.
YOUTUBE_CHANNEL: str = os.getenv("YOUTUBE_CHANNEL", "")

# Bilibili
BILIBILI_SESSDATA: str = os.getenv("BILIBILI_SESSDATA", "")
BILIBILI_BILI_JCT: str = os.getenv("BILIBILI_BILI_JCT", "")
BILIBILI_BUVID3: str = os.getenv("BILIBILI_BUVID3", "")
BILIBILI_ROOM_ID: str = os.getenv("BILIBILI_ROOM_ID", "")

# MissEvan
MISSEVAN_ROOM_ID: str = os.getenv("MISSEVAN_ROOM_ID", "")

# OBS
OBS_HOST: str = os.getenv("OBS_HOST", "localhost")
OBS_PORT: int = int(os.getenv("OBS_PORT", "4455"))
OBS_PASSWORD: str = os.getenv("OBS_PASSWORD", "")

# App
TTS_USE_GTTS: bool = os.getenv("TTS_USE_GTTS", "false").lower() == "true"
CHAT_POLL_INTERVAL: int = int(os.getenv("CHAT_POLL_INTERVAL", "5"))
