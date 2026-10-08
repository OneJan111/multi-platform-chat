# 🎙️ Streaming Dashboard

A Streamlit dashboard for live streamers and their audience. It merges live chat from **YouTube**, **Bilibili** and **MissEvan (猫耳FM)** into one screen, with sending, moderation, translation, text-to-speech, a gifts/Super Chat tracker, OBS control and analytics.

The UI is available in **English / 简体中文 / 日本語** and fits PC and tablet screens (landscape and portrait).

## Features

| Area | What it does |
|---|---|
| 💬 **Chat** | Live chat from YouTube, Bilibili and MissEvan in one feed, with platform badges, per-site show/hide checkboxes and **A− / A+** text size buttons on each feed. |
| ✉️ **Send** | Post one message to several sites at once (tick YouTube / Bilibili / MissEvan). |
| 🎁 **Gifts & Super Chats** | Paid items (Super Chats, Super Stickers, memberships, gifted memberships, Bilibili gold gifts / guards / SC, MissEvan gifts) appear in their own column. Mark each one 🙏 *thanked* (it is greyed out) or *Mark all thanked*. Free gifts stay in regular chat. |
| 👋 **Joins** | Viewers entering the room are listed in their own feed under the gifts, not mixed into chat (toggle *Show join events* in the sidebar). |
| 🛡️ **Moderation** | 🚫 on any message blocks that user. Blocked users, keyword & regex filters and allow-lists are saved to `chat_filters.json` and kept after restarts. |
| 🌐 **Translation** | Inline translation of chat to Chinese (Simplified/Traditional), English, Japanese or Korean. No API key needed. |
| 🔤 **Reading aids** | Pinyin / hiragana ruby over Super Chat text so the streamer can read it aloud. |
| 🔊 **Text-to-speech** | Reads chat aloud (offline `pyttsx3` or online gTTS). Includes: language filter, emoji skipping, reading the translated text (when the TTS language matches *Translate to*), skipping usernames for regular chat, **announcing gifts & Super Chats first**, a 🔊 replay button on every message, and **⏭ Skip / ⏹ Stop TTS** buttons to cut off a sensitive comment instantly. |
| 📡 **Stream Status** | Live / offline state, title and viewer count for each platform. |
| 🎬 **OBS Control** | Start/stop stream & recording and switch scenes via OBS WebSocket v5. Off until you turn on *Connect to OBS* in the sidebar. |
| 📊 **Analytics** | Viewer count (sampled from Stream Status) and messages-per-minute charts, top chatters. |
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

The template only contains placeholder values (`your-…`, `xxx`). **Replace them or delete those lines** — a placeholder is treated as a real setting (e.g. a placeholder `OBS_PASSWORD` makes the app try to log in to OBS with it).

