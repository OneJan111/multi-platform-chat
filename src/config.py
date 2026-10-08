"""Central configuration loaded from .env file."""
import os
from dotenv import load_dotenv

load_dotenv()

# YouTube
YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_CLIENT_ID: str = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET: str = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REDIRECT_URI: str = os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8501/")

# Bilibili
BILIBILI_SESSDATA: str = os.getenv("BILIBILI_SESSDATA", "")
BILIBILI_BILI_JCT: str = os.getenv("BILIBILI_BILI_JCT", "")
BILIBILI_BUVID3: str = os.getenv("BILIBILI_BUVID3", "")
BILIBILI_ROOM_ID: str = os.getenv("BILIBILI_ROOM_ID", "")

# MissEvan
MISSEVAN_ROOM_ID: str = os.getenv("MISSEVAN_ROOM_ID", "869215180")

# OBS
OBS_HOST: str = os.getenv("OBS_HOST", "localhost")
OBS_PORT: int = int(os.getenv("OBS_PORT", "4455"))
OBS_PASSWORD: str = os.getenv("OBS_PASSWORD", "")

# App
TTS_USE_GTTS: bool = os.getenv("TTS_USE_GTTS", "false").lower() == "true"
CHAT_POLL_INTERVAL: int = int(os.getenv("CHAT_POLL_INTERVAL", "5"))
TOKEN_FILE: str = "youtube_token.json"
