# EdgeOne Pages chat translation and transcription

This deployment uses EdgeOne Pages for the web UI, API, KV state, and transcript
Blob storage. A persistent Python collector keeps the existing platform chat
pollers and FFmpeg audio capture running; it sends chat and recognized text to
EdgeOne. Tencent TMT translates chat and transcripts, while Tencent realtime
ASR runs from the collector so recognition can be billed by audio duration.

## EdgeOne Pages setup

1. Deploy this repository as an EdgeOne Pages project. The static UI is
   `index.html`; `edge-functions/[[default]].js` provides the API routes.
2. Create a Pages KV binding named `CHAT_KV`.
3. Configure these Function environment variables:
   - `APP_ACCESS_TOKEN`: a random secret of at least 32 characters for the UI.
   - `COLLECTOR_TOKEN`: a different random secret of at least 32 characters.
   - `TENCENT_SECRET_ID` and `TENCENT_SECRET_KEY`: credentials for TMT.
   - `TENCENT_REGION`: Tencent API region, such as `ap-shanghai`.
   - `EDGEONE_TRANSCRIPTION_ENABLED`: set to `false` initially; set to `true`
     to permit transcription. The environment value is a global kill switch and
     overrides the UI setting.
4. The Blob SDK uses the store named `streaming-transcripts`. Installations are
   included in `package.json`; the function stores the latest 100 transcript
   records in `transcripts/recent.json` and keeps the UI index in KV.
5. Enable Tencent Machine Translation and configure its billing in the Tencent
   console. Keep both access tokens and Tencent credentials out of the
   repository and browser.

## Persistent collector setup

Run the collector on an always-on computer or server that can access the
platforms and has FFmpeg available on `PATH`. It uses this repository's Python
dependencies, including `websocket-client`.

Configure these environment variables on the collector:

- `EDGEONE_BASE_URL`: the deployed Pages HTTPS URL.
- `EDGEONE_COLLECTOR_TOKEN`: the same value configured on EdgeOne.
- `TENCENT_ASR_APP_ID`, `TENCENT_ASR_SECRET_ID`, and
  `TENCENT_ASR_SECRET_KEY`: credentials for Tencent realtime ASR. A restricted
  Tencent key is recommended.
- Existing source settings from `.env`: `YOUTUBE_CHANNEL`,
  `BILIBILI_ROOM_ID`, and/or `MISSEVAN_ROOM_ID`.

Start it with:

```powershell
.\.venv\Scripts\python.exe edgeone_collector.py
```

For another Python environment, install the project's `requirements.txt` first.
The collector polls all configured chat sources and selects transcription audio
in this order: Bilibili, YouTube, then MissEvan. It captures 16 kHz mono WAV
segments and streams PCM audio to Tencent's `16k_ja` or `16k_zh` realtime ASR
engine. Recognized Japanese is translated to Chinese; recognized Chinese is
translated to Japanese.
The collector checks the transcription switch every five seconds by default
(`EDGEONE_CONFIG_INTERVAL`); if it cannot reach the EdgeOne config endpoint, it
stops the current transcriber until configuration is reachable again.

## Using the UI

Open the Pages site and connect with `APP_ACCESS_TOKEN`. Select Japanese or
Chinese as the chat translation target. For transcription, select the spoken
audio language, turn on the UI switch, and ensure the EdgeOne environment
kill-switch is `true`. Setting that environment value to `false` immediately
disables transcription regardless of the stored UI setting.

## Quotas and cost

Do not assume the deployment is universally free. EdgeOne storage allowances
and Tencent free resources depend on the account and current product terms.
Tencent's current TMT pricing page does not list a general free quota for text
translation. Tencent ASR offers duration-based realtime recognition; confirm
the current free-hour quota and billing mode in the ASR console before enabling
the server switch. Realtime recognition connections are made for each captured
audio segment, approximately eight seconds by default.

The UI shows the latest 30 chat messages and transcript entries. KV retains a
bounded chat/transcript window; Blob retains the latest 100 transcript records.
Changing retention or segment length can change storage, API request, and ASR
usage.

## Checks

```powershell
node --test tests/test_edgeone_function.mjs
.\.venv\Scripts\python.exe -m unittest tests.test_edgeone_collector tests.test_tencent_realtime_asr tests.test_transcription tests.test_overlay_server
```

Tencent references:

- [EdgeOne Functions](https://pages.edgeone.ai/document/edge-functions)
- [Tencent realtime ASR V2](https://cloud.tencent.com/document/product/1093/48982)
- [Tencent ASR service and billing FAQ](https://cloud.tencent.com/document/product/1093/35693)
- [Tencent TMT pricing](https://cloud.tencent.com/document/product/551/35017)
