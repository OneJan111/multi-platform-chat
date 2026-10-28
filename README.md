# 🎙️ Streaming Dashboard

**English** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

A Streamlit dashboard for live streamers and their audience. It merges live chat from **YouTube**, **Bilibili** and **MissEvan (猫耳FM)** into one screen, with sending, moderation, translation, text-to-speech, a gifts/Super Chat tracker, OBS control and analytics.

The UI is available in **English / 简体中文 / 日本語** and fits PC and tablet screens (landscape and portrait).

## TL;DR

A multilingual dashboard for monitoring **YouTube, Bilibili and MissEvan** live streams in one place. Read and send chat, moderate and translate messages, track gifts and revenue, use text-to-speech, and control OBS or show a chat overlay.

## Features

| Area | What it does |
|---|---|
| 💬 **Chat** | Live chat from YouTube, Bilibili and MissEvan in one feed, with platform badges, membership badges with the site's own icon (the YouTube channel's member badge, Bilibili's 舰长/提督/总督 icons; MissEvan 贵族/超粉 shows 💎), per-site show/hide checkboxes, and a single global text-size control in the sidebar. Message times use the server's time zone by default; pick another in the sidebar under **🕒 Chat time zone** (remembered in the URL as `?tz=`). **Site emotes** pickers next to the send box offer YouTube channel stamps, Bilibili room emote packs and MissEvan room stickers plus the site's built-in preset kaomoji. YouTube stamps are collected from chat (with a YouTube login the full set is listed, with 🔒 on stamps you can't use); Bilibili packs need a Bilibili login and 🔒 emotes may require e.g. the fan medal. The streamer's **充电表情** (charging-supporter emotes) are listed even without a login, usable once you charge the streamer. Bilibili and MissEvan pickers are available only while listening to that room. YouTube stamps and MissEvan kaomoji are added to the message box and sent when you press **Send**; clicking a Bilibili special emote sends it immediately as its own danmaku. YouTube/Bilibili emotes are sent only to their own site, and regular emoji can still be combined in typed danmaku. Clicking a MissEvan room sticker sends it immediately. Packs are cached for the current YouTube stream / Bilibili room and fetched again when you switch streams or rooms. Each pack can be collapsed (or use **Expand all / Collapse all**); the streamer's own Bilibili packs (⭐: 充电表情, 房间专属表情 and their own 装扮 packs) come first and start open. 装扮 packs are named after the 装扮, plus the UP主 it belongs to when the 装扮 shop lists one. Typed YouTube codes such as `:_wave:` become stamps on YouTube and are left out of the copy sent to Bilibili/MissEvan. |
| 🐱 **MissEvan room stickers** | The MissEvan picker loads available sticker packages for the selected room after login. Open a package and click a sticker to send it immediately to MissEvan; locked packages are disabled. Received room stickers are displayed as images in chat and the OBS browser overlay when their image is served from MissEvan's trusted CDN. |
| ✉️ **Send** | Post one message to several sites at once (tick YouTube / Bilibili / MissEvan). |
| 🎁 **Gifts & Super Chats** | Gifts (including free gifts), Super Chats, Super Stickers, memberships and paid questions appear in their own column. Known gift prices appear beside each gift; the received total is shown by currency, without converting or combining currencies. YouTube gift memberships show the gifter's purchase ("Gifted 10 memberships") and each recipient ("received a gift membership by …"). Bilibili 🧧 红包 show the sender, price and contents, then the winners when the draw ends. Recipients and winners are listed but not read aloud. Mark each one 🙏 *thanked* (it is greyed out) or *Mark all thanked*. |
| 👋 **Joins** | On wide screens, viewers entering the room appear in a separate feed under gifts. On narrow screens, only the latest arrival appears as a single line in chat. |
| 🛡️ **Moderation** | 🚫 on any message blocks that user. Blocked users, keyword & regex filters and allow-lists are saved to `chat_filters.json` and kept after restarts. |
| 🌐 **Translation** | Start translation from the sidebar to translate chat and live transcription into the selected target language when the detected/source language differs. Supports Chinese (Simplified/Traditional), English, Japanese and Korean. Choose Index-Translate, an OpenAI-compatible API (local or hosted), or Google in `.env`; Index-Translate falls back to Google, while the compatible API uses only its configured endpoint. A built-in streaming glossary overrides machine translations for terms such as *舰长*, *醒目留言*, *上舰* and *弹幕*. |
| 🎙️ **Live transcription** | Transcribe audio from one currently monitored YouTube, Bilibili or MissEvan live stream at a time. While running, the latest three segments appear in a full-width sticky panel above both Chat and Gifts & Super Chats. Audio recognition uses local faster-whisper; the selected model downloads on first use. FFmpeg is required. Transcription is translated into the selected target language when translation is started and the detected language differs. |
| 🔤 **Reading aids** | In the desktop chat, pinyin / furigana for message text and usernames appears in a tooltip on hover, rather than inline. Super Chat text, gift names and usernames elsewhere can show ruby readings; translations into Japanese get furigana, and Super Chat and gift translations into Chinese get pinyin. |
| 💾 **Remembered settings** | Your settings (TTS, translation, message order, text size, OBS overlay options, language, time zone, …) are saved in this browser and restored next time. Feed layout adjusts automatically to screen width. Room IDs, stream URLs and chat aren't saved; logins use their own cookie. |
| 🔊 **Text-to-speech** | Reads chat aloud on this computer (offline `pyttsx3` or online gTTS) or **in the viewer's browser with the device's own voices** (used automatically when the dashboard is opened from another device or Streamlit Cloud). Includes: language filter, emoji skipping, reading the translated text (when the TTS language is Auto-detect or matches *Translate to*), skipping usernames for regular chat, **announcing gifts & Super Chats first**, a 🔊 replay button on every message, and **⏭ Skip / ⏹ Stop TTS** buttons to cut off a sensitive comment instantly. |
| 📡 **Stream Monitoring** | Per-site controls (stream URL / room ID, start/stop listener, login status) plus live / offline state, title and viewer count for each platform. MissEvan room cards also show attention count, VIP count and popularity score on hover. |
| 🎬 **OBS** | One streamer-only tab for everything OBS: connect, start/stop stream & recording, switch scenes and sources (OBS WebSocket v5), send chat to an OBS Text source, and the chat-only Browser Source overlay. Off until you turn on *Connect to OBS* in that tab. |
| 📊 **Analytics** | Viewer count (sampled from Stream Monitoring), messages-per-minute charts, top chatters, per-site gift and Super Chat counts/revenue (totals remain in each site's original currency), and 🔥 hotspots for clipping (CSV, timestamp list and DaVinci Resolve EDL markers). |
| 🍪 **Cookies** | Import login cookies for Bilibili, MissEvan and YouTube — read from a browser on this computer (Chrome / Edge / Firefox), or paste / upload cookies exported from any browser (for servers). |

In the desktop app, all configured rooms continue receiving live chat whether **Allow saving** is checked or not. That checkbox only controls whether chat from the room can be saved to Saved Chat; it does not stop reception, recording, or transcription.
In the desktop app, adding a YouTube scheduled stream URL monitors that exact stream first, then follows its channel again after the stream ends. If that stream and its channel are both configured, the channel card stays visible and represents the exact stream while both monitors remain active; use **Unload stream** to remove the exact-stream target and keep monitoring the channel. Bilibili monitor hover details include the observed gift revenue accumulated during the current app session; this is not a platform lifetime-revenue total.
In the desktop app, the Chat and Gifts / Super Chats panes sit side by side on wider windows. When the window is narrower than 1000 px, Gifts / Super Chats moves above Chat; the default narrow layout fits two gift entries and two Joins entries, giving the remaining height to Chat. The minimum window width is 720 px. Drag the splitters to adjust the feed proportions.
Desktop window size, feed splitter proportions, room selections, send targets and other app preferences are remembered. Active recording, scroll pause and playback are session-only and do not resume automatically.
The desktop app shows current process RAM and total RAM for its child processes in the status bar. Samples are logged every 10 seconds to `%LOCALAPPDATA%\StreamingDashboard\logs\memory.log` on Windows (or `~/.streaming-dashboard/logs/memory.log` on macOS/Linux); the **Memory log** button opens the log folder. Logs rotate at 5 MB, retaining three backups, and include chat/cache/TTS/transcription collection sizes to help identify what is growing. Diagnostics also report Qt widget and parent-owned task-bridge counts, pending task callbacks, submitted/completed/failed task totals, offline TTS queue lengths, desktop speech tasks awaiting completion, dropped speech/audio totals, avatar lookup counts, and cumulative feed-row render/reuse/remove counts. RSS changes are recorded both since startup and since the previous sample; Windows private memory is included when available. Startup entries identify the process, Python/Qt versions and TTS limits. Diagnostics version 3 optionally enables Python allocation tracing with `MEMORY_TRACE_ENABLED=true`: each memory sample includes traced bytes and tracer overhead, and a separate `python_allocation_sample` records the top 10 growing source locations once a minute. The first allocation sample is a baseline, and later samples compare against the previous allocation sample. Tracing begins when the desktop memory monitor starts, so earlier allocations and many native allocations are not tracked. Logs contain counts, sizes and (when tracing) source paths/line numbers, not chat text or credentials. No forced garbage collection is performed.

Bilibili diagnostics additionally report `bilibili_http_clients` and `bilibili_http_clients_closed_loops`. Clients on active listener loops are expected; clients on closed loops should remain at zero. Temporary Bilibili request loops close and remove their library-cached HTTP clients before exiting.

## Requirements

- Python 3.10+ (developed on 3.14)
- Windows, macOS or Linux (offline TTS voices depend on the OS)
- Optional live transcription: FFmpeg installed and available on `PATH`; faster-whisper and yt-dlp are installed with the requirements. The Whisper model is downloaded on first use.
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
| `TRANSLATION_PROVIDER` | Translation backend: `index`, `openai_compatible`, or `google`. The compatible API mode does not fall back to another provider. | `index` |
| `OPENAI_COMPATIBLE_TRANSLATE_API_BASE` | OpenAI-compatible chat API base URL (include `/v1`; local LM Studio example: `http://localhost:1234/v1`) | `http://localhost:1234/v1` |
| `OPENAI_COMPATIBLE_TRANSLATE_MODEL` | Exact model ID accepted by the configured API | `local-model` |
| `OPENAI_COMPATIBLE_TRANSLATE_API_KEY` | Optional API key; required by most hosted providers and usually blank for local servers | — |
| `INDEX_TRANSLATE_API_BASE` | Index-Translate OpenAI-compatible API base; set empty to disable it | `https://index-translate.bilibili.com/v1` |
| `INDEX_TRANSLATE_MODEL` | Index-Translate model | `Index-Translate-35B-A3B` |
| `OBS_HOST` | OBS WebSocket host | `localhost` |
| `OBS_PORT` | OBS WebSocket port | `4455` |
| `OBS_PASSWORD` | OBS WebSocket password | — |
| `OVERLAY_HOST` | Chat overlay listen address: `127.0.0.1` = this computer only, `0.0.0.0` = reachable from other machines | `127.0.0.1` |
| `OVERLAY_PORT` | Chat overlay port | `8502` |
| `OVERLAY_PUBLIC_URL` | Overlay address shown in the 🎬 OBS tab (e.g. `http://203.0.113.5:8502` or a reverse-proxy URL) | auto |
| `ANALYTICS_ENABLED` | `false` hides the Analytics page/tab and stops collecting viewer history, activity and hotspot data in both apps | `false` |
| `MEMORY_TRACE_ENABLED` | Opt-in desktop Python allocation tracing. Adds traced current/peak bytes and tracer overhead to memory samples, plus the top 10 allocation growth locations every 60 seconds. Adds CPU/RAM overhead; restart after changing and disable after diagnosis. | `false` |
| `TTS_USE_GTTS` | `true` = online gTTS, `false` = offline pyttsx3 | `false` |
| `TTS_QUEUE_LIMIT` | Offline normal chat/join queue limit; drops oldest waiting message when full | `20` |
| `TTS_PRIORITY_QUEUE_LIMIT` | Offline gifts / Super Chats queue limit; drops oldest waiting priority message when full | `50` |
| `TTS_TASK_LIMIT` | Desktop pending and running speech-generation task limit; skips incoming speech when full | `20` |
| `TTS_AUDIO_QUEUE_LIMIT` | Desktop online audio waiting for playback; drops oldest waiting audio when full | `20` |
| `SIMPLE_CHAT_POLL_INTERVAL` | Chat polling and feed refresh interval for `simple_app.py` and `simple_server_app.py`, in seconds; minimum `1` | `15` |
| `SIMPLE_STATUS_POLL_INTERVAL` | Live-status and current viewer-count refresh interval for simple monitors (continues while live), in seconds; minimum `1` | `60` |
| `CHAT_POLL_INTERVAL` | Chat refresh interval in seconds | `5` |
| `ROOM_STATUS_POLL_INTERVAL` | Live-status, title and viewer-count polling/cache interval in seconds for desktop status checks and browser status data, including YouTube channel monitoring. Minimum `1`; restart after changing. The main dashboard status and transcription panels no longer have background refresh timers; live alerts are checked when the app reruns. | `60` |
| `CHAT_TRANSLATION_DISPLAY_MODE` | `immediate` shows chat right away and adds translations when ready; `wait` shows each message when its translation is ready | `immediate` |
| `LOGIN_SECRET` | Key that encrypts each user's logins in their browser. Changing it logs everyone out | random, in `.login_secret` |

> ⚠️ `.env` and `.login_secret` contain secrets and are listed in `.gitignore`. Never commit or share them.
> TTS queue limits must be positive integers; restart after changing. Audio limits count clips, not bytes. Currently playing audio is not included in the waiting queue.
> For Streamlit Community Cloud, set `LOGIN_SECRET = "your-long-random-secret"` in the app's **Secrets** settings. Locally, you can put the same TOML entry in `.streamlit/secrets.toml`. The `.env`/environment value takes precedence; if neither is set, the app generates `.login_secret`.
>
> By default, translation tries Index-Translate first and automatically falls back to Google. Set `TRANSLATION_PROVIDER=openai_compatible` to use an OpenAI-compatible chat-completions API such as LM Studio or a hosted model provider. Configure its API base URL, exact model ID, and (when required) API key using `OPENAI_COMPATIBLE_TRANSLATE_API_BASE`, `OPENAI_COMPATIBLE_TRANSLATE_MODEL`, and `OPENAI_COMPATIBLE_TRANSLATE_API_KEY`. For hosted APIs, chat text leaves your machine and is sent only to that configured API; it is never sent to a fallback provider. Existing `LM_STUDIO_TRANSLATE_*` settings are still accepted if their generic equivalents are unset.

## Running

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Then open <http://localhost:8501>. To use it from a tablet on the same network, open `http://<PC-IP>:8501`.

### Desktop app (PySide6)

`desktop_app.py` is a native desktop version of the dashboard. It runs in its own window (no browser) and has the same features as `app.py`, plus chat saved automatically to disk and live recording for Bilibili and MissEvan. Install PySide6 in the same environment first:

```powershell
.\.venv\Scripts\python.exe -m pip install PySide6
.\.venv\Scripts\python.exe desktop_app.py
```

On Windows you can double-click [Start_Desktop.bat](Start_Desktop.bat) instead. It uses the project's `.venv` when available, otherwise Python on `PATH`.

- **Monitoring / Cookies**: add any number of YouTube channels, Bilibili rooms and MissEvan rooms. A YouTube channel monitor follows the channel's live page, including its nearest scheduled stream, and starts reading that stream's chat when it goes live. Each room shows as a card (3 per row) with live state, title and viewers, and can be switched on or off. Bilibili room cards distinguish the WebSocket room-audience count and public 大航海 total from the room-info popularity value; hover for the metrics. The live room-audience count appears after the Bilibili listener receives it. On first launch the rooms in `.env` (`YOUTUBE_CHANNEL`, `BILIBILI_ROOM_ID`, `MISSEVAN_ROOM_ID`) are added. Optional live notifications show the channel, stream title and preview image, with a button to open the live stream. Cookie import for sending chat is on the same tab. In the Cookies section, click **Find accounts** to discover YouTube accounts and channels available to the imported login, then choose which identity to use for chat.
- **Incremental desktop updates**: chat rows are retained while unchanged, preserving text selection as new messages arrive. Only new or changed rows (including translations, loaded images and membership updates) are rendered again; expired messages are removed. Join entries and monitoring labels update only when their displayed content changes. Polling does not rebuild the whole desktop UI.
- **Chat**: pick one monitored room per site to show; sending also goes to that room. Click a chat message or gift to pause that feed's auto-scroll while new messages continue to arrive; click the same message again to clear its selection and resume scrolling. Hover a message for its actions (Read, Block, Thank, …) and, when reading aids are enabled, pinyin / furigana for both the message and username. Chat, gifts / Super Chats and room joins have their own panels, with emotes, stickers and member badges as images and optional translation. **Skip speech** skips the currently playing item; **Clear all speech** stops playback and removes the queued speech.
- **Saved Chat**: regular chat and gifts / paid messages from every room with **Allow saving** enabled are appended directly to that room's archive file, including rooms not currently selected in Chat. Joins are not archived. Browse saved rooms by channel name with readable times, reload them later, or delete them. Files are kept under `%LOCALAPPDATA%\StreamingDashboard\chat_archive` on Windows.
- **Live recording**: enable **Monitor** for a YouTube, Bilibili or MissEvan room, then switch **Record** on to arm recording. If the room is offline, recording starts automatically when it goes live; switch **Record** off to disarm or stop immediately. Recording stops when the room goes offline. YouTube and MissEvan streams are saved as MKV; Bilibili streams are saved as FLV (modelled on [BililiveRecorder](https://github.com/BililiveRecorder/BililiveRecorder)). Choose the save folder under **Recording settings**. FFmpeg is required; YouTube recording resolves streams with yt-dlp. Bilibili can also save danmaku / Super Chats / gifts to an XML file.
- **Interface language**: choose English, Simplified Chinese, or Japanese from the menu bar beside **Theme**.
- **Transcription**: the Transcription tab supports YouTube, Bilibili and MissEvan. **Start transcription** prompts for an output file (`.txt` or `.lrc`), enables monitoring for the selected room and waits for it to go live; each recognized segment is automatically appended to the chosen file. Choose an existing file to append to it, or a new file for a separate transcript. LRC timestamps are continued after the last timestamp already in the file and advance per transcription chunk; a separately started recording may need a timing offset. Transcription remains armed for subsequent streams until **Stop transcription** is pressed or monitoring is disabled. Earlier sessions remain visible until **Clear all transcripts** is pressed, which clears only transcript text, not chat, gifts or output files. New transcript text continues to arrive and append after clearing.
- **OBS**: the same controls as `app.py` (connect, stream / recording, scenes and sources, OBS Text source). The Text source can include usernames (**Show usernames**). The **Chat Overlay** section starts the Browser Source overlay for the monitored room you pick per site; the URL uses the short site names (`yt`, `bili`, `me`) and leaves out unselected sites. Press **Start server and copy Browser Source URL** again after changing options to get an updated link.
- **Settings / TTS, Moderation, Transcription, Analytics**: as in `app.py`.
- **Message history limits**: the selected room for each site retains up to **Maximum chat messages per room** regular chat, gifts / paid messages, and joins in memory. Non-selected rooms' regular chat and paid messages are written directly to their Saved Chat files instead of accumulating in the feeds. Joins are not archived.
- **Theme** menu: light or dark.
- **Languages**: English / 简体中文 / 日本語, chosen in Settings.

The desktop app remembers its settings (rooms, selected rooms, TTS, translation, overlay, OBS and recording options, language, theme, last tab, window size) between runs. Settings live in the per-user application settings (the registry on Windows); `.env` is only read.

### Native Rust desktop app (feature port in progress)

Run `Start_Rust_Desktop.bat` on Windows, or build from `rust-desktop` with `cargo run`. The Rust app currently supports YouTube, Bilibili and MissEvan monitoring, room chat archives, received emote/sticker display, optional translation and local or online speech, and English / Simplified Chinese / Japanese UI.

The Chat page can combine one selected room from each platform and shows the selected rooms together; the same room selections determine send destinations. Chat reception continues for configured rooms even when **Allow saving** is off, while only enabled rooms append new messages to their archives. Three independently scrollable and resizable panes show regular chat, paid messages, and joins. Clicking a message pauses only that pane; clicking it again resumes scrolling. **Copy visible messages** copies the visible messages across all three panes, including room labels and translations where available. **Clear Chat window** hides the current selected-room messages from the live view without deleting archive data; later messages still appear. The composer includes a searchable local emoji/kaomoji picker. The **Accounts** page discovers YouTube channel identities and lets you choose which identity sends YouTube messages. Window size and position are saved and restored.

Bilibili danmaku, gifts, Super Chats and room-entry events are categorized; YouTube chat, Super Chats and membership events are categorized. Speech settings let you choose local Windows voices or optional Google online speech, whether to read paid messages, room joins, translated text and usernames, and an automatic, Chinese, English, Japanese or Korean voice language. **Google online** sends message text to Google to generate audio; local Windows speech remains the default. Speech speed and volume are adjustable; volume ranges from 0–100% and defaults to 100%. Emoji skipping is enabled by default and removes emoji/emote markers from mixed messages before speech. Paid events are prioritized ahead of queued regular chat without interrupting the utterance already playing. The waiting queue holds up to 20 regular chat/join messages and 50 paid messages; when one lane fills, the oldest waiting message in that lane is dropped, leaving active speech and the other lane untouched. Paid events and room joins use spoken announcements in the resolved voice language; gift descriptions are not translated. Right-click any message to copy it, including its translation when available, or read it aloud; an existing translation is preferred, otherwise the original text is read. Manual reading works even when automatic speech is disabled. **Skip speech** cancels the current utterance while keeping the remaining queue; **Clear all speech** stops playback and clears queued items. Right-click a paid event to mark or unmark it as thanked; thanked markers persist in settings across app restarts. Joins stay in a bounded live-only feed and are not archived. The **Filters** page supports case-insensitive regex allow/block patterns and blocked user IDs/names; allowed patterns override keyword blocks, while blocked users/names always remain blocked. URL blocking is enabled by default, matching the Python desktop filter defaults. Filters apply before messages are spoken or archived.

The **Analytics** page summarizes messages received since the Rust app started, including counts by platform, paid-event counts, known paid-value totals grouped by platform and original currency, top chatters, messages per minute, and activity hotspots (paid events weighted like five ordinary messages). MissEvan paid questions and gifts are recorded in diamonds and included in those totals. Hotspots can be exported as UTF-8 CSV or DaVinci Resolve EDL. The hotspot window is adjustable. Chat display history is adjustable from 10 to 200 messages per feed; this only limits the visible live feed and does not delete archive entries. Settings independently control overall interface text size and chat-feed font size.

The **Accounts** page accepts a pasted cookie header or JSON/Netscape browser-cookie export for YouTube, Bilibili, and MissEvan. The app verifies the login with the selected platform before saving. For YouTube, refresh the discovered channels and select the identity used for outgoing chat; the selected identity is saved with the encrypted login. Cookie data is encrypted with ChaCha20-Poly1305; its random encryption key is stored in the operating system credential store, not in the settings file. Saving or clearing a login restarts the live listeners so they use the updated credentials. The Rust app does not read browser profiles directly; export cookies from your browser and paste them into this page.

The **Settings** page can enable notifications when a monitored stream goes live. Notifications appear in the app with the channel, stream title, and a link to the platform’s official room or video page.

The **Chat** page can send a message to the selected rooms on YouTube, Bilibili, and MissEvan when their respective send checkboxes are enabled. A room must be live, and the operation reports a separate success or failure for each destination. Right-click a chat message to block that user locally; Bilibili messages also offer a confirmation-protected permanent room mute. Local blocks affect subsequent received messages; platform mutes require a logged-in Bilibili room owner or moderator.

The **OBS** page starts a local read-only Browser Source overlay on `http://127.0.0.1:8502/overlay`. Select enabled monitored rooms, choose the regular-chat and paid-event counts, optionally hide usernames or add custom text, and select off/automatic/pinyin/furigana ruby readings, then add the copied URL as an OBS Browser Source. The overlay displays trusted-platform chat emotes and stickers, annotates Chinese with pinyin or Japanese with furigana when enabled, separates paid events from regular chat, and is stopped when the app exits. The listener binds only to loopback.

The OBS page also supports opt-in OBS WebSocket v5 connection, stream and recording start/stop, scene switching, source visibility, status metrics, and sending the latest ten regular chat messages from the selected room to an OBS Text source. Connection settings use `OBS_HOST`, `OBS_PORT`, and `OBS_PASSWORD` (defaults: `localhost`, `4455`, and no password). Enable the WebSocket server in OBS and configure the same password before turning on **Connect to OBS**. Analytics includes paid-event counts and known paid-value totals grouped by platform and original currency.

Live recording can be armed per monitored room from the **Monitoring** page. Recording begins when the room is live, stops when it goes offline or monitoring is stopped, and retries transient stream/recorder failures. Choose the destination folder in **Settings**. YouTube recording uses `yt-dlp` (and FFmpeg for muxing); Bilibili and MissEvan recording use FFmpeg. Both tools must be installed and available on `PATH`. YouTube and MissEvan files use MKV containers; Bilibili files use FLV. Bilibili recording quality is selectable from Original through Smooth, and optional chat, paid-message and gift XML sidecars are saved beside recordings. Recordings are organized in per-room folders under the selected directory, or `%LOCALAPPDATA%\\StreamingDashboard\\recordings` by default on Windows.

The **Transcription** page can arm one enabled, monitored YouTube, Bilibili or MissEvan room, wait for it to go live, and save local Whisper output as `.txt` or `.lrc`. It uses FFmpeg to capture mono 16 kHz audio in short chunks and the `whisper` command from OpenAI Whisper for local inference; install OpenAI Whisper, FFmpeg, and `yt-dlp` (for YouTube audio resolution) and make them available on `PATH`. Whisper model files are downloaded by Whisper on first use. Transcript translation follows the existing **Translate chat** setting and target language. Stopping transcription or monitoring stops audio capture; clearing the page display leaves the saved transcript intact. OBS ruby readings are generated locally using the Rust pinyin and Japanese furigana libraries.

For a minimal monitor that automatically watches only the platforms configured in `.env` and shows live status, chat, and gifts, run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run simple_app.py
```

The simple monitor keeps translation and browser-based text-to-speech controls in its sidebar. Chat and gift cards show each user's avatar when available and fall back to an initial.
Status checks continue while all configured channels are offline, then stop after any channel goes live; chat and gift updates continue. Restart the monitor to resume status checks.

To retain the full chat and gift history in memory for as long as the Streamlit server is running, use:

```powershell
.\.venv\Scripts\python.exe -m streamlit run simple_server_app.py
```

After opening the app once, background polling continues if all browser sessions disconnect. Status checks stop after any configured channel goes live; chat collection for the live room continues. Restart the server to resume status checks. History is shared by browser sessions connected to that server and cleared when the server stops.

Configure its new-session defaults in `.env` (see `env.template`):

| Setting | Default | Purpose |
|---------|---------|---------|
| `SIMPLE_PAGE_LANGUAGE` | `ja` | UI and translation language: `en`, `zh`, or `ja` |
| `SIMPLE_TRANSLATION_ENABLED` | `true` | Enable chat translation |
| `SIMPLE_TTS_TRANSLATE` | `true` | Read translated chat when TTS is enabled |
| `SIMPLE_NOTIFY_LIVE` | `true` | Enable live notifications; browser permission is still required |

Restart after changing these settings. Existing sessions retain their sidebar selections. TTS itself remains off by default.

On Windows, after setup, double-click [Start_Simple_Monitor.bat](Start_Simple_Monitor.bat).
It uses the project's `.venv` when available, otherwise Python on `PATH`, and opens the browser.
The default port is 8501; set `SIMPLE_MONITOR_PORT` to use another port.

## Usage

### Reading chat (no login needed)

When a room is being monitored, Stream Monitoring shows a reminder to switch to **💬 Chat** in the top bar to view messages. The reminder disappears when all chat listeners stop.

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

MissEvan sending uses the imported account and requires an account eligible to chat in that room (the site's web client requires a bound phone number). If it still fails after binding, re-import fresh MissEvan cookies.

**Logins are per user.** Everyone who opens the dashboard has their own logins: your cookies are never used or shown for anyone else, and other users can't send chat as you. Your logins are stored only in your own browser as an encrypted cookie (the server keeps only the key, `LOGIN_SECRET` / `.login_secret`), so they survive a page refresh or server restart. Opening the dashboard in another browser or a private window starts logged out. Listeners you start use the login you had when you started them.

The 🔑 line in each **📡 Stream Monitoring** column shows the login state. Sending to MissEvan is disabled when its cookies have expired. Click **🚪 Clear login** under it to forget that site's cookies — they are removed from this session and this browser, and chat keeps working read-only.

If your Google login owns several YouTube channels (brand accounts), a **Send as** picker appears under the YouTube login line. Pick the channel your chat messages should come from. The choice is per user and remembered with your login. To use a different Google account, import that account's cookies in the 🍪 Cookies tab.

Sending to YouTube with browser cookies is unofficial (it works like youtube.com itself) and only works on streams with chat enabled.

### Chat display

- Use the **Chat text size** slider in the **Global settings** sidebar to resize all three feeds together (80–200%).
- Choose **Newest at top** or **Newest at bottom** in the sidebar to set the order of the live transcription, Chat and Gifts & Super Chats feeds.
- Chat automatically follows new messages at the selected end. Scrolling away pauses following so you can read history; return to the latest end or use the arrow button to resume.
- On wide screens, live transcription and Chat are on the left, with Gifts & Super Chats on the right. On narrow screens, Gifts & Super Chats moves between live transcription and Chat and can be collapsed with its heading.
- While scrolling Chat, the live-transcription preview stays pinned at the top. Chat rows show timestamps, hide membership text labels, de-emphasize usernames, and emphasize message text.
- In the desktop app, right-click a chat or gift to open its actions (Block, Read, Copy, and any room-specific actions) in a popup without changing the chat row height.
- On narrow screens, the separate Joins controls and feed are hidden; the latest arrival appears as one line in chat.
- The YouTube / Bilibili / MissEvan checkboxes above the feeds show or hide each site's messages.
- Only the Chat tab's chat/gift feed fragment has a background refresh timer (`CHAT_POLL_INTERVAL`, default 5 seconds). Status and transcription panels update on user interaction or a normal app rerun; live alerts are not checked in the background. Other tabs and controls are not re-run by the chat timer. *Max messages displayed* in the sidebar limits how many chat lines are kept on screen.
- *🗑️ Clear chat history* (sidebar) empties Chat and Joins but keeps Gifts & Super Chats, so nobody you still need to thank is lost.

### Gifts & Super Chats

- New gifts and Super Chats appear in the right-hand column. Click an item after thanking the viewer; it is greyed out with a ✅ *Thanked* badge. Click it again to undo.
- *Mark all thanked* marks everything currently pending.
- Each gift shows its known price; the feed header shows the received total, keeping different currencies separate.
- Thanked status is kept for the current browser session only.

### Translation

Chat is displayed without waiting for translation requests. Translated text is added on a later feed refresh when ready. Translated speech is also queued until its result is available, without delaying new chat; muting a feed or stopping TTS cancels its pending automatic speech.

Experimental live transcription is hidden by default. Set `TRANSCRIPTION_ENABLED=true` in `.env` and restart the dashboard to show its navigation entry and live preview. Set it to `false` to hide it again; chat translation remains available.

Choose a target language and turn on **Start translation** in the sidebar. While enabled, chat and transcription in a different language are translated into that target. The default provider tries Index-Translate first and uses Google Translate if it is unavailable or returns an invalid response. To use LM Studio or a hosted OpenAI-compatible provider, set `TRANSLATION_PROVIDER=openai_compatible` and configure `OPENAI_COMPATIBLE_TRANSLATE_API_BASE`, `OPENAI_COMPATIBLE_TRANSLATE_MODEL`, and, if required, `OPENAI_COMPATIBLE_TRANSLATE_API_KEY`. For hosted APIs, text is sent only to the configured service, with no other cloud fallback. Known streaming terms (for example *舰长*, *醒目留言*, *上舰* and *弹幕*) use built-in glossary overrides instead of machine-translated terms.

### Blocking users

Switch pages using the icon-and-label navigation in the top bar, alongside Deploy. On narrow screens, scroll the navigation horizontally. New sessions open Stream Monitoring by default; Transcription appears only when enabled. Settings remain in the initially hidden ☰ drawer, which overlays the page without resizing it. Press Escape to close it.

- Click 🚫 on a message to block its author. Their messages disappear from the dashboard and are filtered from then on; nothing is sent to YouTube / Bilibili / MissEvan.
- Blocks are per platform and saved in `chat_filters.json` (git-ignored), so they survive restarts. Select **🛡️ Filters** in the sidebar and unblock with ✕.
- The **🛡️ Filters** page also takes keywords, regex patterns and user names / IDs to block by hand.

### Text-to-speech

Chat header options are available whenever TTS is enabled, without Advanced mode. **Emoji** skips emoji and stickers; **Username** skips chat usernames; **Translated** reads translated chat. These on/off buttons are highlighted when enabled.

Each feed uses an icon-only speaker button to mute or unmute it, with a tooltip explaining the action. The emoji and username mute buttons also show a muted speaker when enabled and an audible speaker when disabled.

The Gifts & Super Chats translation option is also labeled **Translated**. Both translation buttons use solid green when enabled and a green outline when disabled.

Configure in the sidebar under **🔊 Text-to-Speech**: *Enable TTS*, *Language*, *Speed* and *Volume*. Use *▶ Test voice* to check. While TTS is on, each list (Gifts & Super Chats, Chat, Joins) has a **🔊 Read aloud / 🔇 Muted** button at the top that decides whether that list is read; the Chat list also has *Ignore emoji*, *Don't read usernames* (gifts and Super Chats still say who sent them) and *Read translated chat*; the Gifts & Super Chats list also has *Read translated Super Chats* (gift names are always read as they are). Gifts & Super Chats and Chat are read by default and Joins are not. Gifts & Super Chats are read first, in any language; for joins, only the newest few in each update are read.

To cut off a sensitive comment, use the buttons at the **top right above the feeds** (shown while TTS is on): **⏭ Skip** stops the current message and goes on to the next; **⏹ Stop TTS** stops it and drops everything still queued. New chat arriving afterwards is still read — turn off *Enable TTS* to silence it completely.

The engine (offline pyttsx3 or online gTTS) is chosen with `TTS_USE_GTTS` in `.env`.

**Speak on → This browser (device voices)** uses the browser's Web Speech API instead, so it works on Streamlit Cloud or a remote server (which have no speakers). Remote viewers always get browser voices. The page must stay open, and browsers only allow sound after you've clicked somewhere on the page once.

### OBS

In OBS: **Tools → WebSocket Server Settings**, enable the server and set the same port/password as in `.env`. Then open the **🎬 OBS** tab and turn on **Connect to OBS** (it's off by default, and while off the dashboard never contacts OBS). All OBS functions live in that one tab: stream/recording controls, scenes and sources appear once OBS is connected; if OBS isn't running it shows as disconnected and is re-checked every 15 seconds.

To show chat in OBS, add a **Text (GDI+)** source (or a FreeType text source), then enable **Send chat to OBS Text source** in the 🎬 OBS tab and select it. The source shows the last 10 regular chat messages, oldest first, without usernames or badges. When **Start translation** is enabled, each available translation appears beneath its original; turning it off removes translations on the next update. OBS chat output is opt-in and uses the configured WebSocket server; the separate Browser Source overlay preview does not update this Text source.

Alternatively, add an OBS **Browser Source** pointed at `http://localhost:8502/overlay` (not `:8501/overlay`). This page pins Super Chats, gifts and memberships (Bilibili SC and gifts, MissEvan paid questions and gifts, YouTube Super Chats/Stickers and memberships) to the top of the overlay and regular chat to the bottom, so busy chat never pushes paid events away (3 by default; set **Super Chats & gifts shown in OBS overlay** to 0 to hide), then the most recent regular chat messages (5 by default; change **Messages shown in OBS overlay** in the 🎬 OBS tab, 1–50), available translations only when **Start translation** is enabled, and the optional custom overlay message. In the 🎬 OBS tab, turn off **Show usernames in OBS overlay** to display chat text without usernames (on by default); the preview follows the same setting. Bilibili custom emotes (e.g. `[doge]`), sticker danmaku, YouTube channel custom emojis (member stamps such as `:_wave:`) and Super Sticker images appear as images in the dashboard, preview and Browser Source; the OBS Text source can only show the text code. Keep the dashboard open for updates. Port 8502 (`OVERLAY_PORT`) must be free; an error in the 🎬 OBS tab reports if the overlay server cannot start. The Browser Source works even when *Connect to OBS* is off. By default the overlay listens only on `127.0.0.1`; when the dashboard runs on a server, set `OVERLAY_HOST=0.0.0.0` (and open the port in the firewall) so OBS on your PC can load `http://<server>:8502/overlay` — the 🎬 OBS tab shows the exact URL. The overlay is read-only and only shows public chat. If several people use the same dashboard, give each one a different **Overlay channel** in the 🎬 OBS tab (adds `?ch=name` to the overlay URL); otherwise every open dashboard publishes to the same overlay and the last one wins.

To show only some sites on an overlay, pick them under **Sites on this overlay** in the 🎬 OBS tab, or add `site=` to the URL yourself: `/overlay?site=youtube`, `/overlay?site=bilibili,missevan`, `/overlay?ch=alice&site=bili` (short names `yt`, `bili`, `me` also work). Each URL gets its own full message counts, so you can add one Browser Source per site (e.g. YouTube chat on one side, Bilibili on the other). Without `site=` every site is shown.

To show **pinyin / furigana** above Chinese characters on the overlay (Super Chats, gifts, chat and their translations), pick *Auto*, *Pinyin* or *Furigana* under **Pinyin / furigana in OBS overlay** in the 🎬 OBS tab. On a standalone link, add `ruby=auto`, `ruby=pinyin` or `ruby=furigana`. It's off by default because viewers see it too and it makes each line taller.
To put Super Chats and chat on **different screens or scenes**, use the *Super Chats & gifts only* (`n=0`) and *Chat only* (`sc=0`) links at the top of the 🎬 OBS tab, one Browser Source each. When one part is set to 0, the other uses the whole Browser Source height.

**Streamlit Community Cloud / hosted dashboards:** only the dashboard port is public there, so `:8502/overlay` cannot be reached. The 🎬 OBS tab then shows dashboard links instead, e.g. `https://your-app.streamlit.app/?view=overlay&youtube=@channel&n=10&sc=5`. That page shows only the overlay and refreshes every 2 seconds. If the background is not transparent in OBS, add `body, .stApp { background: transparent !important; }` to the Browser Source's *Custom CSS*.

### 🔥 Hotspots for clipping

The 📊 Analytics tab finds moments where chat, gifts and Super Chats spike well above the stream's usual level (score = messages + 5 × gifts/SC per window, compared with the median). Each hotspot lists start/end times counted from the stream start (taken automatically from Stream Monitoring, or the first message, or a clock time you enter), its peak, and the hot phrases. Lead-in (20 s by default) moves clip starts earlier, because chat reacts after the moment happens. Download as:

Analytics also shows gift and Super Chat event counts and known revenue for YouTube, Bilibili and MissEvan separately. Different currencies (for example ¥ and 💎) are never converted or added together.

- **CSV** (opens in Excel), with times, counts and phrases;
- **Timestamps (.txt)**, `HH:MM:SS` lines you can paste into a video description or note;
- **Markers (.edl)** for DaVinci Resolve: put the recording on a timeline, then right-click the timeline in the Media Pool > *Timelines > Import > Timeline Markers from EDL*. *EDL timeline start* must match the timeline start (`01:00:00:00` by default, as in Resolve).

Only messages received while the dashboard page is open are counted.

## Project structure

```
app.py                 Streamlit UI (all tabs, sidebar, CSS)
desktop_app.py         Native PySide6 desktop app (same features, plus per-room chat archives and Bilibili / MissEvan recording)
Start_Desktop.bat      Windows launcher for desktop_app.py
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
  reading.py           Pinyin / furigana reading aids
  tts.py               Text-to-speech with priority queue
  obs_ctrl.py          OBS WebSocket v5 control
  bili_recorder.py     Bilibili live recorder (FLV + danmaku XML, BililiveRecorder-compatible)
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
