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
| 📡 **Stream Monitoring** | Per-site controls (stream URL / room ID, start/stop listener, login status) plus live / offline state, title and viewer count for each platform. |
| 🎬 **OBS** | One streamer-only tab for everything OBS: connect, start/stop stream & recording, switch scenes and sources (OBS WebSocket v5), send chat to an OBS Text source, and the chat-only Browser Source overlay. Off until you turn on *Connect to OBS* in that tab. |
| 📊 **Analytics** | Viewer count (sampled from Stream Monitoring) and messages-per-minute charts, top chatters. |
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

Settings are read from a `.env` file in the project root (loaded with `python-dotenv`). Start by copying the template: `Copy-Item env.template .env` (macOS/Linux: `cp env.template .env`). All values are optional — fill in only the platforms you use. Cookie values can be imported **by the app** from the 🍪 Cookies tab, so you rarely need to edit them by hand. By default imported cookies are kept in memory only (never written to disk, re-import after a restart); tick **Also save to .env** to keep them across restarts.

The template only contains placeholder values (`your-…`, `xxx`). **Replace them or delete those lines** — a placeholder is treated as a real setting (e.g. a placeholder `OBS_PASSWORD` makes the app try to log in to OBS with it).

| Variable | Purpose | Default |
|---|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API key — optional; reading chat and stream status fall back to the public web page without it (or when the quota runs out) | — |
| `YOUTUBE_CHANNEL` | Default YouTube channel link (or stream URL) in the Stream Monitoring tab; click *Start listening* to watch it | `https://www.youtube.com/@Ya-chan` |
| `YOUTUBE_COOKIE` | YouTube login cookies (for sending chat) | — |
| `YOUTUBE_PAGE_ID` | Channel to send YouTube chat as, for Google logins with several channels (set by **Send as**) | main channel |
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

> ⚠️ `.env` contains login secrets and is listed in `.gitignore`. Never commit or share them.

## Running

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Then open <http://localhost:8501>. To use it from a tablet on the same network, open `http://<PC-IP>:8501`.

## Usage

### Reading chat (no login needed)

Each site has a column on the **📡 Stream Monitoring** tab, and every column has the same layout:

1. **🔑 Login** — who you're logged in as (re-checked every 5 minutes), *Login expired*, or *Not logged in — chat is read-only*.
2. **Room ID or URL** — the stream to read.
3. **🎧 Listener** — *Listening ✓* / *Connecting…* / *Not listening*, with **▶ Start listening** and **⏹ Stop listening**. Changing the room stops the current listener.
4. The stream's live / offline state, title and viewers.

What goes in **Room ID or URL**:

- **YouTube** — a live stream URL or video ID. Or a **channel link** (e.g. `https://www.youtube.com/@Ya-chan`): the app checks the channel every 60 s, starts reading chat as soon as it goes live, and goes back to watching when the stream ends.
- **Bilibili** — the room ID or URL (e.g. `https://live.bilibili.com/21452505`). Without login cookies Bilibili masks usernames (e.g. 波***).
- **MissEvan** — the room ID or URL (e.g. `https://fm.missevan.com/live/869215180`).

### Logging in to send chat

1. Log in to the site in your normal browser.
2. In the **🍪 Cookies** tab pick the browser and site, then import the cookies and click **Use these cookies** (memory only unless **Also save to .env** is ticked).
3. Tick the sites under **Send to** above the message box and send.

The 🔑 line in each **📡 Stream Monitoring** column shows the login state. Sending to MissEvan is disabled when its cookies have expired. Click **🚪 Clear login** under it to forget that site's cookies — they are removed from memory and from `.env`, and chat keeps working read-only.

If your Google login owns several YouTube channels (brand accounts), a **Send as** picker appears under the YouTube login line. Pick the channel your chat messages should come from. The choice is kept in memory, or saved to `.env` as `YOUTUBE_PAGE_ID` when cookie saving to `.env` is enabled. To use a different Google account, import that account's cookies in the 🍪 Cookies tab.

