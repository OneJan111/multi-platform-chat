# 🎙️ Streaming Dashboard

A Streamlit dashboard for live streamers and their audience. It merges live chat from **YouTube**, **Bilibili** and **MissEvan (猫耳FM)** into one screen, with sending, moderation, translation, text-to-speech, a gifts/Super Chat tracker, OBS control and analytics.

The UI is available in **English / 简体中文 / 日本語** and fits PC and tablet screens (landscape and portrait).

## Features

| Area | What it does |
|---|---|
| 💬 **Chat** | Live chat from YouTube, Bilibili and MissEvan in one feed, with platform badges and per-site show/hide checkboxes. |
| ✉️ **Send** | Post one message to several sites at once (tick YouTube / Bilibili / MissEvan). |
| 🎁 **Gifts & Super Chats** | Paid items (Super Chats, Super Stickers, memberships, gifted memberships, Bilibili gold gifts / guards / SC, MissEvan gifts) appear in their own column. Mark each one 🙏 *thanked* (it is greyed out) or *Mark all thanked*. Free gifts stay in regular chat. |
| 🛡️ **Moderation** | Ban / timeout / delete from a message, keyword & regex filters, allow-lists and blocked users. |
| 🌐 **Translation** | Inline translation of chat to Chinese (Simplified/Traditional), English, Japanese or Korean. No API key needed. |
| 🔤 **Reading aids** | Pinyin / hiragana ruby over Super Chat text so the streamer can read it aloud. |
| 🔊 **Text-to-speech** | Reads chat aloud (offline `pyttsx3` or online gTTS). Includes: language filter, emoji skipping, reading the translated text (when the TTS language matches *Translate to*), skipping usernames for regular chat, **announcing gifts & Super Chats first**, and a 🔊 replay button on every message. |
| 🎬 **OBS Control** | Start/stop stream & recording and switch scenes via OBS WebSocket v5. |
| 📊 **Analytics** | Viewer count and messages-per-minute charts, top chatters. |
| 🖥️ **Overlay** | Chat overlay preview for use in OBS. |
| 🍪 **Cookies** | Import login cookies from your browser (Chrome / Edge / Firefox …) for Bilibili, MissEvan and YouTube. |

## Requirements

- Python 3.10+ (developed on 3.14)
- Windows, macOS or Linux (offline TTS voices depend on the OS)
- Optional: [OBS Studio](https://obsproject.com/) 28+ with WebSocket server enabled

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Settings are read from a `.env` file in the project root (loaded with `python-dotenv`). Start by copying the template: `Copy-Item env.template .env` (macOS/Linux: `cp env.template .env`). All values are optional — fill in only the platforms you use. Cookie values are normally written **by the app** from the 🍪 Cookies tab, so you rarely need to edit them by hand.

| Variable | Purpose | Default |
|---|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API key (stream status / analytics) | — |
| `YOUTUBE_CLIENT_ID` | OAuth client ID (official send / moderation) | — |
| `YOUTUBE_CLIENT_SECRET` | OAuth client secret | — |
| `YOUTUBE_REDIRECT_URI` | OAuth redirect URI | `http://localhost:8501/` |
| `YOUTUBE_COOKIE` | Browser cookies for sending chat without OAuth (unofficial) | — |
| `BILIBILI_ROOM_ID` | Default Bilibili live room | — |
| `BILIBILI_SESSDATA` | Bilibili login cookie | — |
| `BILIBILI_BILI_JCT` | Bilibili CSRF cookie | — |
| `BILIBILI_BUVID3` | Bilibili device cookie | — |
| `BILIBILI_DEDEUSERID` | Bilibili user ID cookie | — |
| `MISSEVAN_ROOM_ID` | Default MissEvan live room | `869215180` |
| `MISSEVAN_COOKIE` | MissEvan login cookies (for sending chat) | — |
| `OBS_HOST` | OBS WebSocket host | `localhost` |
| `OBS_PORT` | OBS WebSocket port | `4455` |
| `OBS_PASSWORD` | OBS WebSocket password | — |
| `TTS_USE_GTTS` | `true` = online gTTS, `false` = offline pyttsx3 | `false` |
| `CHAT_POLL_INTERVAL` | Chat refresh interval in seconds | `5` |

> ⚠️ `.env` and `youtube_token.json` contain login secrets and are listed in `.gitignore`. Never commit or share them.

## Running

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Then open <http://localhost:8501>. To use it from a tablet on the same network, open `http://<PC-IP>:8501`.

## Usage

### Reading chat (no login needed)

- **YouTube** — paste a live stream URL, video ID or live chat ID in the sidebar and click *Start YouTube listener*.
- **Bilibili** — enter the room ID and click *Start Bilibili listener*.
- **MissEvan** — enter the room ID or URL (e.g. `https://fm.missevan.com/live/869215180`) and click *Start MissEvan listener*.

### Logging in to send chat

1. Log in to the site in your normal browser.
2. In the **🍪 Cookies** tab pick the browser and site, then import and save the cookies.
3. Tick the sites under **Send to** above the message box and send.

YouTube can also use official OAuth (`YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`). Sending with browser cookies is unofficial and only works on streams with chat enabled.

### Gifts & Super Chats

- New paid items appear in the right-hand column with a 🙏 button. Click it after thanking the viewer; the item is greyed out with a ✅ *Thanked* badge (click ↩️ to undo).
- *Mark all thanked* marks everything currently pending.
- Thanked status is kept for the current browser session only.

### Text-to-speech

Configure in the sidebar under **🔊 Text-to-Speech**: *Enable TTS*, *Language*, *Ignore emoji*, *Always announce gifts & Super Chats* (read before other chat), *Don't read usernames for regular chat*, *Read translated chat*, *Speed* and *Volume*. Use *▶ Test voice* to check. The engine (offline pyttsx3 or online gTTS) is chosen with `TTS_USE_GTTS` in `.env`.

### OBS

In OBS: **Tools → WebSocket Server Settings**, enable the server and set the same port/password as in `.env`. If OBS is not running the OBS tab simply shows it as disconnected.

## Project structure

```
app.py                 Streamlit UI (all tabs, sidebar, CSS)
requirements.txt       Python dependencies
src/
  config.py            .env settings
  i18n.py              UI translations (en / zh / ja)
  youtube.py           YouTube Data API + OAuth (official)
  youtube_web.py       YouTube live chat without API key, cookie login & send
  bilibili.py          Bilibili danmaku listener, gifts, send, moderation
  missevan.py          MissEvan (猫耳FM) chat listener, login & send
  browser_cookies.py   Import cookies from installed browsers
  filters.py           Keyword / regex / user chat filters
  translate.py         Background, cached chat translation
  reading.py           Pinyin / hiragana reading aids
  tts.py               Text-to-speech with priority queue
  obs_ctrl.py          OBS WebSocket v5 control
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ConnectionRefusedError [WinError 10061]` (OBS) | OBS isn't running or its WebSocket server is off — start OBS / enable the server, or ignore if you don't use OBS. |
| `bilibili-api-python not installed or connection failed` | Run `pip install -r requirements.txt` inside the venv; check the room ID and network. |
| YouTube send: "Chat is disabled" | The stream has chat turned off or is not live. |
| No Korean voice offline | Install a Korean voice in Windows (Settings → Time & language → Speech) or set `TTS_USE_GTTS=true`. |
| TTS silent | Check *Enable TTS*, the volume, and that the message language matches the TTS *Language* (or use *Auto-detect*). |
