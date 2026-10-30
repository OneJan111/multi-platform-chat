# Tencent EdgeOne Functions for the chat overlay

EdgeOne Functions run JavaScript handlers using the Web `Request`/`Response` APIs;
they do not run this repository's Python/Streamlit application. This project uses
EdgeOne as a small HTTPS proxy while the existing Streamlit app and chat poller
continue running on a persistent Python host.

The function forwards only `GET /overlay` and `GET /overlay/data`, preserves the
query string, disables caching, and adds a bearer token when connecting to the
origin. The origin rejects overlay requests without that token.

## Deploy

1. Keep `simple_server_app.py` running on a persistent host with its existing
   platform configuration. Do not deploy the chat poller as an EdgeOne Function:
   function instances are not a persistent place for background polling or shared
   in-memory history.
2. Put this repository's `edge-functions/` directory at the root of an EdgeOne
   Makers project. Its `[[default]].js` handler is the catch-all route; it only
   accepts the two overlay paths listed above.
3. Configure these function environment variables in the EdgeOne project:
   - `OVERLAY_ORIGIN`: the HTTPS origin base URL, such as
     `https://overlay-origin.example.com` (no path, query, or credentials).
   - `OVERLAY_PROXY_TOKEN`: a randomly generated secret of at least 32 characters.
4. On the Python origin, set the same `OVERLAY_PROXY_TOKEN` and restart the app.
   The origin must be reachable over HTTPS from EdgeOne. A TLS reverse proxy can
   forward `/overlay` and `/overlay/data` to the app's local overlay listener
   (default port `8502`), preserving the `Authorization` request header.
5. Set the dashboard's `OVERLAY_PUBLIC_URL` to the EdgeOne public domain, for
   example `https://overlay.example.com`. The existing OBS link generator will
   then point Browser Sources at EdgeOne, including the live `/overlay/data`
   refreshes.

Keep the origin listener private (for example `OVERLAY_HOST=127.0.0.1` behind a
local TLS reverse proxy). If it must listen on a public interface, protect its
firewall and TLS reverse proxy; do not expose the overlay port without the token
check enabled.

## Local checks

Run the focused Python tests with the repository's configured environment:

```powershell
python -m unittest tests.test_overlay_server
```

Run the EdgeOne handler tests with Node.js:

```powershell
node --test tests/test_edgeone_function.mjs
```

The handler uses the EdgeOne Makers `EventContext` (`request` and `env`) and
standard Web APIs. See Tencent's [Edge Functions documentation](https://pages.edgeone.ai/document/edge-functions).