Sending to YouTube with browser cookies is unofficial (it works like youtube.com itself) and only works on streams with chat enabled.

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

To cut off a sensitive comment, use the buttons at the **top right of the 💬 Chat feed** (shown while TTS is on): **⏭ Skip** stops the current message and goes on to the next; **⏹ Stop TTS** stops it and drops everything still queued. New chat arriving afterwards is still read — turn off *Enable TTS* to silence it completely.

The engine (offline pyttsx3 or online gTTS) is chosen with `TTS_USE_GTTS` in `.env`.

### OBS

In OBS: **Tools → WebSocket Server Settings**, enable the server and set the same port/password as in `.env`. Then open the **🎬 OBS** tab and turn on **Connect to OBS** (it's off by default, and while off the dashboard never contacts OBS). All OBS functions live in that one tab: stream/recording controls, scenes and sources appear once OBS is connected; if OBS isn't running it shows as disconnected and is re-checked every 15 seconds.

To show chat in OBS, add a **Text (GDI+)** source (or a FreeType text source), then enable **Send chat to OBS Text source** in the 🎬 OBS tab and select it. The source shows the last 10 regular chat messages, oldest first, without usernames or badges. When **Translate chat** is enabled, each available translation appears beneath its original; turning it off removes translations on the next update. OBS chat output is opt-in and uses the configured WebSocket server; the separate Browser Source overlay preview does not update this Text source.

Alternatively, add an OBS **Browser Source** pointed at `http://localhost:8502/overlay` (not `:8501/overlay`). This local-only page pins Super Chats, gifts and memberships (Bilibili SC and gifts, MissEvan paid questions and gifts, YouTube Super Chats/Stickers and memberships) to the top of the overlay and regular chat to the bottom, so busy chat never pushes paid events away (3 by default; set **Super Chats & gifts shown in OBS overlay** to 0 to hide), then the most recent regular chat messages (5 by default; change **Messages shown in OBS overlay** in the 🎬 OBS tab, 1–50), available translations only when **Translate chat** is enabled, and the optional custom overlay message. In the 🎬 OBS tab, turn off **Show usernames in OBS overlay** to display chat text without usernames (on by default); the preview follows the same setting. Bilibili custom emotes (e.g. `[doge]`) and sticker danmaku appear as images in the dashboard, preview and Browser Source; the OBS Text source can only show the text code. Keep the dashboard open for updates. Port 8502 must be free; an error in the 🎬 OBS tab reports if the local server cannot start. The Browser Source works even when *Connect to OBS* is off. OBS on another computer cannot reach this loopback address.

## Project structure

```
app.py                 Streamlit UI (all tabs, sidebar, CSS)
requirements.txt       Python dependencies
env.template           Template for .env (placeholder values only)
.env                   Your settings and login cookies        (created by you / the app, git-ignored)
chat_filters.json      Saved blocks and filters               (created by the app, git-ignored)
src/
  config.py            .env settings
  i18n.py              UI translations (en / zh / ja)
  youtube.py           YouTube stream lookup + chat (Data API with YOUTUBE_API_KEY, else youtube_web.py)
  youtube_web.py       YouTube live chat without API key, cookie login & send
  bilibili.py          Bilibili danmaku listener, gifts, send, moderation
  emotes.py            Bilibili emote/sticker image parsing and safe rendering
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
| `bilibili-api-python not installed or connection failed` | Run `pip install -r requirements.txt` inside the venv; check the room ID and network. |
| YouTube send: "Chat is disabled" | The stream has chat turned off or is not live. |
| Some languages aren't read aloud offline | Offline TTS uses the voices installed in Windows. Check *Settings → Time & language → Speech* for a Chinese / Japanese voice, or set `TTS_USE_GTTS=true`. |
| No Korean voice offline | Install a Korean voice in Windows (Settings → Time & language → Speech) or set `TTS_USE_GTTS=true`. |
| TTS silent | Check *Enable TTS*, the volume, and that the message language matches the TTS *Language* (or use *Auto-detect*). |
