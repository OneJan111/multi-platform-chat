# 🎙️ Streaming Dashboard

**English** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

A Streamlit dashboard for live streamers and their audience. It merges live chat from **YouTube**, **Bilibili** and **MissEvan (猫耳FM)** into one screen, with sending, moderation, translation, text-to-speech, a gifts/Super Chat tracker, OBS control and analytics.

The UI is available in **English / 简体中文 / 日本語** and fits PC and tablet screens (landscape and portrait).

## Features

| Area | What it does |
|---|---|
| 💬 **Chat** | Live chat from YouTube, Bilibili and MissEvan in one feed, with platform badges, membership badges with the site's own icon (the YouTube channel's member badge, Bilibili's 舰长/提督/总督 icons; MissEvan 贵族/超粉 shows 💎), per-site show/hide checkboxes and **A− / A+** text size buttons on each feed. Message times use the server's time zone by default; pick another in the sidebar under **🕒 Chat time zone** (remembered in the URL as `?tz=`). **Site emotes** pickers next to the send box send a site's own emotes to that site only: the YouTube channel's member stamps (collected from chat; with a YouTube login the full set, with 🔒 on stamps you can't use) and the Bilibili room's emote packs (needs a Bilibili login; 🔒 emotes need e.g. the fan medal) plus the streamer's **充电表情** (charging-supporter emotes; listed even without a login, usable once you charge the streamer). All packs show on one page; the streamer's own packs (⭐: 充电表情, 房间专属表情 and their own 装扮 packs) come first. Typed YouTube codes such as `:_wave:` become stamps on YouTube and are left out of the copy sent to Bilibili/MissEvan. MissEvan has no emote picker. |
| ✉️ **Send** | Post one message to several sites at once (tick YouTube / Bilibili / MissEvan). |
| 🎁 **Gifts & Super Chats** | Gifts (including free gifts), Super Chats, Super Stickers, memberships and paid questions appear in their own column. YouTube gift memberships show the gifter's purchase ("Gifted 10 memberships") and each recipient ("received a gift membership by …"). Bilibili 🧧 红包 show the sender, price and contents, then the winners when the draw ends. Recipients and winners are listed but not read aloud. Mark each one 🙏 *thanked* (it is greyed out) or *Mark all thanked*. |
| 👋 **Joins** | Viewers entering the room are listed in their own feed under the gifts, not mixed into chat (toggle *Show join events* in the sidebar). |
| 🛡️ **Moderation** | 🚫 on any message blocks that user. Blocked users, keyword & regex filters and allow-lists are saved to `chat_filters.json` and kept after restarts. |
| 🌐 **Translation** | Inline translation of chat to Chinese (Simplified/Traditional), English, Japanese or Korean. No API key needed. |
| 🔤 **Reading aids** | Pinyin / hiragana ruby over Super Chat text so the streamer can read it aloud. |
| 🔊 **Text-to-speech** | Reads chat aloud on this computer (offline `pyttsx3` or online gTTS) or **in the viewer's browser with the device's own voices** (used automatically when the dashboard is opened from another device or Streamlit Cloud). Includes: language filter, emoji skipping, reading the translated text (when the TTS language matches *Translate to*), skipping usernames for regular chat, **announcing gifts & Super Chats first**, a 🔊 replay button on every message, and **⏭ Skip / ⏹ Stop TTS** buttons to cut off a sensitive comment instantly. |
| 📡 **Stream Monitoring** | Per-site controls (stream URL / room ID, start/stop listener, login status) plus live / offline state, title and viewer count for each platform. |
| 🎬 **OBS** | One streamer-only tab for everything OBS: connect, start/stop stream & recording, switch scenes and sources (OBS WebSocket v5), send chat to an OBS Text source, and the chat-only Browser Source overlay. Off until you turn on *Connect to OBS* in that tab. |
| 📊 **Analytics** | Viewer count (sampled from Stream Monitoring) and messages-per-minute charts, top chatters, and 🔥 hotspots for clipping (CSV, timestamp list and DaVinci Resolve EDL markers). |
| 🍪 **Cookies** | Import login cookies for Bilibili, MissEvan and YouTube — read from a browser on this computer (Chrome / Edge / Firefox), or paste / upload cookies exported from any browser (for servers). |

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

Settings are read from a `.env` file in the project root (loaded with `python-dotenv`). Start by copying the template: `Copy-Item env.template .env` (macOS/Linux: `cp env.template .env`). All values are optional — fill in only the platforms you use. Site logins are **not** set in `.env`: each person imports their own cookies in the 🍪 Cookies tab (see [Logging in to send chat](#logging-in-to-send-chat)).

The template only contains placeholder values (`your-…`, `xxx`). **Replace them or delete those lines** — a placeholder is treated as a real setting (e.g. a placeholder `OBS_PASSWORD` makes the app try to log in to OBS with it).

| Variable | Purpose | Default |
|---|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API key — optional; reading chat and stream status fall back to the public web page without it (or when the quota runs out) | — |
| `YOUTUBE_CHANNEL` | Default YouTube channel link (or stream URL) in the Stream Monitoring tab; click *Start listening* to watch it | `https://www.youtube.com/@Ya-chan` |
| `BILIBILI_ROOM_ID` | Default Bilibili live room | — |
| `MISSEVAN_ROOM_ID` | Default MissEvan live room | `869215180` |
| `OBS_HOST` | OBS WebSocket host | `localhost` |
| `OBS_PORT` | OBS WebSocket port | `4455` |
| `OBS_PASSWORD` | OBS WebSocket password | — |
| `OVERLAY_HOST` | Chat overlay listen address: `127.0.0.1` = this computer only, `0.0.0.0` = reachable from other machines | `127.0.0.1` |
| `OVERLAY_PORT` | Chat overlay port | `8502` |
| `OVERLAY_PUBLIC_URL` | Overlay address shown in the 🎬 OBS tab (e.g. `http://203.0.113.5:8502` or a reverse-proxy URL) | auto |
| `TTS_USE_GTTS` | `true` = online gTTS, `false` = offline pyttsx3 | `false` |
| `CHAT_POLL_INTERVAL` | Chat refresh interval in seconds | `5` |
| `LOGIN_SECRET` | Key that encrypts each user's logins in their browser. Changing it logs everyone out | random, in `.login_secret` |

> ⚠️ `.env` and `.login_secret` contain secrets and are listed in `.gitignore`. Never commit or share them.

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
- **Bilibili** — the room ID or URL (e.g. `https://live.bilibili.com/21452505`, or a `b23.tv` share link). Without login cookies Bilibili masks usernames (e.g. 波***).
- **MissEvan** — the room ID or URL (e.g. `https://fm.missevan.com/live/869215180`).

### Logging in to send chat

1. Log in to the site in your normal browser.
2. In the **🍪 Cookies** tab pick the browser and site, then import the cookies and click **Use these cookies**.
   - **App running on a server / another computer?** The app can only read a browser installed on the machine it runs on (otherwise you get `Could not find Firefox profile directory`), so **🧭 Browser on this computer** is only offered when the dashboard is opened on that machine itself. Choose **📋 Paste / upload cookies** instead and paste cookies exported from your own browser: a `Cookie:` header copied from DevTools (F12 → Network), or an export from an extension such as *Get cookies.txt LOCALLY* (Netscape `cookies.txt`) or *Cookie-Editor* (JSON). Upload the exported file if you prefer.
3. Tick the sites under **Send to** above the message box and send.

**Logins are per user.** Everyone who opens the dashboard has their own logins: your cookies are never used or shown for anyone else, and other users can't send chat as you. Your logins are stored only in your own browser as an encrypted cookie (the server keeps only the key, `LOGIN_SECRET` / `.login_secret`), so they survive a page refresh or server restart. Opening the dashboard in another browser or a private window starts logged out. Listeners you start use the login you had when you started them.

The 🔑 line in each **📡 Stream Monitoring** column shows the login state. Sending to MissEvan is disabled when its cookies have expired. Click **🚪 Clear login** under it to forget that site's cookies — they are removed from this session and this browser, and chat keeps working read-only.

If your Google login owns several YouTube channels (brand accounts), a **Send as** picker appears under the YouTube login line. Pick the channel your chat messages should come from. The choice is per user and remembered with your login. To use a different Google account, import that account's cookies in the 🍪 Cookies tab.

Sending to YouTube with browser cookies is unofficial (it works like youtube.com itself) and only works on streams with chat enabled.

### Chat display

- Each feed (Chat, Gifts & Super Chats, Joins) has **A− / A+** at the top right to resize its text (80–200%).
- The YouTube / Bilibili / MissEvan checkboxes above the feeds show or hide each site's messages.
- Chat refreshes every `CHAT_POLL_INTERVAL` seconds (default 5). *Max messages displayed* in the sidebar limits how many chat lines are kept on screen.
- *🗑️ Clear chat history* (sidebar) empties Chat and Joins but keeps Gifts & Super Chats, so nobody you still need to thank is lost.

### Gifts & Super Chats

- New gifts and Super Chats appear in the right-hand column. Click an item after thanking the viewer; it is greyed out with a ✅ *Thanked* badge. Click it again to undo.
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

**Speak on → This browser (device voices)** uses the browser's Web Speech API instead, so it works on Streamlit Cloud or a remote server (which have no speakers). Remote viewers always get browser voices. The page must stay open, and browsers only allow sound after you've clicked somewhere on the page once.

### OBS

In OBS: **Tools → WebSocket Server Settings**, enable the server and set the same port/password as in `.env`. Then open the **🎬 OBS** tab and turn on **Connect to OBS** (it's off by default, and while off the dashboard never contacts OBS). All OBS functions live in that one tab: stream/recording controls, scenes and sources appear once OBS is connected; if OBS isn't running it shows as disconnected and is re-checked every 15 seconds.

To show chat in OBS, add a **Text (GDI+)** source (or a FreeType text source), then enable **Send chat to OBS Text source** in the 🎬 OBS tab and select it. The source shows the last 10 regular chat messages, oldest first, without usernames or badges. When **Translate chat** is enabled, each available translation appears beneath its original; turning it off removes translations on the next update. OBS chat output is opt-in and uses the configured WebSocket server; the separate Browser Source overlay preview does not update this Text source.

Alternatively, add an OBS **Browser Source** pointed at `http://localhost:8502/overlay` (not `:8501/overlay`). This page pins Super Chats, gifts and memberships (Bilibili SC and gifts, MissEvan paid questions and gifts, YouTube Super Chats/Stickers and memberships) to the top of the overlay and regular chat to the bottom, so busy chat never pushes paid events away (3 by default; set **Super Chats & gifts shown in OBS overlay** to 0 to hide), then the most recent regular chat messages (5 by default; change **Messages shown in OBS overlay** in the 🎬 OBS tab, 1–50), available translations only when **Translate chat** is enabled, and the optional custom overlay message. In the 🎬 OBS tab, turn off **Show usernames in OBS overlay** to display chat text without usernames (on by default); the preview follows the same setting. Bilibili custom emotes (e.g. `[doge]`), sticker danmaku, YouTube channel custom emojis (member stamps such as `:_wave:`) and Super Sticker images appear as images in the dashboard, preview and Browser Source; the OBS Text source can only show the text code. Keep the dashboard open for updates. Port 8502 (`OVERLAY_PORT`) must be free; an error in the 🎬 OBS tab reports if the overlay server cannot start. The Browser Source works even when *Connect to OBS* is off. By default the overlay listens only on `127.0.0.1`; when the dashboard runs on a server, set `OVERLAY_HOST=0.0.0.0` (and open the port in the firewall) so OBS on your PC can load `http://<server>:8502/overlay` — the 🎬 OBS tab shows the exact URL. The overlay is read-only and only shows public chat. If several people use the same dashboard, give each one a different **Overlay channel** in the 🎬 OBS tab (adds `?ch=name` to the overlay URL); otherwise every open dashboard publishes to the same overlay and the last one wins.

To show only some sites on an overlay, pick them under **Sites on this overlay** in the 🎬 OBS tab, or add `site=` to the URL yourself: `/overlay?site=youtube`, `/overlay?site=bilibili,missevan`, `/overlay?ch=alice&site=bili` (short names `yt`, `bili`, `me` also work). Each URL gets its own full message counts, so you can add one Browser Source per site (e.g. YouTube chat on one side, Bilibili on the other). Without `site=` every site is shown.

**Streamlit Community Cloud / hosted dashboards:** only the dashboard port is public there, so `:8502/overlay` cannot be reached. The 🎬 OBS tab then shows dashboard links instead, e.g. `https://your-app.streamlit.app/?view=overlay&youtube=@channel&n=10&sc=5`. That page shows only the overlay and refreshes every 2 seconds. If the background is not transparent in OBS, add `body, .stApp { background: transparent !important; }` to the Browser Source's *Custom CSS*.

### 🔥 Hotspots for clipping

The 📊 Analytics tab finds moments where chat, gifts and Super Chats spike well above the stream's usual level (score = messages + 5 × gifts/SC per window, compared with the median). Each hotspot lists start/end times counted from the stream start (taken automatically from Stream Monitoring, or the first message, or a clock time you enter), its peak, and the hot phrases. Lead-in (20 s by default) moves clip starts earlier, because chat reacts after the moment happens. Download as:

- **CSV** (opens in Excel), with times, counts and phrases;
- **Timestamps (.txt)**, `HH:MM:SS` lines you can paste into a video description or note;
- **Markers (.edl)** for DaVinci Resolve: put the recording on a timeline, then right-click the timeline in the Media Pool > *Timelines > Import > Timeline Markers from EDL*. *EDL timeline start* must match the timeline start (`01:00:00:00` by default, as in Resolve).

Only messages received while the dashboard page is open are counted.

## Project structure

```
app.py                 Streamlit UI (all tabs, sidebar, CSS)
requirements.txt       Python dependencies
env.template           Template for .env (placeholder values only)
.env                   Your settings                          (created by you, git-ignored)
.login_secret          Key encrypting users' browser-stored logins (created by the app, git-ignored)
chat_filters.json      Saved blocks and filters               (created by the app, git-ignored)
src/
  config.py            .env settings
  i18n.py              UI translations (en / zh / ja)
  youtube.py           YouTube stream lookup + chat (Data API with YOUTUBE_API_KEY, else youtube_web.py)
  youtube_web.py       YouTube live chat without API key, cookie login & send
  bilibili.py          Bilibili danmaku listener, gifts, send, moderation
  emotes.py            Bilibili emote/sticker image parsing and safe rendering
  missevan.py          MissEvan (猫耳FM) chat listener, login & send
  browser_cookies.py   Import cookies from installed browsers or pasted/exported text
  user_login.py        Per-user logins (session + encrypted browser cookie)
  filters.py           Keyword / regex / user chat filters (saved to chat_filters.json)
  translate.py         Background, cached chat translation
  reading.py           Pinyin / hiragana reading aids
  tts.py               Text-to-speech with priority queue
  obs_ctrl.py          OBS WebSocket v5 control
```

## Troubleshooting

| Problem | Fix |
|---|---|
| OBS shows "not connected" | The warning names the cause. *Nothing answered*: OBS isn't running or its WebSocket server is off — start OBS / enable the server and check `OBS_HOST` / `OBS_PORT`. *Refused the login*: wrong `OBS_PASSWORD`. If you don't use OBS, turn off *Connect to OBS*. |
| OBS not connected when the dashboard runs on a server | `OBS_HOST=localhost` means the server itself. Set `OBS_HOST` to the IP of the PC running OBS, make it reachable from the server (same LAN, VPN such as Tailscale, or a port forward) and allow port 4455 in that PC's firewall. The chat overlay (`:8502`) listens only on `127.0.0.1` unless you set `OVERLAY_HOST=0.0.0.0` and allow the port in the server firewall. |
| `bilibili-api-python not installed or connection failed` | Run `pip install -r requirements.txt` inside the venv; check the room ID and network. |
| YouTube send: "Chat is disabled" | The stream has chat turned off or is not live. |
| Some languages aren't read aloud offline | Offline TTS uses the voices installed in Windows. Check *Settings → Time & language → Speech* for a Chinese / Japanese voice, or set `TTS_USE_GTTS=true`. |
| No Korean voice offline | Install a Korean voice in Windows (Settings → Time & language → Speech) or set `TTS_USE_GTTS=true`. |
| TTS silent | Check *Enable TTS*, the volume, and that the message language matches the TTS *Language* (or use *Auto-detect*). |