| Variable | Purpose | Default |
|---|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API key — optional; reading chat and stream status fall back to the public web page without it (or when the quota runs out) | — |
| `YOUTUBE_CLIENT_ID` | OAuth client ID for Google sign-in (see [YouTube Google sign-in](#youtube-google-sign-in-optional)) | — |
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
  - Or paste a **channel link** (e.g. `https://www.youtube.com/@Ya-chan`) and click *👀 Watch channel*. The app checks the channel every 60 s, starts reading chat as soon as it goes live, and goes back to watching when the stream ends.
- **Bilibili** — enter the room ID and click *Start Bilibili listener*.
- **MissEvan** — enter the room ID or URL (e.g. `https://fm.missevan.com/live/869215180`) and click *Start MissEvan listener*.

### Logging in to send chat

1. Log in to the site in your normal browser.
2. In the **🍪 Cookies** tab pick the browser and site, then import and save the cookies.
3. Tick the sites under **Send to** above the message box and send.

Sending to YouTube with browser cookies is unofficial and only works on streams with chat enabled. Google sign-in (below) is the official alternative; when both are set up, the official route is tried first.

### YouTube Google sign-in (optional)

Only needed if you want to send YouTube chat through the official API instead of browser cookies.

1. In [Google Cloud Console](https://console.cloud.google.com/) create a project, enable **YouTube Data API v3**, and create an **OAuth client ID** of type *Web application* with the redirect URI `http://localhost:8501/`.
2. Put the client ID / secret in `.env` (`YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`; `YOUTUBE_REDIRECT_URI` must match the URI from step 1) and restart the app.
3. In the sidebar's YouTube section click **Start YouTube OAuth → Open Google sign-in** and approve. Google redirects back to the dashboard and sign-in completes automatically; if it doesn't, paste the full redirect URL into *Redirect URL or code* and click *Submit*.

The login is saved to `youtube_token.json` (git-ignored) and refreshed automatically, so you only sign in once. Delete that file to sign out.

### Chat display

- Each feed (Chat, Gifts & Super Chats, Joins) has **A− / A+** at the top right to resize its text (80–200%).
- The YouTube / Bilibili / MissEvan checkboxes above the feeds show or hide each site's messages.
- Chat refreshes every `CHAT_POLL_INTERVAL` seconds (default 5). *Max messages displayed* in the sidebar limits how many chat lines are kept on screen.
- *🗑️ Clear chat history* (sidebar) empties Chat and Joins but keeps Gifts & Super Chats, so nobody you still need to thank is lost.

### Gifts & Super Chats

- New paid items appear in the right-hand column with a 🙏 button. Click it after thanking the viewer; the item is greyed out with a ✅ *Thanked* badge (click ↩️ to undo).
- *Mark all thanked* marks everything currently pending.
- Thanked status is kept for the current browser session only.

### Blocking users

- Click 🚫 on a message to block its author. Their messages disappear from the dashboard and are filtered from then on; nothing is sent to YouTube / Bilibili / MissEvan.
- Blocks are per platform and saved in `chat_filters.json` (git-ignored), so they survive restarts. Unblock with ✕ in the **🛡️ Filters** tab.
- The Filters tab also takes keywords, regex patterns and user names / IDs to block by hand.

### Text-to-speech

Configure in the sidebar under **🔊 Text-to-Speech**: *Enable TTS*, *Language*, *Ignore emoji*, *Always announce gifts & Super Chats* (read before other chat), *Don't read usernames for regular chat*, *Read translated chat*, *Speed* and *Volume*. Use *▶ Test voice* to check.

To cut off a sensitive comment, use the buttons at the right of the **Send to** row in the Chat tab (shown while TTS is on) or under *▶ Test voice* in the sidebar: **⏭ Skip** stops the current message and goes on to the next; **⏹ Stop TTS** stops it and drops everything still queued. New chat arriving afterwards is still read — turn off *Enable TTS* to silence it completely.

The engine (offline pyttsx3 or online gTTS) is chosen with `TTS_USE_GTTS` in `.env`.

### OBS

In OBS: **Tools → WebSocket Server Settings**, enable the server and set the same port/password as in `.env`. Then turn on **Connect to OBS** in the sidebar (it's off by default, and while off the dashboard never contacts OBS). The scene picker and the 🎬 OBS Control tab appear once OBS is connected; if OBS isn't running it shows as disconnected and is re-checked every 15 seconds.

## Project structure

```
app.py                 Streamlit UI (all tabs, sidebar, CSS)
requirements.txt       Python dependencies
env.template           Template for .env (placeholder values only)
.env                   Your settings and login cookies        (created by you / the app, git-ignored)
youtube_token.json     Saved Google sign-in                   (created by the app, git-ignored)
chat_filters.json      Saved blocks and filters               (created by the app, git-ignored)
src/
  config.py            .env settings
  i18n.py              UI translations (en / zh / ja)
  youtube.py           YouTube Data API + Google sign-in (official); falls back to youtube_web.py
  youtube_web.py       YouTube live chat without API key, cookie login & send
  bilibili.py          Bilibili danmaku listener, gifts, send, moderation
  missevan.py          MissEvan (猫耳FM) chat listener, login & send
  browser_cookies.py   Import cookies from installed browsers
  filters.py           Keyword / regex / user chat filters (saved to chat_filters.json)
  translate.py         Background, cached chat translation
  reading.py           Pinyin / hiragana reading aids
  tts.py               Text-to-speech with priority queue
  obs_ctrl.py          OBS WebSocket v5 control
```

## Troubleshooting

| Problem | Fix |
|---|---|
| OBS shows "not connected" | OBS isn't running or its WebSocket server is off — start OBS / enable the server and check `OBS_PORT` / `OBS_PASSWORD`. If you don't use OBS, turn off *Connect to OBS*. |
| Google sign-in: "request is unknown or expired" | The app restarted or 10 minutes passed. Click *Start YouTube OAuth* and sign in again. |
| Google sign-in: `redirect_uri_mismatch` | `YOUTUBE_REDIRECT_URI` must exactly match the redirect URI in Google Cloud Console (including the trailing `/`). |
| `bilibili-api-python not installed or connection failed` | Run `pip install -r requirements.txt` inside the venv; check the room ID and network. |
| YouTube send: "Chat is disabled" | The stream has chat turned off or is not live. |
| Some languages aren't read aloud offline | Offline TTS uses the voices installed in Windows. Check *Settings → Time & language → Speech* for a Chinese / Japanese voice, or set `TTS_USE_GTTS=true`. |
| No Korean voice offline | Install a Korean voice in Windows (Settings → Time & language → Speech) or set `TTS_USE_GTTS=true`. |
| TTS silent | Check *Enable TTS*, the volume, and that the message language matches the TTS *Language* (or use *Auto-detect*). |
