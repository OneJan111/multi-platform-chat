"""
Streaming Dashboard – main Streamlit application.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import base64
import html as html_lib
import json
import os
import re
import time
import zlib
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Page config must be first ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Streaming Dashboard",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="auto",
)

from src import bilibili as bili
from src import browser_cookies as bc
from src import config as app_config
from src import emotes
from src import highlights as hl
from src import i18n
from src import missevan as me
from src import obs_ctrl as obs
from src import overlay_server
from src import reading
from src import tts as _tts
from src import translate as tr
from src import user_login
from src import youtube as yt
from src import youtube_web as ytw


def _fresh(mod):
    """Streamlit reruns app.py after a code update (e.g. a push to Streamlit Cloud) but keeps already-imported
    modules, so new code in src/ would be missing until the server restarts. Reload a module whose file
    changed since it was loaded (one loaded before this check existed is reloaded once). Only for modules
    whose module-level state is just caches."""
    import importlib
    try:
        mtime = os.path.getmtime(mod.__file__)
    except (OSError, TypeError, AttributeError):
        return mod
    if getattr(mod, "_loaded_mtime", None) != mtime:
        mod = importlib.reload(mod)
        mod._loaded_mtime = mtime
    return mod


# Refresh shared configuration before modules that import its constants; Streamlit can
# retain config while reloading modules after a code update.
app_config = _fresh(app_config)

# Dependencies first: youtube imports youtube_web; bilibili and youtube_web import emotes.
emotes = _fresh(emotes)
i18n = _fresh(i18n)
_tts = _fresh(_tts)
hl = _fresh(hl)
ytw = _fresh(ytw)
yt = _fresh(yt)
bili = _fresh(bili)
if not hasattr(overlay_server, "render_html"):  # stale copy from before a code update (state survives reload)
    import importlib
    overlay_server = importlib.reload(overlay_server)
from src.config import (
    BILIBILI_ROOM_ID, CHAT_POLL_INTERVAL, MISSEVAN_ROOM_ID, OBS_HOST, OBS_PORT, OVERLAY_HOST,
    OVERLAY_PUBLIC_URL, YOUTUBE_CHANNEL,
)
from src.filters import ChatFilter, make_default_filter
from src.tts import (
    LANGUAGES as TTS_LANGUAGES, format_announcement, format_join, format_message, is_emoji_only, is_gift, is_paid,
    matches_language, resolve_language, speak, speak_async, stop_speaking, strip_emoji,
)

# ──────────────────────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* Chat bubbles (--chat-scale is set by the sidebar "Text size" option) */
.chat-bubble {
    padding: 6px 10px;
    border-radius: 8px;
    margin-bottom: 4px;
    font-size: calc(0.88rem * var(--chat-scale, 1));
    line-height: 1.4;
    word-break: break-word;
}
/* Translucent tints and currentColor mixes so the chat reads well in both light and dark themes */
.chat-yt   { background: rgba(128,128,160,0.13); border-left: 3px solid #ff0000; }
.chat-bili { background: rgba(128,128,160,0.13); border-left: 3px solid #23ade5; }
.chat-me   { background: rgba(128,128,160,0.13); border-left: 3px solid #ff7a45; }
.chat-gift { background: rgba(156,39,176,0.16) !important; }
.chat-thanked { opacity: 0.45; }
/* Gifts / Super Chats: clicking the bubble toggles thanked (see _render_message) */
div[class*="st-key-thankbox_"] { position: relative; }
div[class*="st-key-thankbox_"] div[class*="st-key-thank_"] { position: absolute; inset: 0; z-index: 2; margin: 0; width: 100% !important; height: 100% !important; }
div[class*="st-key-thankbox_"] div[class*="st-key-thank_"] div,
div[class*="st-key-thankbox_"] div[class*="st-key-thank_"] button { width: 100% !important; height: 100% !important; max-width: none !important; }
div[class*="st-key-thankbox_"] div[class*="st-key-thank_"] button { opacity: 0; cursor: pointer; }
div[class*="st-key-thankbox_"]:hover .chat-bubble { filter: brightness(1.15); }
.chat-mod  { border-left-color: #ffd700 !important; }
.chat-sc   { background: rgba(255,120,0,0.17) !important; border-left-color: #ff6600 !important; }
.chat-superchat { background: rgba(230,0,0,0.16) !important; border-left-color: #ff0000 !important; }
.chat-translation {
    margin-top: 3px;
    padding-top: 3px;
    border-top: 1px dashed rgba(128,128,128,0.45);
    color: color-mix(in srgb, #2f8fe0 65%, currentColor);
    font-size: 0.95em;
}
.chat-translation.pending { color: color-mix(in srgb, currentColor 50%, transparent); font-style: italic; }
/* Message text sits on its own line under the badges / time / username */
.chat-text { margin-top: 2px; }
.chat-reading { line-height: 2.2; }
.chat-reading rt { font-size: 0.62em; color: color-mix(in srgb, #f08c00 70%, currentColor); letter-spacing: 0; }
.badge {
    display: inline-block;
    font-size: 0.77em;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 4px;
    margin-right: 4px;
    vertical-align: middle;
}
.site-icon { display: inline-block; vertical-align: middle; object-fit: contain; border-radius: 22%; }
h3 .site-icon { margin-right: 0.15em; position: relative; top: -0.08em; }
.badge-icon { margin-right: 4px; }
.badge-mod  { background:#ffd700; color:#000; }
.badge-owner{ background:#cc0000; color:#fff; }
.badge-sc   { background:#ff6600; color:#fff; }
.badge-member { background:#2e7d32; color:#fff; }
.badge-member-icon { height:1.3em; width:auto; vertical-align:middle; margin-right:2px; }
.yt-stamp-preview { max-width: 34rem; line-height: 2; word-break: break-word; }
.yt-stamp-preview img { height: 28px !important; vertical-align: middle; }
[class*="st-key-emote_grid_"] { gap: 4px !important; align-items: center; }
[class*="st-key-emote_grid_"] [data-testid="stMarkdownContainer"] p { margin: 0; }
[class*="st-key-emote_grid_"] [data-testid="stElementContainer"] { width: auto !important; }
[class*="st-key-emote_grid_"] button { padding: 1px 2px; min-height: 0; }
[class*="st-key-emote_grid_"] button img { height: 32px !important; max-height: 32px !important; width: auto; }
/* Emote pickers: wide enough to show a whole pack without scrolling */
[data-testid="stPopoverBody"]:has([class*="st-key-emote_grid_"], [class*="st-key-emo_bili_expand"]) {
    max-width: min(64rem, 92vw) !important; width: min(64rem, 92vw) !important; max-height: 88vh !important;
}
.status-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
}
.dot-live   { background: #00e676; box-shadow: 0 0 6px #00e676; }
.dot-offline{ background: #9e9e9e; }
.dot-error  { background: #ff5252; }
/* Invisible helper that reads the encrypted login cookie in the browser (see _restore_user_logins) */
.st-key-login_cookie_reader { display: none !important; }
/* Invisible helpers (scripts, style blocks) would each still take a gap in the page */
[data-testid="stElementContainer"]:has(> [data-testid="stHtml"] > script:only-child),
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) { display: none !important; }
/* ── Responsive layout (PC + tablet) ── */
[data-testid="stMainBlockContainer"] {
    /* Top padding must clear Streamlit's opaque fixed header (60px) or it covers the tab bar */
    padding: 4.25rem 1.5rem 1rem;
    max-width: 100%;
}
/* Send-to, site-emote and chat-filter rows always stay on one line (scroll sideways if the screen is too narrow) */
.st-key-send_targets, .st-key-emote_row, .st-key-show_row {
    flex-wrap: nowrap !important;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: none;
}
.st-key-send_targets > *, .st-key-emote_row > *, .st-key-show_row > * { flex-shrink: 0 !important; }
.st-key-send_targets label, .st-key-emote_row p, .st-key-show_row label { white-space: nowrap; }
/* The emote hint shrinks first, cut off with "…" */
.st-key-emote_row > [data-testid="stElementContainer"]:has([data-testid="stCaptionContainer"]) {
    flex: 1 1 0 !important;
    min-width: 0 !important;
}
.st-key-emote_row [data-testid="stCaptionContainer"] p { overflow: hidden; text-overflow: ellipsis; }
[data-testid="stMainBlockContainer"] hr { margin: 0.25rem 0; }
[data-testid="stMainBlockContainer"] [data-testid="stForm"] { padding: 0.5rem; }
/* Chat / gift feeds scroll inside a box that fits the screen height */
.st-key-chat_feed, .st-key-paid_feed {
    flex: none !important;
    height: calc(100dvh - 370px) !important;
    max-height: calc(100dvh - 370px) !important;
    min-height: 260px;
    overflow-y: auto !important;
    overflow-x: hidden;
    padding-right: 4px;
}
.join-feed {
    height: 130px;
    overflow-y: auto;
    font-size: calc(0.82rem * var(--chat-scale, 1));
    color: color-mix(in srgb, currentColor 70%, transparent);
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 6px;
    padding: 4px 8px;
}
.join-row { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.6; }
.join-row b { color: color-mix(in srgb, currentColor 85%, transparent); font-weight: 500; margin-left: 4px; }
.join-time { color: color-mix(in srgb, currentColor 55%, transparent); margin-right: 6px; font-size: 0.9em; }
.join-empty { color: color-mix(in srgb, currentColor 55%, transparent); font-style: italic; }
/* Portrait tablets: stack chat above gifts (must precede the row rules below) */
@media (max-width: 900px) {
    .st-key-chat_paid [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    .st-key-chat_paid [data-testid="stColumn"] {
        flex: 1 1 100% !important;
        width: 100% !important;
        min-width: 100% !important;
    }
    .st-key-chat_feed { height: 50dvh !important; max-height: 50dvh !important; }
    .st-key-paid_feed { height: 35dvh !important; max-height: 35dvh !important; }
    /* Feeds always stack here, so the 2-column / 1-column switch and its spacer do nothing */
    .st-key-feed_layout, .st-key-show_row > [data-testid="stElementContainer"]:has([data-testid="stSpace"]) { display: none !important; }
}
/* Message rows and the send box: keep text + buttons on one line at any width */
.st-key-chat_feed [data-testid="stHorizontalBlock"],
.st-key-paid_feed [data-testid="stHorizontalBlock"],
.st-key-send_box [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 4px;
}
.st-key-chat_feed [data-testid="stColumn"],
.st-key-paid_feed [data-testid="stColumn"],
.st-key-send_box [data-testid="stColumn"] {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 0 !important;
}
.st-key-chat_feed [data-testid="stColumn"]:first-child,
.st-key-paid_feed [data-testid="stColumn"]:first-child,
.st-key-send_box [data-testid="stColumn"]:first-child {
    flex: 1 1 auto !important;
}
.st-key-chat_feed button, .st-key-paid_feed button {
    padding: 0.15rem 0.45rem;
    min-height: 2.2rem;
}
@media (max-width: 1100px) {
    [data-testid="stMainBlockContainer"] { padding: 4.25rem 0.75rem 1rem; }
    .st-key-show_row { column-gap: 1rem !important; }
    .chat-bubble { font-size: calc(0.85rem * var(--chat-scale, 1)); padding: 5px 8px; }
}
/* Touch screens: bigger tap targets */
@media (hover: none) and (pointer: coarse) {
    .st-key-chat_feed button, .st-key-paid_feed button { min-height: 2.6rem; min-width: 2.6rem; }
}
/* ── Phones ── */
@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] { padding: 4.25rem 0.5rem 1rem; }
    [data-testid="stMainBlockContainer"] hr { margin: 0.1rem 0; }
    /* Control rows wrap here: keep the wrapped lines close together (their gap is meant for one line) */
    [data-testid="stMainBlockContainer"] [data-testid="stHorizontalBlock"] { row-gap: 0.4rem !important; }
    .st-key-send_targets, .st-key-show_row { column-gap: 0.5rem !important; }
    .st-key-send_targets p { font-size: 0.9rem; }
    .st-key-emote_row { column-gap: 0.4rem !important; }
    .st-key-emote_row [data-testid="stPopover"] button { padding: 0.25rem 0.5rem; }
    /* Feeds always stack on phones, so ◀ ▶ do nothing */
    [class*="st-key-move_"][class*="_side"] { display: none !important; }
    .st-key-emote_row [data-testid="stElementContainer"]:has([data-testid="stCaptionContainer"]) { display: none !important; }
    /* Feed headers: compact buttons so they take fewer lines */
    .st-key-chat_paid button { min-height: 2rem; padding: 0.1rem 0.5rem; font-size: 0.85rem; }
    .st-key-chat_paid [data-testid="stPopover"] button { min-height: 2rem; }
    /* Message rows: the bubble gets the width, the 🔊 / 🚫 buttons stay tappable */
    .st-key-chat_feed button, .st-key-paid_feed button {
        min-height: 2.4rem; min-width: 2.2rem; padding: 0.1rem 0.25rem; font-size: 0.95rem;
    }
    .st-key-chat_feed [data-testid="stHorizontalBlock"],
    .st-key-paid_feed [data-testid="stHorizontalBlock"] { gap: 2px !important; }
    .chat-bubble { padding: 4px 7px; }
    /* Feeds grow with their messages up to these heights, so an empty list doesn't take half the screen */
    .st-key-chat_feed { height: auto !important; min-height: 0; max-height: 60dvh !important; padding-bottom: 1rem; }
    .st-key-paid_feed { height: auto !important; min-height: 0; max-height: 40dvh !important; padding-bottom: 1rem; }
    .join-feed { height: auto; max-height: 110px; margin-bottom: 1rem; }
}
/* Small phones: drop the hover-only "?" hints so the send-to row fits */
@media (max-width: 360px) {
    .st-key-send_targets [data-testid="stTooltipIcon"] { display: none !important; }
}
/* Overlay preview */
.overlay-box {
    background: rgba(0,0,0,0.8);
    color: #fff;
    padding: 8px 12px;
    border-radius: 6px;
    font-family: monospace;
}
</style>
""",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# Session-state initialisation
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _shared_filter() -> ChatFilter:
    """One filter for every browser tab, so tabs can't overwrite each other's saved file."""
    return make_default_filter()


_TIMEZONES = sorted(tz for tz in available_timezones() if "/" in tz and not tz.startswith(("Etc/", "SystemV/")))


_FEEDS = ("paid", "chat", "join")  # chat-tab feeds in their default top-to-bottom / left-to-right order
_DEFAULT_FEED_SIDES = {"paid": "left", "chat": "right", "join": "left"}


def _init_state():
    defaults = {
        "chat_messages": [],          # unified list of all chat messages
        "yt_page_token": "",
        "bili_listener": None,
        "blocked_msgs": [],
        "paid_messages": [],          # gifts / Super Chats, kept apart so chat trimming can't drop them
        "join_messages": [],          # "entered the room" events, shown in their own feed
        "thanked_ids": set(),
        "tts_enabled": False,
        "tts_rate": 150,
        "tts_volume": 1.0,
        "tts_lang": "auto",
        "tts_translate": False,       # read translated chat
        "tts_translate_paid": False,  # read translated Super Chats
        "tts_skip_name": False,
        "tts_announce_paid": True,    # 🔊 on the Gifts & Super Chats feed
        "tts_read_chat": True,        # 🔊 on the Chat feed
        "tts_read_joins": False,      # 🔊 on the Joins feed
        "tts_skip_emoji": True,
        "translate_enabled": False,
        "translate_target": "en",
        "sc_reading": "auto",
        "show_enter_events": True,
        "obs_enabled": False,         # never contact OBS unless the streamer turns this on
        "obs_chat_enabled": False,
        "obs_chat_source": "",
        "obs_chat_last": None,
        "obs_chat_last_at": 0.0,
        "text_scale": {"chat": 100, "paid": 100, "join": 100},  # text size in % per feed
        "max_chat_display": 200,
        "feed_layout": "columns",     # "columns" = two side by side, "stack" = one column
        "feed_order": list(_FEEDS),
        "feed_sides": dict(_DEFAULT_FEED_SIDES),
        "selected_chat_id": "",
        "yt_chat_input": YOUTUBE_CHANNEL.strip(),
        "yt_watch_channel": "",       # channel URL being watched for its next live stream
        "yt_watch_info": {},          # last ytw.find_live_video() result
        "yt_watch_last": 0.0,
        "yt_live_video": "",          # video ID of the stream the watcher attached to
        "yt_chat_error": "",
        "bili_room_id": bili.parse_room_id(BILIBILI_ROOM_ID),
        "me_listener": None,
        "me_room_id": MISSEVAN_ROOM_ID,
        "overlay_text": "",
        "overlay_visible": False,
        "overlay_show_username": True,
        "overlay_count": 5,
        "overlay_sc_count": 3,
        # ?overlay=name keeps this dashboard's overlay channel across refreshes.
        "overlay_channel": overlay_server.clean_channel(st.query_params.get("overlay", "")),
        "overlay_sites": list(overlay_server.SITES),
        "live_notify": True,          # toast + desktop notification when a monitored site goes live
        "live_states": {},            # "site:room" -> last seen live flag
        "_live_alerts": [],           # desktop notifications waiting to be shown this run
        "tts_output": "server",       # "server" = this computer's speakers, "browser" = viewer's device voices
        "_tts_browser": [],           # lines waiting to be sent to the browser speech player
        "_tts_browser_cmd": "",       # "skip" / "stop" for the browser speech player
        "last_poll": 0.0,
        "viewer_history": [],         # list of {time, yt, bili}
        "activity_log": [],           # compact record of every message this session, for 🔥 hotspots
        "stream_starts": {},          # site -> epoch seconds the current stream went live
        # ?lang=zh in the URL lets a bookmark or refresh keep the chosen page language.
        "ui_lang": st.query_params.get("lang", "en") if st.query_params.get("lang") in i18n.UI_LANGUAGES else "en",
        # Chat timestamps: "" = server time; ?tz=Asia/Tokyo in the URL keeps a choice across refreshes.
        "chat_tz": st.query_params.get("tz", "") if st.query_params.get("tz", "") in _TIMEZONES else "",
        "show_yt": True,
        "show_bili": True,
        "show_me": True,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if not isinstance(st.session_state["text_scale"], dict):  # older session stored one number
        st.session_state["text_scale"] = dict(defaults["text_scale"])
    filt = _shared_filter()
    if not hasattr(filt, "is_blocked_user"):  # stale object from before a code reload
        _shared_filter.clear()
        filt = _shared_filter()
    st.session_state["filter"] = filt


_init_state()


_LOGIN_RESTORED = "_user_logins_restored"
_LOGIN_COOKIE_JS = """
export default function(component) {
    const jar = {};
    for (const part of document.cookie.split(";")) {
        const i = part.indexOf("=");
        if (i > 0) jar[part.slice(0, i).trim()] = part.slice(i + 1).trim();
    }
    const n = parseInt(jar["%(name)s_n"] || "0", 10);
    let token = "";
    if (n > 0 && n <= %(max)d) {
        const parts = [];
        for (let i = 0; i < n; i++) parts.push(jar["%(name)s_" + i] || "");
        if (parts.every(Boolean)) token = parts.join("");
    }
    component.setStateValue("token", token);
}
""" % {"name": user_login.COOKIE_NAME, "max": user_login.MAX_CHUNKS}


@st.cache_resource
def _login_cookie_reader():
    return st.components.v2.component("login_cookie_reader", js=_LOGIN_COOKIE_JS)


def _restore_user_logins() -> None:
    """New browser session: load this user's own logins from their encrypted browser cookie.

    The server normally sees the cookie in the request, but Streamlit Community Cloud's proxy strips
    app cookies, so when it is missing the browser reads it and sends it over on the next rerun."""
    if st.session_state.get(_LOGIN_RESTORED):
        return
    token = user_login.join_cookies(st.context.cookies)
    if not token:
        token = _login_cookie_reader()(
            key="login_cookie_reader", default={"token": None}, on_token_change=lambda: None,
        ).token
        if token is None:  # the browser hasn't answered yet
            return
    st.session_state[_LOGIN_RESTORED] = True
    logins = user_login.current()
    for k, v in user_login.decode(token).items():
        logins.setdefault(k, v)  # a login made before the cookie arrived wins


def _sync_login_cookie() -> None:
    """After a login changes, rewrite (or delete) the encrypted copy in this user's browser."""
    if user_login.take_changed():
        st.html(user_login.cookie_script(user_login.current()), unsafe_allow_javascript=True)


def _is_local_client() -> bool:
    """True when the dashboard is opened on the computer running it (not over the network/a proxy)."""
    headers = st.context.headers
    return st.context.ip_address is None and not (headers.get("X-Forwarded-For") or headers.get("X-Real-Ip"))


_restore_user_logins()
_sync_login_cookie()
try:
    overlay_server.ensure_started()  # standalone overlays (?youtube=…) work without opening the OBS tab
except OSError:
    pass  # reported in the 🎬 OBS tab


def _render_overlay_page() -> None:
    """?view=overlay: just the overlay, served through the dashboard's own address.

    Hosts like Streamlit Community Cloud only expose the Streamlit port, so OBS can't reach the
    separate overlay server (port 8502) there; this page shows the same thing on the normal URL."""
    query = {name: st.query_params.get_all(name) for name in st.query_params}
    st.markdown(
        "<style>"
        "header, footer, [data-testid='stHeader'], [data-testid='stToolbar'], [data-testid='stDecoration'],"
        "[data-testid='stStatusWidget'], [data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl']"
        "{display:none !important;}"
        "html, body, .stApp, [data-testid='stAppViewContainer'], [data-testid='stMain'], [data-testid='stBottom']"
        "{background:transparent !important;}"
        "[data-testid='stMainBlockContainer'], .block-container {padding:0 !important;}"
        "[data-stale='true'] {opacity:1 !important; transition:none !important;}"
        + overlay_server._PAGE_CSS + "</style>",
        unsafe_allow_html=True,
    )

    @st.fragment(run_every=2)
    def _live():
        try:
            server = overlay_server.ensure_started()
        except OSError:
            server = None
        st.markdown(overlay_server.render_html(overlay_server.overlay_data(query, server)),
                    unsafe_allow_html=True)

    _live()


if st.query_params.get("view") == "overlay":
    _render_overlay_page()
    st.stop()


def t(text: str, **kwargs) -> str:
    return i18n.translate(text, st.session_state["ui_lang"], **kwargs)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")
_ICON_FILES = {"youtube": "youtube.png", "bilibili": "bilibili.svg", "missevan": "missevan.png"}


@st.cache_resource
def _site_icon_uris() -> dict[str, str]:
    uris = {}
    for platform, name in _ICON_FILES.items():
        mime = "image/svg+xml" if name.endswith(".svg") else "image/png"
        with open(os.path.join(_ICON_DIR, name), "rb") as f:
            uris[platform] = f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"
    return uris


def _site_icon(platform: str, size: str = "1.1em", cls: str = "site-icon") -> str:
    name = _PLATFORM_NAMES.get(platform, platform)
    return (f'<img class="{cls}" src="{_site_icon_uris()[platform]}" alt="{name}" title="{name}" '
            f'style="width:{size};height:{size}">')


def _site_heading(platform: str) -> None:
    st.markdown(f"### {_site_icon(platform)} {_PLATFORM_NAMES[platform]}", unsafe_allow_html=True)


def _platform_badge(msg: dict) -> str:
    p = msg.get("platform", "")
    return _site_icon(p if p in _ICON_FILES else "bilibili", size="1.25em", cls="site-icon badge-icon")


def _role_badges(msg: dict) -> str:
    parts = []
    if msg.get("is_owner"):
        parts.append('<span class="badge badge-owner">OWNER</span>')
    if msg.get("is_moderator"):
        parts.append('<span class="badge badge-mod">MOD</span>')
    if msg.get("membership"):
        icon = emotes.safe_badge_url(msg.get("membership_icon"))
        mark = (
            f'<img class="badge-member-icon" src="{html_lib.escape(icon, quote=True)}" alt="" referrerpolicy="no-referrer">'
            if icon else "💎"
        )
        parts.append(f'<span class="badge badge-member">{mark} {html_lib.escape(msg["membership"])}</span>')
    return "".join(parts)


def _type_badge(msg: dict) -> str:
    t = msg.get("type", "")
    if "super" in t.lower() or "sc" in t.lower():
        return '<span class="badge badge-sc">SC</span>'
    return ""


def _bubble_class(msg: dict) -> str:
    base = {"youtube": "chat-yt", "missevan": "chat-me"}.get(msg.get("platform", ""), "chat-bili")
    if msg.get("is_moderator") or msg.get("is_owner"):
        base += " chat-mod"
    t = msg.get("type", "")
    if "super" in t.lower():
        base += " chat-superchat"
    elif t == "gift":
        base += " chat-gift"
    return base


def _chat_tz():
    """None = the server's local time; otherwise the ZoneInfo picked in the sidebar."""
    name = st.session_state.get("chat_tz", "")
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _fmt_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            return ts
    if dt.tzinfo is None:
        dt = dt.astimezone()  # naive times come from this server's clock
    return dt.astimezone(_chat_tz()).strftime("%H:%M:%S")


_RENDER_KEYS: dict[str, int] = {}  # app.py re-executes every run, so this resets per run


def _set_thanked(msg_ids: list[str], thanked: bool):
    ids: set = st.session_state["thanked_ids"]
    if thanked:
        ids.update(msg_ids)
    else:
        ids.difference_update(msg_ids)


def _author_html(name: str) -> str:
    """The escaped username with pinyin / furigana over its Chinese characters (the 注音 setting)."""
    annotated = reading.annotate_html(name or "", st.session_state["sc_reading"])
    if not annotated:
        return html_lib.escape(name or "")
    return f'<span class="chat-reading">{annotated.replace("<br>", " · ")}</span>'


def _render_message(msg: dict, key_prefix: str = "", thank: bool = False):
    # Widget keys must be unique per run even if a platform sends the same message id twice.
    base_key = f"{key_prefix}_{msg['id']}"
    n = _RENDER_KEYS.get(base_key, 0)
    _RENDER_KEYS[base_key] = n + 1
    wkey = base_key if n == 0 else f"{base_key}_{n}"
    thanked = thank and msg["id"] in st.session_state["thanked_ids"]
    bubble = _bubble_class(msg) + (" chat-thanked" if thanked else "")
    badges = _platform_badge(msg) + _role_badges(msg) + _type_badge(msg)
    if thanked:
        badges += f'<span class="badge badge-owner">✅ {t("Thanked")}</span>'
    ts = _fmt_time(msg.get("timestamp", ""))
    author = _author_html(msg.get("author", ""))
    text = msg.get("text", "")
    text_html = emotes.text_to_html(text, msg.get("emotes"), msg.get("sticker_url", ""), msg.get("sticker_caption", False))
    # Super Chats and gifts get pinyin / furigana so their text (and gift names) can be read aloud.
    reading_aid = "super" in msg.get("type", "").lower() or msg.get("type") == "gift"
    if reading_aid:
        annotated = reading.annotate_html(text, st.session_state["sc_reading"])
        if annotated:
            text_html = f'<span class="chat-reading">{annotated}</span>'
    translation_html = ""
    if st.session_state["translate_enabled"] and text and msg.get("type") != "enter":
        target = st.session_state["translate_target"]
        translated = tr.get_translation(text, target)
        if translated is None:
            translation_html = f'<div class="chat-translation pending">🌐 {t("translating…")}</div>'
        elif translated:
            # The translation's language is known: furigana for Japanese (all messages), pinyin for
            # Chinese (Super Chats and gifts, like their original text); none when 注音 is off.
            rd_mode = ""
            if st.session_state["sc_reading"] != "off":
                if target.startswith("ja"):
                    rd_mode = "hiragana"
                elif target.startswith("zh") and reading_aid:
                    rd_mode = "pinyin"
            annotated = reading.annotate_html(translated, rd_mode) if rd_mode else ""
            body = f'<span class="chat-reading">{annotated}</span>' if annotated else html_lib.escape(translated)
            translation_html = f'<div class="chat-translation">🌐 {body}</div>'
    html = (
        f'<div class="chat-bubble {bubble}">'
        f'{badges}'
        f'<span style="color:color-mix(in srgb, currentColor 60%, transparent);font-size:0.85em;">[{ts}]</span> '
        f'<strong>{author}</strong>'
        f'<div class="chat-text">{text_html}</div>'
        f"{translation_html}"
        f"</div>"
    )
    if thank:
        col1, col2, col3 = st.columns([9, 1, 1])
        with col1:
            # The whole bubble is the toggle: an invisible button stretched over the keyed container.
            with st.container(key=f"thankbox_{wkey}"):
                st.markdown(html, unsafe_allow_html=True)
                st.button(
                    "↩️" if thanked else "🙏", key=f"thank_{wkey}",
                    help=t("Undo: mark as not thanked yet") if thanked else t("Mark as thanked"),
                    on_click=_set_thanked, args=([msg["id"]], not thanked),
                )
    else:
        col1, col2, col3 = st.columns([9, 1, 1])
        with col1:
            st.markdown(html, unsafe_allow_html=True)
    with col2:
        if text and msg.get("type") != "enter":
            st.button(
                "🔊", key=f"tts_{wkey}", help=t("Read this message aloud"),
                on_click=_replay_message, args=(msg,),
            )
    with col3:
        st.button(
            "🚫", key=f"ban_{wkey}", help=t("Block this user (hides their messages; saved permanently)"),
            on_click=_block_user, args=(msg,),
        )


def _block_user(msg: dict):
    """Add the author to the saved blocked-users filter and drop their messages already on screen."""
    filt: ChatFilter = st.session_state["filter"]
    platform, author_id, author = msg.get("platform", ""), msg.get("author_id", ""), msg.get("author", "")
    if author_id and author_id != "0":  # Bilibili sends uid 0 when it hides the viewer's ID
        filt.block_user(author_id, name=author, platform=platform)
    else:
        filt.block_name(author)
    names = set(filt.blocked_names)
    for key in ("chat_messages", "paid_messages", "join_messages"):
        st.session_state[key] = [
            m for m in st.session_state[key]
            if not (filt.is_blocked_user(m) or m.get("author", "").lower() in names)
        ]
    st.toast(t("Blocked {author} — see the 🛡️ Filters tab to unblock", author=author))


_PLATFORM_NAMES = {"youtube": "YouTube", "bilibili": "Bilibili", "missevan": "MissEvan"}


def _browser_tts() -> bool:
    """Speak in the viewer's browser (device voices) instead of on the computer running the app."""
    return st.session_state["tts_output"] == "browser" or not _is_local_client()


def _tts_say(text: str, lang: str = "auto", priority: bool = False) -> None:
    """Queue speech: browser player (sent at the end of this run) or the server's pyttsx3 worker."""
    if not _browser_tts():
        speak_async(text, rate=st.session_state["tts_rate"], volume=st.session_state["tts_volume"],
                    lang=lang, priority=priority)
        return
    code = resolve_language(lang, text)
    queue = st.session_state["_tts_browser"]
    queue.append({
        "id": f"{time.time_ns()}-{len(queue)}",
        "text": text,
        "lang": TTS_LANGUAGES[code][2],
        "rate": round(st.session_state["tts_rate"] / 150, 2),
        "volume": st.session_state["tts_volume"],
        "priority": priority,
    })
    del queue[:-60]


def _play_tts(text: str, lang: str):
    """Speak now; in gTTS mode keep the clip so the browser player survives auto-refresh."""
    if _browser_tts():
        _tts_say(text, lang, priority=True)
        return
    audio = speak(
        text,
        rate=st.session_state["tts_rate"],
        volume=st.session_state["tts_volume"],
        lang=lang,
    )
    if audio:
        st.session_state["_tts_audio"] = audio


def _stop_tts(clear: bool):
    """Cut off the message being read (e.g. a sensitive comment); clear=True also drops the queue."""
    if _browser_tts():
        st.session_state["_tts_browser"] = []
        st.session_state["_tts_browser_cmd"] = "stop" if clear else "skip"
        st.toast(t("⏹ TTS stopped · queue cleared") if clear else t("⏭ Skipped the current message"))
        return
    dropped = stop_speaking(clear=clear)
    st.session_state.pop("_tts_audio", None)  # gTTS: removing the player stops browser playback
    if clear:
        st.toast(t("⏹ TTS stopped · {n} queued message(s) dropped", n=dropped))
    else:
        st.toast(t("⏭ Skipped the current message"))


_TEXT_SIZES = [80, 90, 100, 115, 130, 150, 175, 200]


def _change_text_size(feed: str, step: int):
    scales = st.session_state["text_scale"]
    i = _TEXT_SIZES.index(scales[feed]) if scales[feed] in _TEXT_SIZES else _TEXT_SIZES.index(100)
    scales[feed] = _TEXT_SIZES[max(0, min(len(_TEXT_SIZES) - 1, i + step))]


def _text_size_buttons(container, feed: str):
    """A− / A+ for a feed's header tools."""
    size = st.session_state["text_scale"][feed]
    container.button(
        "A−", key=f"size_{feed}_dec", type="tertiary", disabled=size <= _TEXT_SIZES[0],
        on_click=_change_text_size, args=(feed, -1), help=t("Smaller text ({p}%)", p=size),
    )
    container.button(
        "A+", key=f"size_{feed}_inc", type="tertiary", disabled=size >= _TEXT_SIZES[-1],
        on_click=_change_text_size, args=(feed, 1), help=t("Bigger text ({p}%)", p=size),
    )


_FEEDS = ("paid", "chat", "join")


def _feed_layout_state() -> tuple[list[str], dict[str, str], bool]:
    """(feed order, left/right column per feed, one-column mode), repaired if session state is stale."""
    order = st.session_state.get("feed_order")
    if not isinstance(order, list) or sorted(order) != sorted(_FEEDS):
        order = st.session_state["feed_order"] = list(_FEEDS)
    sides = st.session_state.get("feed_sides")
    if not isinstance(sides, dict) or any(sides.get(f) not in ("left", "right") for f in _FEEDS):
        sides = st.session_state["feed_sides"] = dict(_DEFAULT_FEED_SIDES)
    return order, sides, st.session_state.get("feed_layout") == "stack"


def _feed_column(feed: str) -> list[str]:
    """Feeds shown in the same column as `feed`, top to bottom."""
    order, sides, stacked = _feed_layout_state()
    return order if stacked else [f for f in order if sides[f] == sides[feed]]


def _move_feed(feed: str, step: int):
    """Swap a feed with its neighbour above (-1) or below (+1) in the same column."""
    column = _feed_column(feed)
    i = column.index(feed) + step
    if 0 <= i < len(column):
        order = st.session_state["feed_order"]
        a, b = order.index(feed), order.index(column[i])
        order[a], order[b] = order[b], order[a]


def _switch_feed_side(feed: str):
    sides = st.session_state["feed_sides"]
    sides[feed] = "right" if sides[feed] == "left" else "left"


def _feed_move_buttons(container, feed: str):
    """▲ ▼ to reorder within a column, ◀ / ▶ to move to the other column (two-column layout only)."""
    _, sides, stacked = _feed_layout_state()
    column = _feed_column(feed)
    i = column.index(feed)
    container.button("▲", key=f"move_{feed}_up", type="tertiary", disabled=i == 0,
                     on_click=_move_feed, args=(feed, -1), help=t("Move up"))
    container.button("▼", key=f"move_{feed}_down", type="tertiary", disabled=i == len(column) - 1,
                     on_click=_move_feed, args=(feed, 1), help=t("Move down"))
    if not stacked:
        left = sides[feed] == "left"
        container.button("▶" if left else "◀", key=f"move_{feed}_side", type="tertiary",
                         on_click=_switch_feed_side, args=(feed,),
                         help=t("Move to the right column") if left else t("Move to the left column"))


def _feed_tools(head, feed: str, text_size: bool = True):
    """Right end of a feed's header: A− / A+ and the position buttons, kept together if the header wraps."""
    head.space("stretch")
    tools = head.container(horizontal=True, vertical_alignment="center", width="content", gap="small")
    if text_size:
        _text_size_buttons(tools, feed)
    _feed_move_buttons(tools, feed)


def _feed_height_css(columns: list[list[str]], stacked: bool, joins_shown: bool) -> str:
    """Fit the scrolling chat / gift boxes to the screen height, sharing it with the other feeds in their column."""
    if stacked:  # narrower screens use the main stylesheet's heights
        return ("@media (min-width: 641px) {"
                ".st-key-chat_feed { height: 50dvh !important; max-height: 50dvh !important; }"
                ".st-key-paid_feed { height: 35dvh !important; max-height: 35dvh !important; }}")
    rules = []
    for column in columns:
        big = [f for f in column if f != "join"]
        if not big:
            continue
        reserved = 370 + 60 * (len(big) - 1)
        if "paid" in column:
            reserved += 50  # gifts header + "Mark all" button may wrap to two lines
        if "join" in column:
            reserved += 190 if joins_shown else 50
        height = f"calc((100dvh - {reserved}px) / {len(big)})"
        rules += [f".st-key-{f}_feed {{ height: {height} !important; max-height: {height} !important; "
                  f"min-height: 180px; }}" for f in big]
    # Narrow screens stack the columns; the fixed heights in the main stylesheet apply there.
    return "@media (min-width: 901px) {" + "".join(rules) + "}"


def _sync_obs_chat():
    if not st.session_state["obs_enabled"] or not st.session_state["obs_chat_enabled"]:
        st.session_state["obs_chat_last"] = None
        return
    source = st.session_state["obs_chat_source"]
    if not source:
        return
    chat = st.session_state["chat_messages"]
    if st.session_state["translate_enabled"]:
        tr.prefetch(
            [m["text"] for m in obs.recent_chat(chat)],
            st.session_state["translate_target"],
        )
    text = obs.format_chat_text(
        chat, st.session_state["translate_enabled"], st.session_state["translate_target"], tr.get_translation,
    )
    last = st.session_state["obs_chat_last"]
    now = time.monotonic()
    if last == (source, text) and now - st.session_state["obs_chat_last_at"] < 30:
        return
    try:
        obs.set_text_source(source, text)
    except Exception as exc:
        st.warning(t("Couldn't update OBS chat text: {err}", err=str(exc)))
        return
    st.session_state["obs_chat_last"] = (source, text)
    st.session_state["obs_chat_last_at"] = now


def _tts_stop_buttons(container, prefix: str):
    container.button(
        t("⏭ Skip"), key=f"{prefix}_tts_skip", on_click=_stop_tts, args=(False,),
        help=t("Stop reading the current message and go on to the next one."),
    )
    container.button(
        t("⏹ Stop TTS"), key=f"{prefix}_tts_stop", on_click=_stop_tts, args=(True,), type="primary",
        help=t("Stop reading now and drop all queued messages. New chat is still read."),
    )


_TTS_MAX_JOINS = 3  # joins read per poll


def _feed_tts_button(container, state_key: str) -> None:
    """🔊/🔇 on a feed header: whether text-to-speech reads that feed (shown while TTS is on)."""
    if not st.session_state["tts_enabled"]:
        return
    on = st.session_state[state_key]
    container.button(
        t("🔊 Read aloud") if on else t("🔇 Muted"), key=f"{state_key}_btn",
        type="secondary" if on else "tertiary",
        help=t("Text-to-speech reads this list. Click to mute it.") if on
        else t("Text-to-speech doesn't read this list. Click to read it aloud."),
        on_click=lambda: st.session_state.update({state_key: not st.session_state[state_key]}),
    )


def _tts_option(container, state_key: str, label: str, help_text: str) -> None:
    """Checkbox-style on/off button for a TTS option, kept in session_state[state_key]."""
    on = st.session_state[state_key]
    container.button(
        label, key=f"{state_key}_btn",
        icon=":material/check_box:" if on else ":material/check_box_outline_blank:",
        type="secondary" if on else "tertiary",
        help=help_text,
        on_click=lambda: st.session_state.update({state_key: not st.session_state[state_key]}),
    )


def _tts_translation_usable() -> bool:
    """Translations can be read when the TTS language is auto-detect or the same as "Translate to"."""
    tts_lang = st.session_state["tts_lang"]
    return tts_lang == "auto" or tts_lang == st.session_state["translate_target"].split("-")[0]


def _tts_translating(paid: bool = False) -> bool:
    """Whether chat (or, with `paid`, Super Chats) is read translated."""
    return st.session_state["tts_translate_paid" if paid else "tts_translate"] and _tts_translation_usable()


def _reads_translated(msg: dict) -> bool:
    """Whether this message is read translated; gift names are product names, so gifts never are."""
    return msg.get("type") != "gift" and _tts_translating(is_paid(msg))


def _speech_for(text: str, src_lang: str, translate: bool) -> tuple[str, str]:
    """(text to speak, voice language). With `translate`, speak the translation."""
    if not translate:
        return text, src_lang
    translated = tr.get_translation(text, st.session_state["translate_target"])
    if translated:
        # Auto-detect: use the "Translate to" language's voice for the translated text.
        return translated, st.session_state["translate_target"].split("-")[0]
    # Already in the target language, or the translation failed / isn't ready: read the original.
    return text, "auto"


def _chat_line(author: str, text: str, lang: str) -> str:
    """Spoken line for a regular chat message, with or without the username."""
    if st.session_state["tts_skip_name"]:
        return text
    return format_message(author, text, lang)


def _replay_message(msg: dict):
    text = msg.get("text", "")
    if st.session_state["tts_skip_emoji"]:
        text = strip_emoji(text, msg.get("platform", "")) or text
    lang = st.session_state["tts_lang"]
    translate = _reads_translated(msg)
    if not matches_language(text, lang) and not translate:
        lang = "auto"  # manual replay reads any message, in its own language
    if translate:
        tr.prefetch([text], st.session_state["translate_target"], wait=3.0)
        text, lang = _speech_for(text, lang, True)
    elif msg.get("type") == "gift":
        lang = "auto"
    if is_paid(msg):
        _play_tts(format_announcement(msg.get("type", ""), msg.get("author", ""), text, lang), lang)
    else:
        _play_tts(_chat_line(msg.get("author", ""), text, lang), lang)


def _poll_chat():
    """Pull new messages from both platforms and append to session state."""
    now = time.time()
    if now - st.session_state["last_poll"] < CHAT_POLL_INTERVAL:
        return
    st.session_state["last_poll"] = now

    new_msgs: list[dict] = []
    history_ids: set = set()

    # YouTube
    _check_watched_channel()
    chat_id = st.session_state.get("selected_chat_id", "")
    if chat_id:
        first_fetch = not st.session_state["yt_page_token"]
        msgs, next_tok, _ = yt.get_chat_messages(
            chat_id, st.session_state["yt_page_token"]
        )
        st.session_state["yt_page_token"] = next_tok
        new_msgs.extend(msgs)
        if first_fetch:  # backlog of earlier chat — show it, but don't read it aloud
            history_ids = {m["id"] for m in msgs}

    # Bilibili
    listener: Optional[bili.DanmakuListener] = st.session_state.get("bili_listener")
    if listener:
        bili_msgs = listener.pop_messages()
        new_msgs.extend(bili_msgs)

    # MissEvan
    me_listener: Optional[me.MissEvanListener] = st.session_state.get("me_listener")
    if me_listener:
        new_msgs.extend(me_listener.pop_messages())

    if not new_msgs:
        return

    filt: ChatFilter = st.session_state["filter"]
    allowed, blocked = filt.filter_messages(new_msgs)

    # TTS: each feed's 🔊 button decides whether its messages are read.
    if st.session_state["tts_enabled"]:
        skip_emoji = st.session_state["tts_skip_emoji"]
        announce_paid = st.session_state["tts_announce_paid"]
        read_chat = st.session_state["tts_read_chat"]
        translating = _tts_translating()
        to_speak: list[tuple[dict, str]] = []
        joins: list[dict] = []
        for m in allowed:
            if m["id"] in history_ids or m.get("history"):
                continue
            if m.get("type") == "enter":
                if st.session_state["tts_read_joins"] and m.get("author"):
                    joins.append(m)
                continue
            paid = announce_paid and is_paid(m)
            if paid or (read_chat and m.get("type") in ("textMessageEvent", "danmaku")):
                text = m["text"]
                if skip_emoji:
                    if is_emoji_only(m) and not paid:
                        continue
                    text = strip_emoji(text, m.get("platform", "")) or text
                # Paid events are always announced, whatever language they're in. When reading
                # translations, every message ends up in the TTS language, so don't filter by source.
                if not paid and not translating and not matches_language(text, st.session_state["tts_lang"]):
                    continue
                to_speak.append((m, text))
        to_translate = [text for m, text in to_speak if _reads_translated(m)]
        if to_translate:
            tr.prefetch(to_translate, st.session_state["translate_target"], wait=3.0)
        # Paid events first, so a burst of chat in the same poll can't delay them.
        to_speak.sort(key=lambda item: not (announce_paid and is_paid(item[0])))
        for m, text in to_speak:
            paid = announce_paid and is_paid(m)
            if m.get("type") == "gift":
                lang = "auto"  # gift names are product names; translating them gives nonsense
            else:
                text, lang = _speech_for(text, st.session_state["tts_lang"], _reads_translated(m))
            _tts_say(
                format_announcement(m["type"], m["author"], text, lang) if paid
                else _chat_line(m["author"], text, lang),
                lang=lang,
                priority=paid,
            )
        # Joins come last; a busy room can have many per poll, so only the newest few are read.
        tts_lang = st.session_state["tts_lang"]
        for m in joins[-_TTS_MAX_JOINS:]:
            # Auto-detecting a username (often Latin letters/digits) would pick English for a Chinese stream.
            lang = tts_lang if tts_lang != "auto" else ("zh" if m.get("platform") in ("bilibili", "missevan") else "auto")
            _tts_say(format_join(m["author"], lang), lang=lang)

    # Update history; join events go to their own feed, never into chat
    _now = time.time()
    _log = st.session_state["activity_log"]
    for m in allowed:
        if m.get("type") != "enter":
            _log.append(hl.log_entry(m, is_paid(m) or is_gift(m), _now))
        if is_paid(m) or is_gift(m):
            st.session_state["paid_messages"].append(m)
        if m.get("type") == "enter":
            st.session_state["join_messages"].append(m)
            continue
        st.session_state["chat_messages"].append(m)
    if len(st.session_state["paid_messages"]) > 1000:
        st.session_state["paid_messages"] = st.session_state["paid_messages"][-1000:]
    if len(st.session_state["join_messages"]) > 500:
        st.session_state["join_messages"] = st.session_state["join_messages"][-300:]
    if len(_log) > hl.MAX_LOG:
        st.session_state["activity_log"] = _log[-hl.MAX_LOG:]

    st.session_state["blocked_msgs"].extend(blocked)

    # Cap history
    max_disp = st.session_state["max_chat_display"]
    if len(st.session_state["chat_messages"]) > max_disp * 2:
        st.session_state["chat_messages"] = st.session_state["chat_messages"][-max_disp:]


def _note_stream_start(site: str, value: str, zone: str = "") -> None:
    """Remember when `site`'s stream went live (hotspot clip times are measured from it).
    `zone` is the time zone of naive date strings (Bilibili reports Beijing time)."""
    value = (value or "").strip()
    if not value or value.startswith("0000") or value == "0":
        return
    if value.isdigit():
        st.session_state["stream_starts"][site] = float(value)
        return
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(zone)) if zone else dt.astimezone()
    st.session_state["stream_starts"][site] = dt.timestamp()


def _record_viewer_snapshot(yt_viewers: int, bili_viewers: int, me_viewers: int = 0):
    now = datetime.now().strftime("%H:%M:%S")
    st.session_state["viewer_history"].append(
        {"time": now, "YouTube": yt_viewers, "Bilibili": bili_viewers, "MissEvan": me_viewers}
    )
    # Keep last 60 snapshots
    if len(st.session_state["viewer_history"]) > 60:
        st.session_state["viewer_history"] = st.session_state["viewer_history"][-60:]


@st.cache_data(ttl=60, show_spinner=False)
def _cached_video_status(video_id: str) -> dict:
    # Cached because the app reruns every few seconds and each lookup costs API quota.
    return yt.get_video_live_status(video_id)


YT_WATCH_INTERVAL = 60  # seconds between checks of a watched channel


def _yt_video_id() -> str:
    """Video ID of the YouTube stream in use: the watched channel's live stream, or the one typed in."""
    if st.session_state["yt_watch_channel"]:
        return st.session_state["yt_live_video"]
    return yt.extract_video_id(st.session_state["yt_chat_input"])


def _stop_yt_listener():
    st.session_state["selected_chat_id"] = ""
    st.session_state["yt_page_token"] = ""
    st.session_state["yt_live_video"] = ""


def _alert_live(msg: str) -> None:
    st.toast(msg, icon="🔴")
    st.session_state["_live_alerts"].append(msg)


def _notify_live(key: str, site: str, live: bool, title: str = "") -> None:
    """Alert when a monitored stream goes from offline to live (not when it was already live on first check)."""
    states = st.session_state["live_states"]
    was, states[key] = states.get(key), live
    if live and was is False and st.session_state["live_notify"]:
        _alert_live(t("{site} is live: {title}", site=site, title=title) if title else t("{site} is live", site=site))


def _emit_live_alerts() -> None:
    """Show queued go-live alerts as desktop notifications (if this browser allowed them)."""
    alerts = st.session_state["_live_alerts"]
    if not alerts:
        return
    st.session_state["_live_alerts"] = []
    st.html(
        "<script>(() => {"
        "if (!('Notification' in window) || Notification.permission !== 'granted') return;"
        f"for (const body of {json.dumps(alerts)}) new Notification('Streaming Dashboard', {{body, tag: body}});"
        "})();</script>",
        unsafe_allow_javascript=True,
    )


# Browser speech player: lives in the parent page so it keeps talking across Streamlit reruns.
_TTS_PLAYER_JS = """
(() => {
  const w = window.parent || window, synth = w.speechSynthesis;
  if (!synth) return;
  const P = w.__mpcTts || (w.__mpcTts = {seen: new Set(), queue: [], speaking: false});
  const pick = (lang) => {
    const voices = synth.getVoices(), base = lang.split('-')[0];
    return voices.find(v => v.lang.replace('_', '-') === lang)
        || voices.find(v => v.lang.toLowerCase().startsWith(base)) || null;
  };
  const next = () => {
    if (P.speaking || synth.speaking) return;
    const item = P.queue.shift();
    if (!item) return;
    const u = new w.SpeechSynthesisUtterance(item.text);
    u.lang = item.lang || ''; u.rate = item.rate; u.volume = item.volume;
    const voice = item.lang ? pick(item.lang) : null;
    if (voice) u.voice = voice;
    P.speaking = true;
    u.onend = u.onerror = () => { P.speaking = false; setTimeout(next, 50); };
    synth.speak(u);
  };
  P.next = next;
  const cmd = __CMD__;
  if (cmd) {
    if (cmd === 'stop') P.queue = [];
    P.speaking = false;
    synth.cancel();
  }
  for (const item of __ITEMS__) {
    if (P.seen.has(item.id)) continue;
    P.seen.add(item.id);
    if (item.priority) {
      const at = P.queue.findIndex(q => !q.priority);
      P.queue.splice(at < 0 ? P.queue.length : at, 0, item);
    } else P.queue.push(item);
  }
  if (P.seen.size > 500) P.seen = new Set([...P.seen].slice(-200));
  setTimeout(next, 50);
})();
"""


def _emit_browser_tts() -> None:
    """Send this run's TTS lines (and skip/stop) to the viewer's browser, which speaks with its own voices."""
    items, cmd = st.session_state["_tts_browser"], st.session_state["_tts_browser_cmd"]
    if not items and not cmd:
        return
    st.session_state["_tts_browser"] = []
    st.session_state["_tts_browser_cmd"] = ""
    st.html(
        f"<script>/*{time.time_ns()}*/" + _TTS_PLAYER_JS.replace("__CMD__", json.dumps(cmd))
        .replace("__ITEMS__", json.dumps(items).replace("</", "<\\/")) + "</script>",
        unsafe_allow_javascript=True,
    )


def _check_watched_channel(force: bool = False):
    """Attach to the watched channel's stream once it goes live; detach when it ends."""
    channel = st.session_state["yt_watch_channel"]
    now = time.time()
    if not channel or (not force and now - st.session_state["yt_watch_last"] < YT_WATCH_INTERVAL):
        return
    st.session_state["yt_watch_last"] = now
    live_vid = st.session_state["yt_live_video"]
    if st.session_state["selected_chat_id"] and live_vid:
        status = ytw.get_video_status(live_vid)
        if status and status.get("broadcast") != "live":  # {} = network hiccup, keep listening
            _stop_yt_listener()
            st.toast(t("The YouTube stream ended — watching the channel for the next one."))
        return
    info = ytw.find_live_video(channel)
    st.session_state["yt_watch_info"] = info
    if not info["live"]:
        return
    chat_id, err = yt.resolve_live_chat_id(info["video_id"])
    st.session_state["yt_chat_error"] = err
    if chat_id:
        st.session_state["selected_chat_id"] = chat_id
        st.session_state["yt_page_token"] = ""
        st.session_state["yt_live_video"] = info["video_id"]
        msg = t("{channel} is live — reading chat", channel=info["channel"] or "YouTube")
        if not force and st.session_state["live_notify"]:
            _alert_live(msg)  # it went live while we were watching
        else:
            st.toast(msg)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_room_info(room_id: str) -> dict:
    return bili.get_room_info(room_id)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_me_room_info(room_id: str) -> dict:
    return me.get_room_info(room_id)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_yt_cookie_login(cookie: str, page_id: str = "") -> dict:
    # `cookie`/`page_id` are the cache key so new cookies or a channel switch re-check immediately.
    return ytw.verify_login(user_login.parse_cookie_string(cookie))


@st.cache_data(ttl=600, show_spinner=False)
def _cached_yt_channels(cookie: str) -> dict:
    return ytw.list_channels(user_login.parse_cookie_string(cookie))


def _set_yt_channel(choices: dict[str, str]) -> None:
    ytw.select_channel(choices.get(st.session_state["yt_send_as"], ""))


def _render_yt_channel_picker() -> None:
    """'Send as' picker when the Google login owns more than one YouTube channel (brand accounts)."""
    channels = _cached_yt_channels(user_login.cookie_string(ytw.login_cookies())).get("channels", [])
    if len(channels) < 2:
        return
    choices = {}
    for ch in channels:
        label = ch["name"] + (f" ({ch['handle']})" if ch["handle"] and ch["handle"] != ch["name"] else "")
        choices[label] = ch["page_id"]
    current = ytw.selected_page_id()
    labels = list(choices)
    index = next((i for i, lbl in enumerate(labels) if choices[lbl] == current), 0)
    st.selectbox(
        t("Send as"), labels, index=index, key="yt_send_as",
        on_change=_set_yt_channel, args=(choices,),
        help=t("This Google login owns several YouTube channels — pick which one your chat messages come from."),
    )


@st.cache_data(ttl=300, show_spinner=False)
def _cached_me_cookie_login(cookie: str) -> dict:
    return me.verify_login(user_login.parse_cookie_string(cookie))


@st.cache_data(ttl=300, show_spinner=False)
def _cached_bili_login(cookie: str) -> dict:
    return bc.verify_bilibili_login(user_login.parse_cookie_string(cookie))


def _login_key(site: str) -> str:
    """The current user's cookies for `site` as one string (cache key for the verify helpers)."""
    return user_login.cookie_string(user_login.get(site))


def _clear_login(site_label: str, site: str) -> None:
    bc.clear_login(site)
    for key in ("_yt_saved_name", "_yt_saved_msg", "_me_saved_msg", "_me_saved_uid", "yt_send_as"):
        st.session_state.pop(key, None)
    st.toast(t("Cleared the {site} login.", site=site_label))


def _render_login(state: Optional[dict], name: str, detail: str = "",
                  site: str = "", login_site: str = "") -> None:
    """Login line shared by every site; `state` is the verify result, or None when no cookies are set."""
    if state and state.get("is_login"):
        st.success(t("🔑 Logged in as **{name}**", name=name) + (f" · {detail}" if detail else ""))
    elif state and state.get("error"):
        st.warning(t("🔑 Couldn't check the login: {err}", err=state["error"]))
    elif state:
        st.warning(t("🔑 Login expired — re-import cookies in the 🍪 Cookies tab."))
    else:
        st.info(t("🔑 Not logged in — chat is read-only. Import cookies in the 🍪 Cookies tab to send."))
    if state is not None and login_site:
        st.button(
            t("🚪 Clear login"), key=f"clear_login_{login_site}", type="tertiary",
            on_click=_clear_login, args=(site, login_site),
            help=t("Forget your login cookies for this site (also removed from this browser). "
                   "Chat keeps working read-only."),
        )


def _render_listener(site: str, running: bool, level: str, msg: str, detail: str = "",
                     can_start: bool = True) -> Optional[str]:
    """Listener line plus Start/Stop button shared by every site. Returns "start"/"stop" when clicked."""
    if msg:
        {"ok": st.success, "info": st.info, "warn": st.warning}[level](msg)
    elif not running:
        st.caption(t("🎧 Not listening."))
    if detail:
        st.caption(detail)
    if running:
        return "stop" if st.button(t("⏹ Stop listening"), key=f"{site}_listen_stop") else None
    clicked = st.button(t("▶ Start listening"), key=f"{site}_listen_start", type="primary", disabled=not can_start)
    return "start" if clicked else None


def _me_login_state() -> Optional[dict]:
    """Verified MissEvan cookie login, or None when no cookies are saved."""
    return _cached_me_cookie_login(_login_key("missevan")) if me.has_login() else None


def _cookie_applied_msg() -> str:
    return t("Login saved for you only — kept encrypted in this browser, not shared with other users.")


def _render_missevan_verify(verify: Optional[dict], cookies: dict, key: str):
    if verify and verify["is_login"]:
        st.success(t("Logged in as **{uname}** (UID {mid}).", uname=verify["username"], mid=verify["user_id"]))
        if st.button(t("✅ Use these cookies"), key=key):
            me.save_login(cookies)
            st.session_state["_me_saved_uid"] = verify["user_id"]
            st.session_state["_me_saved_msg"] = _cookie_applied_msg()
        if st.session_state.get("_me_saved_uid") == verify["user_id"]:
            st.success(st.session_state.get("_me_saved_msg", "") + " " + t("You can now send chat to MissEvan."))
    elif verify and verify.get("error"):
        st.error(verify["error"])
    else:
        st.warning(t("MissEvan reports these cookies are not logged in — log in at fm.missevan.com first."))


# ──────────────────────────────────────────────────────────────────────────────
# Remembered settings: kept in this user's browser (localStorage), so they survive refreshes
# and restarts on Streamlit Cloud too, where the proxy strips app cookies.
# ──────────────────────────────────────────────────────────────────────────────

_SETTINGS_STORE = "mpc_settings"
_SETTINGS_READ_JS = """
export default function(component) {
    let prefs = {};
    try {
        const v = JSON.parse(window.localStorage.getItem("%s") || "{}");
        if (v && typeof v === "object" && !Array.isArray(v)) prefs = v;
    } catch (e) {}
    component.setStateValue("prefs", prefs);
}
""" % _SETTINGS_STORE


def _pref_flag(v):
    if not isinstance(v, bool):
        raise ValueError
    return v


def _pref_pick(options):
    def parse(v):
        if not isinstance(v, str) or v not in options:
            raise ValueError
        return v
    return parse


def _pref_num(lo, hi, cast=int):
    def parse(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ValueError
        return cast(v)
    return parse


def _pref_text(limit):
    def parse(v):
        if not isinstance(v, str):
            raise ValueError
        return v[:limit]
    return parse


def _pref_scales(v):
    if not isinstance(v, dict) or any(v.get(f) not in _TEXT_SIZES for f in _FEEDS):
        raise ValueError
    return {f: int(v[f]) for f in _FEEDS}


def _pref_order(v):
    if not isinstance(v, list) or sorted(v) != sorted(_FEEDS):
        raise ValueError
    return list(v)


def _pref_sides(v):
    if not isinstance(v, dict) or any(v.get(f) not in ("left", "right") for f in _FEEDS):
        raise ValueError
    return {f: v[f] for f in _FEEDS}


def _pref_sites(v):
    if not isinstance(v, list) or any(s not in overlay_server.SITES for s in v):
        raise ValueError
    return list(dict.fromkeys(v))


_PREFS = {
    **{k: _pref_flag for k in (
        "tts_enabled", "tts_translate", "tts_translate_paid", "tts_skip_name", "tts_announce_paid", "tts_read_chat", "tts_read_joins",
        "tts_skip_emoji", "translate_enabled", "show_enter_events", "obs_enabled", "obs_chat_enabled",
        "overlay_visible", "overlay_show_username", "live_notify", "show_yt", "show_bili", "show_me",
    )},
    "tts_rate": _pref_num(80, 300),
    "tts_volume": _pref_num(0.0, 1.0, float),
    "tts_lang": _pref_pick(TTS_LANGUAGES),
    "tts_output": _pref_pick(("server", "browser")),
    "translate_target": _pref_pick(tr.LANGUAGES),
    "sc_reading": _pref_pick(reading.MODES),
    "max_chat_display": _pref_num(50, 1000),
    "feed_layout": _pref_pick(("columns", "stack")),
    "feed_order": _pref_order,
    "feed_sides": _pref_sides,
    "text_scale": _pref_scales,
    "overlay_count": _pref_num(1, overlay_server.MAX_MESSAGES),
    "overlay_sc_count": _pref_num(0, overlay_server.MAX_MESSAGES),
    "overlay_sites": _pref_sites,
    "overlay_text": _pref_text(2000),
    "obs_chat_source": _pref_text(200),
    "ui_lang": _pref_pick(i18n.UI_LANGUAGES),
    "chat_tz": _pref_pick(("", *_TIMEZONES)),
    "overlay_channel": lambda v: overlay_server.clean_channel(_pref_text(40)(v)),
}
# These are also in the URL (?lang= / ?tz= / ?overlay=); a link that sets them wins over the browser copy.
_PREF_URL_PARAMS = {"ui_lang": "lang", "chat_tz": "tz", "overlay_channel": "overlay"}
# Keyed widgets that copy their value from a setting; dropped so they redraw with the restored one.
_PREF_MIRRORS = {"ui_lang": "ui_lang_select", "chat_tz": "chat_tz_select", "sc_reading": "sc_reading_pick"}


@st.cache_resource
def _settings_reader():
    return st.components.v2.component("settings_reader", js=_SETTINGS_READ_JS)


def _settings_blob() -> str:
    return json.dumps({k: st.session_state[k] for k in _PREFS if k in st.session_state},
                      sort_keys=True, ensure_ascii=False)


def _apply_saved_settings() -> None:
    """Apply the settings the browser sent on the previous run, before any widget is drawn."""
    saved = st.session_state.pop("_settings_pending", None)
    if saved is None:
        return
    for key, parse in _PREFS.items():
        if key not in saved or (key in _PREF_URL_PARAMS and _PREF_URL_PARAMS[key] in st.query_params):
            continue
        try:
            st.session_state[key] = parse(saved[key])
        except (ValueError, TypeError):
            continue
        if key in _PREF_MIRRORS:
            st.session_state.pop(_PREF_MIRRORS[key], None)
    if "lang" not in st.query_params and st.session_state["ui_lang"] != "en":
        st.query_params["lang"] = st.session_state["ui_lang"]
    if "tz" not in st.query_params and st.session_state["chat_tz"]:
        st.query_params["tz"] = st.session_state["chat_tz"]
    st.session_state["_settings_saved"] = _settings_blob()


def _read_saved_settings() -> None:
    """New browser session: ask the browser for its saved settings once.

    Drawn after every widget: if the browser's answer interrupted a run before the widgets were
    created, Streamlit would show their default values instead of the ones in session state."""
    if st.session_state.get("_settings_loaded"):
        return
    saved = _settings_reader()(
        key="settings_reader", default={"prefs": None}, on_prefs_change=lambda: None,
    ).prefs
    if saved is None:  # the browser hasn't answered yet
        return
    st.session_state["_settings_loaded"] = True
    st.session_state["_settings_pending"] = dict(saved)
    st.rerun()


def _save_settings() -> None:
    """Write the settings to this browser when they changed (never before the saved ones were loaded)."""
    if not st.session_state.get("_settings_loaded") or "_settings_pending" in st.session_state:
        return
    blob = _settings_blob()
    if blob != st.session_state.get("_settings_saved"):
        st.session_state["_settings_saved"] = blob
        st.html(f"<script>try {{ window.localStorage.setItem({json.dumps(_SETTINGS_STORE)}, "
                f"{json.dumps(blob)}); }} catch (e) {{}}</script>", unsafe_allow_javascript=True)


_apply_saved_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    _ui_keys = list(i18n.UI_LANGUAGES)
    _ui_lang = st.selectbox(
        "🌐 Language / 语言 / 言語",
        _ui_keys,
        index=_ui_keys.index(st.session_state["ui_lang"]),
        format_func=lambda k: i18n.UI_LANGUAGES[k],
        key="ui_lang_select",
    )
    if _ui_lang != st.session_state["ui_lang"]:
        st.session_state["ui_lang"] = _ui_lang
        st.query_params["lang"] = _ui_lang
        st.rerun()

    _off = datetime.now().astimezone().strftime("%z")
    _server_tz = f"UTC{_off[:3]}:{_off[3:]}" if _off else "UTC"
    _browser_tz = st.context.timezone if st.context.timezone in _TIMEZONES else ""
    _tz_options = [""] + ([_browser_tz] if _browser_tz else []) + [z for z in _TIMEZONES if z != _browser_tz]
    _chat_tz_pick = st.selectbox(
        t("🕒 Chat time zone"), _tz_options,
        index=_tz_options.index(st.session_state["chat_tz"]) if st.session_state["chat_tz"] in _tz_options else 0,
        format_func=lambda z: t("Server time ({tz})", tz=_server_tz) if not z
        else (t("{tz} (this browser)", tz=z) if z == _browser_tz else z),
        key="chat_tz_select",
        help=t("Time zone for the times shown on chat messages."),
    )
    if _chat_tz_pick != st.session_state["chat_tz"]:
        st.session_state["chat_tz"] = _chat_tz_pick
        if _chat_tz_pick:
            st.query_params["tz"] = _chat_tz_pick
        else:
            st.query_params.pop("tz", None)

    st.title(t("🎙️ Streaming Dashboard"))
    st.divider()

    # ── Translation ───────────────────────────────────────────────────────────
    st.subheader(t("🌐 Translation"))
    st.session_state["translate_enabled"] = st.toggle(
        t("Translate chat"), value=st.session_state["translate_enabled"],
        help=t("Shows a translation under each chat message."),
    )
    _tr_keys = list(tr.LANGUAGES)
    st.session_state["translate_target"] = st.selectbox(
        t("Translate to"),
        _tr_keys,
        index=_tr_keys.index(st.session_state["translate_target"]),
        format_func=lambda k: t(tr.LANGUAGES[k]),
    )

    st.divider()

    # ── TTS ───────────────────────────────────────────────────────────────────
    st.subheader(t("🔊 Text-to-Speech"))
    st.session_state["tts_enabled"] = st.toggle(
        t("Enable TTS"), value=st.session_state["tts_enabled"]
    )
    if _is_local_client():
        _out_keys = ["server", "browser"]
        st.session_state["tts_output"] = st.radio(
            t("Speak on"),
            _out_keys,
            index=_out_keys.index(st.session_state["tts_output"]),
            format_func=lambda k: t("This computer (Windows voices)") if k == "server" else t("This browser (device voices)"),
            horizontal=True,
            help=t("Browser mode uses your device's own voices and only speaks while this page is open."),
        )
    else:
        st.caption(t("🔈 Speaks with this device's voices while this page is open. Click anywhere on the page once so the browser allows sound."))
    _lang_keys = list(TTS_LANGUAGES)
    st.session_state["tts_lang"] = st.selectbox(
        t("Language"),
        _lang_keys,
        index=_lang_keys.index(st.session_state["tts_lang"]),
        format_func=lambda k: t(TTS_LANGUAGES[k][0]),
        help=t("Auto-detect reads every message in its own language. Picking a language only reads chat written in that language."),
    )
    st.caption(t("Choose what is read with 🔊 / 🔇 at the top of each list (Gifts & Super Chats, Chat, Joins). "
                 "Gifts & Super Chats are read first, in any language."))
    if (st.session_state["tts_translate"] or st.session_state["tts_translate_paid"]) and not _tts_translation_usable():
        st.caption(t(
            "⚠️ Not active: set the TTS language to Auto-detect or to the same language as \"Translate to\" ({target}).",
            target=t(tr.LANGUAGES[st.session_state["translate_target"]]),
        ))
    if st.button(t("▶ Test voice")):
        _samples = {"zh": "你好，欢迎来到直播间", "ja": "こんにちは、配信へようこそ", "ko": "안녕하세요, 방송에 오신 것을 환영합니다", "en": "Hello, welcome to the stream"}
        _sample = _samples.get(st.session_state["tts_lang"], _samples["en"])
        _play_tts(format_message("Streamer", _sample, st.session_state["tts_lang"]), st.session_state["tts_lang"])
    if st.session_state.get("_tts_audio"):
        st.audio(st.session_state["_tts_audio"], format="audio/mp3", autoplay=True)
    st.session_state["tts_rate"] = st.slider(
        t("Speed (WPM)"), 80, 300, st.session_state["tts_rate"]
    )
    st.session_state["tts_volume"] = st.slider(
        t("Volume"), 0.0, 1.0, st.session_state["tts_volume"]
    )

    st.divider()
    st.session_state["max_chat_display"] = st.number_input(
        t("Max messages displayed"), 50, 1000, st.session_state["max_chat_display"]
    )

    if st.button(t("🗑️ Clear chat history")):
        st.session_state["chat_messages"] = []
        st.session_state["join_messages"] = []
        st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# Main area tabs
# ──────────────────────────────────────────────────────────────────────────────

tab_chat, tab_status, tab_obs, tab_analytics, tab_filters, tab_cookies = st.tabs(
    [t(x) for x in ("💬 Chat", "📡 Stream Monitoring", "🎬 OBS", "📊 Analytics", "🛡️ Filters", "🍪 Cookies")]
)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: STREAM STATUS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_status:
    _notify_col, _allow_col = st.columns([3, 2], vertical_alignment="center")
    _notify_col.toggle(
        t("Notify me when a stream goes live"), key="live_notify",
        help=t("While this dashboard is open, show a pop-up (and a desktop notification, if allowed) "
               "when the YouTube channel/stream, Bilibili room or MissEvan room below goes live."),
    )
    if st.session_state["live_notify"]:
        with _allow_col:
            # A real click in the page: browsers only ask for notification permission on a user gesture.
            st.html(
                f'<button id="mpc-allow-notify" style="padding:4px 10px;border-radius:6px;cursor:pointer;'
                f'border:1px solid rgba(128,128,128,.5);background:transparent;color:inherit;font:inherit">'
                f'{html_lib.escape(t("🔔 Allow desktop notifications"))}</button>'
                '<script>(() => {'
                'const b = document.getElementById("mpc-allow-notify");'
                'if (!b) return;'
                'if (!("Notification" in window)) { b.disabled = true; return; }'
                f'const done = {json.dumps(t("🔔 Desktop notifications on"))};'
                'if (Notification.permission === "granted") { b.textContent = done; b.disabled = true; return; }'
                'b.onclick = () => Notification.requestPermission().then(p => {'
                ' if (p === "granted") { b.textContent = done; b.disabled = true; } });'
                '})();</script>',
                unsafe_allow_javascript=True,
            )
    yt_col, bili_col, me_col = st.columns(3)
    yt_viewers_now = 0
    bili_viewers_now = 0

    # ── YouTube ───────────────────────────────────────────────────────────────
    with yt_col:
        _site_heading("youtube")
        _yt_login = (_cached_yt_cookie_login(_login_key("youtube"), ytw.selected_page_id())
                     if ytw.has_login() else None)
        _render_login(_yt_login, (_yt_login or {}).get("name", ""), site="YouTube", login_site="youtube")
        if _yt_login and _yt_login.get("is_login"):
            _render_yt_channel_picker()

        yt_chat_input = st.text_input(
            t("Room ID or URL"),
            value=st.session_state["yt_chat_input"],
            key="yt_room_input",
            placeholder="https://www.youtube.com/watch?v=…",
            help=t("A live stream URL or video ID, or a channel link like https://www.youtube.com/@name — "
                   "a channel's chat is picked up automatically when it goes live."),
        ).strip()
        if yt_chat_input != st.session_state["yt_chat_input"]:
            st.session_state["yt_chat_input"] = yt_chat_input
            # Changing the stream stops the current listener, like the other sites' room fields.
            _stop_yt_listener()
            st.session_state["yt_chat_error"] = ""
            st.session_state["yt_watch_channel"] = ""
            st.session_state["yt_watch_info"] = {}

        _yt_vid = yt.extract_video_id(yt_chat_input) if yt_chat_input else ""
        _yt_channel = "" if _yt_vid else ytw.channel_url(yt_chat_input)

        _check_watched_channel()  # before drawing, so the status below is current
        watching = st.session_state["yt_watch_channel"]
        winfo = st.session_state["yt_watch_info"]
        if st.session_state["selected_chat_id"]:
            action = _render_listener(
                "yt", True, "ok", t("🎧 Listening ✓"),
                t("Live now: {title}", title=winfo["title"]) if watching and winfo.get("title") else "",
            )
        elif watching:
            name = winfo.get("channel") or watching.rsplit("/", 1)[-1]
            if winfo.get("error"):
                level, msg = "warn", t(winfo["error"])
            elif winfo.get("upcoming"):
                level, msg = "info", t("👀 Watching {name} — stream scheduled: {title}", name=name, title=winfo.get("title", ""))
            else:
                level, msg = "info", t("👀 Watching {name} — not live yet", name=name)
            action = _render_listener("yt", True, level, msg, t(
                "Checks every {s}s · last checked {time}", s=YT_WATCH_INTERVAL,
                time=datetime.fromtimestamp(st.session_state["yt_watch_last"]).strftime("%H:%M:%S"),
            ))
        else:
            action = _render_listener(
                "yt", False, "", "",
                t("Waits for the channel to go live, then reads its chat automatically.") if _yt_channel else "",
                can_start=bool(yt_chat_input),
            )
        if action == "stop":
            _stop_yt_listener()
            st.session_state["yt_watch_channel"] = ""
            st.session_state["yt_watch_info"] = {}
            st.rerun()
        elif action == "start" and _yt_channel:
            st.session_state["yt_watch_channel"] = _yt_channel
            _check_watched_channel(force=True)
            st.rerun()
        elif action == "start":
            chat_id, err = yt.resolve_live_chat_id(yt_chat_input)
            st.session_state["selected_chat_id"] = chat_id
            st.session_state["yt_chat_error"] = err
            st.session_state["yt_page_token"] = ""
            if chat_id:
                st.rerun()
        if st.session_state["yt_chat_error"] and not st.session_state["selected_chat_id"]:
            st.error(t(st.session_state["yt_chat_error"]))
        st.divider()
        yt_input = st.session_state["yt_chat_input"]
        video_id = _yt_video_id()
        if not yt_input:
            st.warning(t("Enter a stream URL above to see its status."))
        elif st.session_state["yt_watch_channel"] and not video_id:
            st.info(t("Watching the channel — it isn't live yet."))
        elif not video_id:
            st.info(t("Status needs a stream URL or video ID (a raw chat ID has no video info)."))
        else:
            info = _cached_video_status(video_id)
            if not info:
                st.error(t("Could not fetch stream info."))
            elif not info["is_stream"]:
                st.warning(t("That video is not a live stream."))
            else:
                _notify_live(f"youtube:{video_id}", "YouTube", info["broadcast"] == "live",
                             info.get("title", ""))
                if info["broadcast"] == "live":
                    dot, label = "dot-live", t("🟢 Live")
                elif info["broadcast"] == "upcoming":
                    dot, label = "dot-offline", t("🕒 Upcoming")
                else:
                    dot, label = "dot-offline", t("⚫ Ended") if info["ended"] else t("⚫ Offline")
                st.markdown(
                    f'<span class="status-dot {dot}"></span>**{label}**',
                    unsafe_allow_html=True,
                )
                st.subheader(info["title"])
                if info["channel"]:
                    st.caption(t("Channel: {channel}", channel=info["channel"]))
                if info["thumbnail"]:
                    st.image(info["thumbnail"], width=200)
                if info["broadcast"] == "live":
                    st.metric(t("Viewers"), f"{info['viewers']:,}")
                    if info["actual_start"]:
                        st.caption(t("Live since: {t}", t=info["actual_start"]))
                        _note_stream_start("youtube", info["actual_start"])
                    yt_viewers_now = info["viewers"]
                elif info["broadcast"] == "upcoming" and info["scheduled_start"]:
                    st.caption(t("Scheduled: {t}", t=info["scheduled_start"]))

    # ── Bilibili status ───────────────────────────────────────────────────────
    with bili_col:
        _site_heading("bilibili")
        _bili_login = _cached_bili_login(_login_key("bilibili")) if bili.has_login_credentials() else None
        _render_login(_bili_login, (_bili_login or {}).get("uname", ""),
                      t("UID {mid}", mid=_bili_login["mid"]) if _bili_login and _bili_login.get("mid") else "",
                      site="Bilibili", login_site="bilibili")

        bili_input = st.text_input(
            t("Room ID or URL"), value=st.session_state["bili_room_id"], key="bili_room_input",
            placeholder="https://live.bilibili.com/21452505",
        ).strip()
        bili_room = bili.parse_room_id(bili_input)
        if bili_room != st.session_state["bili_room_id"]:
            st.session_state["bili_room_id"] = bili_room
            if st.session_state["bili_listener"]:
                st.session_state["bili_listener"].stop()
                st.session_state["bili_listener"] = None
        if bili_input and not bili_room:
            st.error(t("Could not find a room ID in that text."))

        listener: Optional[bili.DanmakuListener] = st.session_state["bili_listener"]
        bili_running = bool(listener and listener._running)
        level, msg = "", ""
        if bili_running and listener.connected_uid is None:
            level, msg = "info", t("🎧 Connecting…")
        elif bili_running and listener.is_anonymous:
            level, msg = "warn", t(
                "🎧 Listening anonymously — Bilibili masks usernames (e.g. 波***). "
                "Import login cookies in the 🍪 Cookies tab."
            )
        elif bili_running:
            level, msg = "ok", t("🎧 Listening ✓")
        action = _render_listener("bili", bili_running, level, msg, can_start=bool(bili_room))
        if action == "stop":
            listener.stop()
            st.session_state["bili_listener"] = None
            st.rerun()
        elif action == "start":
            l = bili.DanmakuListener(bili_room)
            if l.start():
                st.session_state["bili_listener"] = l
                st.rerun()
            else:
                st.error(t("bilibili-api-python not installed or connection failed."))
        st.divider()
        room_id = st.session_state["bili_room_id"]
        if not room_id:
            st.warning(t("Enter a room ID above to see its status."))
        else:
            info = _cached_room_info(room_id)
            if not info:
                st.error(t("Could not fetch room info."))
            else:
                live_status = info.get("live_status", 0)
                _notify_live(f"bilibili:{room_id}", "Bilibili", live_status == 1,
                             info.get("uname") or info.get("title", ""))
                status_map = {1: ("dot-live", t("🟢 Live")), 0: ("dot-offline", t("⚫ Offline")), 2: ("dot-offline", t("📼 Playback"))}
                dot, label = status_map.get(live_status, ("dot-offline", t("Unknown")))
                st.markdown(
                    f'<span class="status-dot {dot}"></span>**{label}**',
                    unsafe_allow_html=True,
                )
                st.subheader(info.get("title", ""))
                if info.get("uname"):
                    st.caption(t("Streamer: {name}", name=info["uname"]))
                area = info.get("parent_area_name", "")
                if area:
                    st.caption(t("Category: {area} › {sub}", area=area, sub=info.get("area_name", "")))
                if info.get("cover"):
                    st.image(info["cover"], width=200)
                viewers = info.get("online", 0)
                bili_viewers_now = viewers
                st.metric(t("Viewers"), f"{viewers:,}")
                if info.get("start_time") and live_status == 1:
                    st.caption(t("Live since: {t}", t=info["start_time"]))
                    _note_stream_start("bilibili", str(info["start_time"]), "Asia/Shanghai")

    # ── MissEvan status ───────────────────────────────────────────────────────
    me_viewers_now = 0
    with me_col:
        _site_heading("missevan")
        _me_login = _me_login_state()
        _render_login(_me_login, (_me_login or {}).get("username", ""),
                      t("UID {mid}", mid=_me_login["user_id"]) if _me_login and _me_login.get("user_id") else "",
                      site=t("MissEvan"), login_site="missevan")

        me_input = st.text_input(
            t("Room ID or URL"), value=st.session_state["me_room_id"], key="me_room_input",
            placeholder="https://fm.missevan.com/live/869215180",
        ).strip()
        me_room = me.parse_room_id(me_input)
        if me_room != st.session_state["me_room_id"]:
            st.session_state["me_room_id"] = me_room
            if st.session_state["me_listener"]:
                st.session_state["me_listener"].stop()
                st.session_state["me_listener"] = None
        if me_input and not me_room:
            st.error(t("Could not find a room ID in that text."))

        me_listener: Optional[me.MissEvanListener] = st.session_state["me_listener"]
        me_running = bool(me_listener and me_listener.running)
        level, msg = "", ""
        if me_running and me_listener.connected:
            level, msg = "ok", t("🎧 Listening ✓")
        elif me_running and me_listener.error:
            level, msg = "warn", me_listener.error
        elif me_running:
            level, msg = "info", t("🎧 Connecting…")
        action = _render_listener("me", me_running, level, msg, can_start=bool(me_room))
        if action == "stop":
            me_listener.stop()
            st.session_state["me_listener"] = None
            st.rerun()
        elif action == "start":
            l = me.MissEvanListener(me_room)
            if l.start():
                st.session_state["me_listener"] = l
                st.rerun()
            else:
                st.error(l.error)
        st.divider()
        me_room_id = st.session_state["me_room_id"]
        if not me_room_id:
            st.warning(t("Enter a room ID above to see its status."))
        else:
            info = _cached_me_room_info(me_room_id)
            if not info:
                st.error(t("Could not fetch room info."))
            else:
                _notify_live(f"missevan:{me_room_id}", t("MissEvan"), info["live"],
                             info.get("uname") or info.get("title", ""))
                dot, label = ("dot-live", t("🟢 Live")) if info["live"] else ("dot-offline", t("⚫ Offline"))
                st.markdown(f'<span class="status-dot {dot}"></span>**{label}**', unsafe_allow_html=True)
                st.subheader(info.get("title", ""))
                if info.get("uname"):
                    st.caption(t("Streamer: {name}", name=info["uname"]))
                if info.get("cover"):
                    st.image(info["cover"], width=200)
                _l = st.session_state["me_listener"]
                viewers = _l.online if _l and _l.online is not None else info.get("online", 0)
                if info["live"] and viewers:
                    me_viewers_now = viewers
                    st.metric(t("Viewers"), f"{viewers:,}")
                st.caption(t("Followers: {n}", n=f"{info.get('followers', 0):,}"))
                if info.get("start_time"):
                    st.caption(t("Live since: {t}", t=info["start_time"]))
                    if info["live"]:
                        _note_stream_start("missevan", info["start_time"])

    if yt_viewers_now or bili_viewers_now or me_viewers_now:
        _record_viewer_snapshot(yt_viewers_now, bili_viewers_now, me_viewers_now)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: CHAT
# ═══════════════════════════════════════════════════════════════════════════════

_EMOTE_TTL = 600


def _emote_button(e: dict, key: str, locked_help: str, on_pick=None) -> bool:
    alt = re.sub(r"[\[\]()\\]", "", e["name"])[:24] or "emote"
    locked = e.get("locked") is True
    tip = e["name"] + (f"\n\n🔒 {e.get('hint') or locked_help}" if locked else "")
    return st.button(f"![{alt}]({e['url']})", key=key, help=tip, disabled=locked,
                     on_click=on_pick, args=(e,) if on_pick else None)


def _emote_buttons(items: list[dict], key: str, locked_help: str, on_pick=None) -> dict | None:
    """Image buttons for emotes; returns the clicked one (or calls on_pick(emote) as a click callback)."""
    picked = None
    with st.container(horizontal=True, gap="small", key=f"emote_grid_{key}"):
        for i, e in enumerate(items):
            if _emote_button(e, f"emo_{key}_{i}", locked_help, on_pick):
                picked = e
    return picked


def _emote_pack_keys(packs: list[dict], key: str) -> list[str]:
    """Expander keys from the pack names (packs have no ID), so open/closed survives a refresh."""
    seen: dict[str, int] = {}
    keys = []
    for pack in packs:
        name = pack.get("name") or "?"
        seen[name] = seen.get(name, 0) + 1
        keys.append(f"emo_pack_{key}_{zlib.crc32(name.encode('utf-8')):08x}_{seen[name]}")
    return keys


# Which emote packs are open, kept in this user's browser (localStorage) so it survives refreshes and restarts.
_EMOTE_PACK_PREFS = "emote_pack_prefs"
_EMOTE_PACK_STORE = "mpc_emote_packs"
_EMOTE_PACK_READ_JS = """
export default function(component) {
    let prefs = {};
    try {
        const v = JSON.parse(window.localStorage.getItem("%s") || "{}");
        if (v && typeof v === "object" && !Array.isArray(v)) prefs = v;
    } catch (e) {}
    component.setStateValue("prefs", prefs);
}
""" % _EMOTE_PACK_STORE


@st.cache_resource
def _emote_pack_reader():
    return st.components.v2.component("emote_pack_reader", js=_EMOTE_PACK_READ_JS)


def _load_emote_pack_prefs() -> None:
    """New browser session: read the remembered open/closed packs once (the browser answers on a rerun)."""
    if _EMOTE_PACK_PREFS in st.session_state:
        return
    prefs = _emote_pack_reader()(
        key="emote_pack_reader", default={"prefs": None}, on_prefs_change=lambda: None,
    ).prefs
    if prefs is None:  # the browser hasn't answered yet
        return
    st.session_state[_EMOTE_PACK_PREFS] = {
        k: v for k, v in dict(prefs).items() if isinstance(k, str) and k.startswith("emo_pack_") and isinstance(v, bool)
    }


def _save_emote_pack_prefs() -> None:
    if st.session_state.pop("_emote_pack_prefs_dirty", False):
        data = json.dumps(st.session_state.get(_EMOTE_PACK_PREFS, {}), sort_keys=True)
        st.html(f"<script>try {{ window.localStorage.setItem({json.dumps(_EMOTE_PACK_STORE)}, "
                f"{json.dumps(data)}); }} catch (e) {{}}</script>", unsafe_allow_javascript=True)


def _remember_emote_packs(keys: list[str]) -> None:
    prefs = st.session_state.setdefault(_EMOTE_PACK_PREFS, {})
    for k in keys:
        prefs[k] = bool(st.session_state.get(k))
    st.session_state["_emote_pack_prefs_dirty"] = True


def _set_emote_packs_open(keys: list[str], is_open: bool) -> None:
    for k in keys:
        st.session_state[k] = is_open
    _remember_emote_packs(keys)


def _emote_packs(packs: list[dict], key: str, locked_help: str) -> dict | None:
    """One collapsible section per pack; the room owner's packs (⭐) start open. Closed packs aren't
    rendered at all, which keeps a room with many packs quick. Open/closed is remembered per user."""
    picked = None
    keys = _emote_pack_keys(packs, key)
    any_owner = any(p.get("owner") for p in packs)
    prefs = st.session_state.get(_EMOTE_PACK_PREFS, {})
    tools = st.container(horizontal=True, gap="small")
    tools.button(t("Expand all"), key=f"emo_{key}_expand", type="tertiary", icon=":material/unfold_more:",
                 on_click=_set_emote_packs_open, args=(keys, True))
    tools.button(t("Collapse all"), key=f"emo_{key}_collapse", type="tertiary", icon=":material/unfold_less:",
                 on_click=_set_emote_packs_open, args=(keys, False))
    for n, (pack, pack_key) in enumerate(zip(packs, keys)):
        # Streamlit forgets a widget's state while it isn't shown (picker closed), so the prefs are the source.
        if pack_key not in st.session_state:
            st.session_state[pack_key] = prefs.get(pack_key, bool(pack.get("owner")) or (not any_owner and n == 0))
    # Open packs first (in their usual order), then the closed ones; n stays the pack's original index for keys.
    order = sorted(range(len(packs)), key=lambda n: not st.session_state[keys[n]])
    for n in order:
        pack, pack_key = packs[n], keys[n]
        label = ("⭐ " if pack.get("owner") else "") + (pack["name"] or "?") + f" ({len(pack['emotes'])})"
        exp = st.expander(label, key=pack_key, type="compact",
                          on_change=_remember_emote_packs, args=([pack_key],))
        if not exp.open:
            continue
        with exp, st.container(horizontal=True, gap="small", key=f"emote_grid_{key}{n}"):
            for i, e in enumerate(pack["emotes"]):
                if _emote_button(e, f"emo_{key}{n}_{i}", locked_help):
                    picked = e
    return picked


_YT_STAMP_MAX = 200  # YouTube's chat message length limit


# The draft lives in its own key: widget state inside a closed popover is discarded.
def _add_yt_stamp(emote: dict) -> None:
    draft = st.session_state.get("yt_stamp_draft", "")
    if len(draft) + len(emote["code"]) <= _YT_STAMP_MAX:
        st.session_state["yt_stamp_draft"] = draft + emote["code"]


def _sync_yt_stamp_input() -> None:
    st.session_state["yt_stamp_draft"] = st.session_state.get("yt_stamp_input", "")


def _send_yt_stamps(yt_chat: str, yt_vid: str) -> None:
    draft = st.session_state.get("yt_stamp_draft", "").strip()
    if not draft:
        return
    ok, err = yt.send_chat(yt_chat, yt_vid, draft)
    st.session_state["yt_stamp_result"] = (ok, err)
    if ok:
        st.session_state["yt_stamp_draft"] = ""


def _report_send(site: str, ok: bool, err: str) -> None:
    # A toast, not st.error: the picker popover closes on the rerun that sends.
    if ok:
        st.toast(t("Sent to {site} ✓", site=site))
    else:
        st.toast(t("Failed to send to {site}: {err}", site=site, err=t(err) if err else "?"), icon="⚠️", duration="long")


_EMOTE_IMG_JS = """<script>(() => {
  if (window.__mpcEmoteImgs2) return;
  window.__mpcEmoteImgs2 = true;
  // Bilibili's CDN refuses hotlinked images; markdown images in buttons can't set referrerpolicy.
  const fix = (root) => root.querySelectorAll('[class*="st-key-emote_grid_"] img').forEach((img) => {
    if (img.referrerPolicy === 'no-referrer') return;
    img.referrerPolicy = 'no-referrer';
    const src = img.getAttribute('src');
    img.removeAttribute('src');
    img.setAttribute('src', src);
  });
  fix(document);
  // Keep emote popovers inside the window: when they open low, the bottom (last packs) was unreachable.
  const fit = () => document.querySelectorAll('[data-testid="stPopoverBody"]').forEach((p) => {
    if (!p.querySelector('[class*="st-key-emote_grid_"], [class*="st-key-emo_bili_expand"]')) return;
    const room = Math.max(240, Math.floor(window.innerHeight - p.getBoundingClientRect().top - 12));
    if (p.style.maxHeight !== room + 'px') p.style.setProperty('max-height', room + 'px', 'important');
  });
  new MutationObserver(() => { fix(document); fit(); }).observe(document.body, {childList: true, subtree: true});
  window.addEventListener('resize', fit);
})();</script>"""


def _site_emote_row(yt_chat: str, yt_vid: str, bili_room: str) -> None:
    """One picker per site, each sending only to its own site. YouTube stamps are collected into a
    draft (several stamps plus text per message); a Bilibili emote is a danmaku of its own."""
    st.html(_EMOTE_IMG_JS, unsafe_allow_javascript=True)
    _load_emote_pack_prefs()
    _save_emote_pack_prefs()
    row = st.container(horizontal=True, vertical_alignment="center", gap="small", key="emote_row")
    row.markdown(f"**{t('Site emotes')}:**", width="content")
    yt_pop = row.popover("YouTube", icon="😀", key="emo_pop_yt", on_change="rerun", disabled=not yt_chat,
                         help=None if yt_chat else t("Start the YouTube listener first."))
    bili_pop = row.popover("Bilibili", icon="😀", key="emo_pop_bili", on_change="rerun", disabled=not bili_room,
                           help=None if bili_room else t("Enter a Bilibili room ID first."))
    row.caption(t("Each site's own emotes, sent only to that site."), width="content")

    result = st.session_state.pop("yt_stamp_result", None)
    if result:
        _report_send("YouTube", *result)

    if yt_pop.open:
        with yt_pop:
            refresh = st.button(t("🔄 Refresh"), key="emo_yt_refresh")
            items = ytw.channel_emojis(yt_vid, fetch=True, refresh=refresh)
            st.caption(t("Sent only to YouTube. Click stamps to add them (as many as you like), add text if you "
                         "want, then send. Channel stamps show up here once someone uses them in chat; with a "
                         "YouTube login (🍪 Cookies tab) the full set is listed and 🔒 marks member-only stamps "
                         "you can't use."))
            if not items:
                st.info(t("No channel stamps seen yet."))
            _emote_buttons(items, "yt", t("Members only"), on_pick=_add_yt_stamp)
            draft = st.session_state.setdefault("yt_stamp_draft", "")
            st.session_state["yt_stamp_input"] = draft
            st.text_input(t("Message"), key="yt_stamp_input", max_chars=_YT_STAMP_MAX, on_change=_sync_yt_stamp_input,
                          placeholder=t("Click stamps above…"), label_visibility="collapsed")
            if draft.strip():
                emote_map = {c: e["url"] for e in items for c in e.get("shortcuts") or [e["code"]]}
                st.markdown(f'<div class="yt-stamp-preview">{emotes.text_to_html(draft, emote_map)}</div>',
                            unsafe_allow_html=True)
            act = st.container(horizontal=True, gap="small")
            act.button(t("Send to YouTube"), key="emo_yt_send", type="primary", disabled=not draft.strip(),
                       on_click=_send_yt_stamps, args=(yt_chat, yt_vid))
            act.button(t("Clear"), key="emo_yt_clear", disabled=not draft,
                       on_click=lambda: st.session_state.update(yt_stamp_draft=""))

    if bili_pop.open:
        with bili_pop:
            cache = st.session_state.setdefault("bili_emotes", {})
            refresh = st.button(t("🔄 Refresh"), key="emo_bili_refresh")
            if refresh or cache.get("room") != bili_room or time.time() - cache.get("ts", 0) > _EMOTE_TTL:
                packs, err = bili.get_emoticons(bili_room)
                # A Bilibili server hiccup shouldn't stick for the whole TTL: try again after a minute.
                ts = time.time() - (_EMOTE_TTL - 60 if err == getattr(bili, "_EMOTE_SERVER_ERR", None) else 0)
                cache.update(room=bili_room, ts=ts, packs=packs, err=err)
            st.caption(t("Sent only to Bilibili, as a sticker danmaku. 🔒 emotes need e.g. this room's fan medal, "
                         "a guard membership, or charging (充电) the streamer for the 充电表情 tab."))
            if cache.get("err"):
                st.warning(t(cache["err"]))
            packs = cache.get("packs") or []
            if packs:
                # get_emoticons lists the room owner's packs (⭐) first; the sort is a fallback for old caches.
                packs = sorted(packs, key=lambda p: 0 if p.get("owner") else 1)
                picked = _emote_packs(packs, "bili", t("Locked"))
                if picked:
                    _report_send("Bilibili", *bili.send_emoticon(bili_room, picked["unique"]))
            elif not cache.get("err"):
                st.info(t("This room has no emotes you can send."))


with tab_chat:
    _poll_chat()  # fetch new messages every rerun
    _sync_obs_chat()

    # ── Send message ──────────────────────────────────────────────────────────
    yt_chat = st.session_state.get("selected_chat_id", "")
    bili_room_send = st.session_state["bili_room_id"]
    tgt_row = st.container(horizontal=True, vertical_alignment="center", gap="medium", key="send_targets")
    tgt_row.markdown(f"**{t('Send to')}:**", width="content")
    send_yt = tgt_row.checkbox(
        "YouTube", key="send_yt", value=True, disabled=not yt_chat,
        help=None if yt_chat else t("Start the YouTube listener first."),
    )
    send_bili = tgt_row.checkbox(
        "Bilibili", key="send_bili", value=True, disabled=not bili_room_send,
        help=None if bili_room_send else t("Enter a Bilibili room ID first."),
    )
    me_room_send = st.session_state["me_room_id"]
    _me_send_login = _me_login_state()
    # A failed check (network error) shouldn't block sending; only a confirmed logout does.
    me_logged_in = bool(_me_send_login and (_me_send_login["is_login"] or _me_send_login.get("error")))
    send_me = tgt_row.checkbox(
        t("MissEvan"), key="send_me", value=True, disabled=not (me_room_send and me_logged_in),
        help=None if me_room_send and me_logged_in
        else t("Log in to MissEvan in the 🍪 Cookies tab first.") if not me_logged_in
        else t("Enter a MissEvan room first."),
    )
    _yt_emo_vid = _yt_video_id() or (yt_chat[len(yt.WEB_CHAT_PREFIX):] if yt.is_web_chat(yt_chat) else "")
    _emotes_ready = hasattr(ytw, "channel_emojis") and hasattr(bili, "get_emoticons")
    _yt_emojis = ytw.channel_emojis(_yt_emo_vid) if _emotes_ready and _yt_emo_vid else []
    if _emotes_ready:
        _site_emote_row(yt_chat, _yt_emo_vid, bili_room_send)
    with st.form("send_form", clear_on_submit=True), st.container(key="send_box"):
        send_cols = st.columns([8, 1])
        outgoing = send_cols[0].text_input(t("Message"), label_visibility="collapsed", placeholder=t("Type a message…"))
        submitted = send_cols[1].form_submit_button(t("Send"))
        if submitted and outgoing:
            # YouTube stamp codes (:_name:) only mean something on YouTube; don't spam them elsewhere.
            other = ytw.strip_emoji_codes(outgoing, _yt_emojis) if _emotes_ready else outgoing
            targets = []
            if send_yt and yt_chat:
                targets.append(("YouTube", lambda: yt.send_chat(
                    yt_chat, _yt_video_id(), outgoing)))
            if send_bili and bili_room_send:
                if other:
                    targets.append(("Bilibili", lambda: (bili.send_danmaku(bili_room_send, other), "")))
                else:
                    st.info(t("Only YouTube stamps — not sent to {site}.", site="Bilibili"))
            if send_me and me_room_send and me_logged_in:
                if other:
                    targets.append(("MissEvan", lambda: me.send_message(me_room_send, other)))
                else:
                    st.info(t("Only YouTube stamps — not sent to {site}.", site=t("MissEvan")))
            if not (send_yt and yt_chat) and not (send_bili and bili_room_send) and not (
                    send_me and me_room_send and me_logged_in):
                st.warning(t("Tick at least one site to send to."))
            for name, send in targets:
                ok, err = send()
                if ok:
                    st.toast(t("Sent to {site} ✓", site=name))
                elif err:
                    st.error(t("Failed to send to {site}: {err}", site=name, err=err))
                else:
                    st.error(t("Failed to send to {site} (check the login cookies).", site=name))

    st.divider()

    # ── Platform filter ───────────────────────────────────────────────────────
    show_row = st.container(horizontal=True, vertical_alignment="center", gap="large", key="show_row")
    show_yt = show_row.checkbox("YouTube", key="show_yt")
    show_bili = show_row.checkbox("Bilibili", key="show_bili")
    show_me = show_row.checkbox(t("MissEvan"), key="show_me")
    show_row.space("stretch")
    show_row.segmented_control(
        t("Layout"), ["columns", "stack"], key="feed_layout", required=True, label_visibility="collapsed",
        format_func=lambda v: t("◫ 2 columns") if v == "columns" else t("☰ 1 column"),
        help=t("Use ▲ ▼ on each list to change its position, and ◀ ▶ to move it to the other column."),
    )
    if st.session_state["tts_enabled"]:
        _tts_stop_buttons(show_row, "feeds")

    hidden_platforms = {
        p for p, shown in (("youtube", show_yt), ("bilibili", show_bili), ("missevan", show_me)) if not shown
    }
    # All gifts, including free gifts, and other paid events have their own column.
    msgs = [
        m for m in st.session_state["chat_messages"]
        if m.get("platform") not in hidden_platforms and not (is_paid(m) or is_gift(m))
    ]
    paid_all = [m for m in st.session_state["paid_messages"] if m.get("platform") not in hidden_platforms]

    # Show newest first
    visible = msgs[-st.session_state["max_chat_display"] :]
    if st.session_state["translate_enabled"]:
        # One batched request for everything on screen (also covers changing the target language).
        tr.prefetch(
            [m.get("text", "") for m in visible + paid_all[-100:] if m.get("type") != "enter"],
            st.session_state["translate_target"],
            wait=2.0,
        )

    scales = st.session_state["text_scale"]
    _joins_shown = st.session_state["show_enter_events"]
    feed_order, feed_sides, stacked = _feed_layout_state()
    if stacked:
        feed_columns = [feed_order]
    else:
        feed_columns = [[f for f in feed_order if feed_sides[f] == side] for side in ("left", "right")]
        feed_columns = [c for c in feed_columns if c]
    st.markdown(
        f"<style>.st-key-chat_feed {{ --chat-scale: {scales['chat'] / 100}; }}"
        f".st-key-paid_feed {{ --chat-scale: {scales['paid'] / 100}; }}"
        f"{_feed_height_css(feed_columns, stacked, _joins_shown)}</style>",
        unsafe_allow_html=True,
    )

    def _chat_feed():
        chat_head = st.container(horizontal=True, vertical_alignment="center")
        chat_head.markdown(f"**💬 {t('Chat')}**", width="content")
        _feed_tts_button(chat_head, "tts_read_chat")
        if st.session_state["tts_enabled"]:
            _tts_option(chat_head, "tts_skip_emoji", t("Ignore emoji"),
                        t("Skip emoji-only messages and stickers, and don't read emoji inside messages."))
            _tts_option(chat_head, "tts_skip_name", t("Don't read usernames"),
                        t("Reads only the message text. Gifts and Super Chats still say who sent them."))
            _tts_option(chat_head, "tts_translate", t("Read translated chat"), t(
                "When the TTS language is Auto-detect or matches \"Translate to\" (Translation section), every chat "
                "message is read translated into that language. Otherwise messages are read in their original language."
            ))
        _feed_tools(chat_head, "chat")
        with st.container(key="chat_feed"):
            for msg in reversed(visible):
                _render_message(msg, key_prefix="chat")

    def _paid_feed():
        thanked_ids: set = st.session_state["thanked_ids"]
        pending = [m for m in paid_all if m["id"] not in thanked_ids]
        paid_head = st.container(horizontal=True, vertical_alignment="center")
        paid_head.markdown(
            f"**🎁 {t('Gifts & Super Chats')}** · "
            f"{t('{n} to thank', n=len(pending))} / {t('{n} total', n=len(paid_all))}",
            width="content",
        )
        paid_head.button(
            t("🙏 Mark all thanked"), key="thank_all", disabled=not pending,
            on_click=_set_thanked, args=([m["id"] for m in pending], True),
        )
        with paid_head.popover(f"🔤 {t('Super Chat reading aid')}"):
            _rd_keys = list(reading.MODES)
            # on_change stores the choice before the rerun, so feeds drawn above this one use it too.
            st.selectbox(
                t("Super Chat reading aid"),
                _rd_keys,
                index=_rd_keys.index(st.session_state["sc_reading"]),
                key="sc_reading_pick",
                format_func=lambda k: t(reading.MODES[k]),
                help=t("Shows pinyin / furigana above Chinese characters in Super Chats, gifts and all usernames "
                       "so you can read them aloud. Translations get furigana when Japanese, and Super Chat "
                       "and gift translations get pinyin when Chinese."),
                on_change=lambda: st.session_state.update(sc_reading=st.session_state["sc_reading_pick"]),
            )
        _feed_tts_button(paid_head, "tts_announce_paid")
        if st.session_state["tts_enabled"]:
            _tts_option(paid_head, "tts_translate_paid", t("Read translated Super Chats"), t(
                "When the TTS language is Auto-detect or matches \"Translate to\" (Translation section), Super Chat "
                "messages are read translated into that language. Gift names are always read as they are."
            ))
        _feed_tools(paid_head, "paid")
        with st.container(key="paid_feed"):
            if not paid_all:
                st.caption(t("No gifts or Super Chats yet."))
            for msg in reversed(paid_all[-200:]):
                _render_message(msg, key_prefix="paid", thank=True)

    def _join_feed():
        joins = [m for m in st.session_state["join_messages"] if m.get("platform") not in hidden_platforms]
        join_head = st.container(horizontal=True, vertical_alignment="center")
        join_head.markdown(f"**👋 {t('Joins')}** · {t('{n} total', n=len(joins))}", width="content")
        join_head.button(
            t("🙈 Hide") if _joins_shown else t("👁️ Show"), key="toggle_joins",
            help=t("Show or hide viewers entering the room."),
            on_click=lambda: st.session_state.update(show_enter_events=not st.session_state["show_enter_events"]),
        )
        _feed_tts_button(join_head, "tts_read_joins")
        _feed_tools(join_head, "join", text_size=_joins_shown)
        if _joins_shown:
            rows = "".join(
                f'<div class="join-row"><span class="join-time">{_fmt_time(m.get("timestamp", ""))}</span>'
                f'{_platform_badge(m)}<b>{_author_html(m.get("author", ""))}</b></div>'
                for m in reversed(joins[-150:])
            ) or f'<div class="join-empty">{t("No one has joined yet.")}</div>'
            st.markdown(
                f'<div class="join-feed" style="--chat-scale: {scales["join"] / 100}">{rows}</div>',
                unsafe_allow_html=True,
            )

    _feed_renderers = {"chat": _chat_feed, "paid": _paid_feed, "join": _join_feed}
    feeds_box = st.container(key="chat_paid")
    if len(feed_columns) == 1:
        targets = [feeds_box]
    else:
        # The column holding the chat gets more room, as chat lines are longer than gift lines.
        targets = feeds_box.columns([3 if "chat" in c else 2 for c in feed_columns])
    for target, column in zip(targets, feed_columns):
        with target:
            for feed in column:
                _feed_renderers[feed]()

    # Auto-refresh placeholder
    st.markdown(
        f"<p style='color:color-mix(in srgb, currentColor 50%, transparent);font-size:0.75rem'>"
        f"{t('Auto-refreshes every {s}s · {n} messages shown', s=CHAT_POLL_INTERVAL, n=len(msgs))}</p>",
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: OBS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_obs:
    # Everything OBS-related lives here: it's for the streamer only.
    # Filled in below, once the overlay settings further down have produced the link.
    _overlay_quick = st.container(border=True)
    # The overlay settings render right under the link they change.
    _overlay_settings = st.expander(t("⚙️ Overlay settings"), expanded=True)
    _obs_local = _is_local_client()
    if not _obs_local:
        # The OBS WebSocket can start/stop the stream, so only the computer running the dashboard gets it.
        st.session_state["obs_enabled"] = False
        st.info(t("OBS controls are only available on the computer running this dashboard. "
                  "The chat overlay below works from anywhere."))
    else:
        st.toggle(
            t("Connect to OBS"), key="obs_enabled", on_change=obs.retry_now,
            help=t("Off: the dashboard never contacts OBS. On: stream, recording, scene and Text source controls appear here once OBS is connected."),
        )
    obs_status = obs.get_status() if st.session_state["obs_enabled"] else {"connected": False}
    if not _obs_local:
        st.session_state["obs_chat_last"] = None
    elif not obs_status.get("connected"):
        st.session_state["obs_chat_last"] = None
        if st.session_state["obs_enabled"]:
            code, detail = obs.last_error
            addr = f"{OBS_HOST}:{OBS_PORT}"
            if code == "no_lib":
                st.warning(t("⚠️ OBS is not connected: obsws-python is not installed. Run `pip install obsws-python`."))
            elif code == "no_password":
                st.warning(t("⚠️ OBS is not connected: OBS_PASSWORD is not set in .env."))
            elif code == "auth":
                st.warning(t("⚠️ OBS at {addr} refused the login — check OBS_PASSWORD. ({detail})",
                             addr=addr, detail=detail))
            else:
                st.warning(t("⚠️ OBS is not connected: nothing answered at {addr}.", addr=addr))
                st.caption(t(
                    "Is OBS running with its WebSocket server enabled? OBS_HOST is resolved on the computer "
                    "running this dashboard — if that's a server, `localhost` means the server itself. Set "
                    "OBS_HOST to the address of the PC running OBS, reachable from the server (same network, "
                    "VPN such as Tailscale, or a port forward), and allow port {port} in that PC's firewall.", port=OBS_PORT,
                ))
        else:
            st.caption(t("OBS functions are off."))
        with st.expander(t("Setup instructions")):
            st.markdown(
                t("obs_setup_md") if st.session_state["ui_lang"] != "en" else """
1. Open OBS → **Tools → WebSocket Server Settings**
2. Enable the WebSocket server
3. Set a password and note the port (default 4455)
4. Add to your `.env`:
   ```
   OBS_HOST=localhost
   OBS_PORT=4455
   OBS_PASSWORD=your_password
   ```
"""
            )
    else:
        st.success(t("OBS connected ✓"))
        # ── Status metrics ────────────────────────────────────────────────────
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("CPU", f"{obs_status['cpu_usage']}%")
        m2.metric("RAM", f"{obs_status['memory_usage']} MB")
        m3.metric("FPS", f"{obs_status['fps']}")
        m4.metric(
            t("Dropped Frames"),
            obs_status.get("output_skipped_frames", 0),
        )

        st.divider()

        # ── Stream / Record controls ─────────────────────────────────────────
        ctrl_col1, ctrl_col2 = st.columns(2)
        with ctrl_col1:
            st.subheader(t("🔴 Stream"))
            streaming = obs_status.get("streaming", False)
            if streaming:
                st.success(t("Streaming is LIVE"))
                if st.button(t("⏹ Stop Stream")):
                    obs.stop_stream()
                    st.rerun()
            else:
                st.info(t("Not streaming"))
                if st.button(t("▶️ Start Stream")):
                    obs.start_stream()
                    st.rerun()

        with ctrl_col2:
            st.subheader(t("⏺ Recording"))
            recording = obs_status.get("recording", False)
            if recording:
                st.success(t("Recording in progress"))
                if st.button(t("⏹ Stop Recording")):
                    obs.stop_recording()
                    st.rerun()
            else:
                st.info(t("Not recording"))
                if st.button(t("▶️ Start Recording")):
                    obs.start_recording()
                    st.rerun()

        st.divider()

        # ── Scene / Source management ─────────────────────────────────────────
        st.subheader(t("🎭 Scenes & Sources"))
        scenes = obs.get_scenes()
        cur_scene = obs_status.get("current_scene", "")
        if scenes:
            new_scene = st.radio(t("Active scene"), scenes, index=scenes.index(cur_scene) if cur_scene in scenes else 0, horizontal=True)
            if new_scene != cur_scene:
                obs.switch_scene(new_scene)
                st.rerun()

            sources = obs.get_sources(new_scene)
            if sources:
                st.caption(t("Sources in selected scene:"))
                for src in sources:
                    vis = st.checkbox(src["name"], value=src["visible"], key=f"src_{src['id']}")
                    if vis != src["visible"]:
                        obs.set_source_visibility(new_scene, src["name"], vis)

        st.divider()

        # ── Chat → OBS Text source ──────────────────────────────────────────
        st.subheader(t("📝 OBS Text source"))
        st.toggle(t("Send chat to OBS Text source"), key="obs_chat_enabled")
        if st.session_state["obs_chat_enabled"]:
            try:
                text_sources = obs.get_text_sources()
            except Exception as exc:
                st.warning(t("Couldn't list OBS Text sources: {err}", err=str(exc)))
            else:
                if text_sources:
                    if st.session_state["obs_chat_source"] not in text_sources:
                        st.session_state["obs_chat_source"] = text_sources[0]
                    st.selectbox(t("OBS Text source"), text_sources, key="obs_chat_source")
                else:
                    st.session_state["obs_chat_source"] = ""
                    st.warning(t("Add a Text source in OBS to display chat."))

    st.divider()

    # ── Browser Source overlay (works without the WebSocket connection) ──────
    st.subheader(t("🖥️ Chat Overlay"))
    st.markdown(
        t("Use the overlay URL in OBS as a **Browser Source** to show a transparent chat on stream.")
    )

    st.caption(t("⬆️ The overlay settings are at the top of this tab, under the standalone overlay link."))

    _overlay_site_labels = {"youtube": "YouTube", "bilibili": "Bilibili", "missevan": t("MissEvan")}
    # A stale/unknown entry would make format_func return None, which newer Streamlit can't serialize.
    st.session_state["overlay_sites"] = [s for s in st.session_state["overlay_sites"] if s in _overlay_site_labels]
    with _overlay_settings:
        _set_l, _set_r = st.columns(2)
        with _set_l:
            st.multiselect(
                t("Sites on this overlay"), list(_overlay_site_labels), key="overlay_sites",
                format_func=lambda s: _overlay_site_labels.get(s, str(s)),
                help=t("Show only some sites' chat — e.g. one Browser Source per site. Adds ?site=… to the overlay URL; "
                       "leave all selected (or empty) for every site."),
            )
            st.number_input(
                t("Messages shown in OBS overlay"), min_value=1, max_value=overlay_server.MAX_MESSAGES,
                step=1, key="overlay_count",
            )
            st.number_input(
                t("Super Chats & gifts shown in OBS overlay"), min_value=0, max_value=overlay_server.MAX_MESSAGES,
                step=1, key="overlay_sc_count",
                help=t("Super Chats, gifts and memberships are pinned to the top of the overlay, apart from regular chat, so busy chat never pushes them away. Set to 0 to hide them."),
            )
            st.toggle(t("Show usernames in OBS overlay"), key="overlay_show_username")
        with _set_r:
            overlay_text = st.text_area(
                t("Custom overlay message (shown permanently on stream)"),
                value=st.session_state["overlay_text"],
                height=80,
            )
            st.session_state["overlay_text"] = overlay_text
            st.session_state["overlay_visible"] = st.toggle(
                t("Show custom overlay message"), value=st.session_state["overlay_visible"]
            )
            st.text_input(
                t("Overlay channel"), key="overlay_channel", max_chars=40,
                help=t("Each dashboard user can pick their own channel name so their overlays don't overwrite each other. Letters, digits, - and _ only."),
            )
    overlay_count = int(st.session_state["overlay_count"])
    overlay_sc_count = int(st.session_state["overlay_sc_count"])

    _overlay_ch = overlay_server.clean_channel(st.session_state["overlay_channel"])
    if _overlay_ch == overlay_server.DEFAULT_CHANNEL:
        st.query_params.pop("overlay", None)
    else:
        st.query_params["overlay"] = _overlay_ch
    _loopback = ("127.0.0.1", "localhost", "::1")
    # Same machine name the browser used to reach this dashboard, minus the Streamlit port.
    _req_host = urlsplit("//" + (st.context.headers.get("Host") or "localhost")).hostname or "localhost"
    _req_host_url = f"[{_req_host}]" if ":" in _req_host else _req_host
    if OVERLAY_PUBLIC_URL:
        _overlay_base = OVERLAY_PUBLIC_URL
    else:
        _overlay_base = f"http://{_req_host_url}:{overlay_server.PORT}"
    # Remote browser + overlay server bound to loopback (e.g. Streamlit Community Cloud, which only exposes
    # the Streamlit port): OBS can't reach port 8502, so link to the dashboard's own ?view=overlay page.
    _via_dashboard = not OVERLAY_PUBLIC_URL and OVERLAY_HOST in _loopback and _req_host not in _loopback
    _dash_parts = urlsplit(st.context.url or "")
    _dash_base = (f"{_dash_parts.scheme}://{_dash_parts.netloc}{_dash_parts.path or '/'}"
                  if _dash_parts.netloc else f"http://{_req_host_url}/")

    def _overlay_link(query: str) -> str:
        if _via_dashboard:
            return _dash_base + "?view=overlay" + (f"&{query}" if query else "")
        return f"{_overlay_base}/overlay" + (f"?{query}" if query else "")
    _overlay_sites = [s for s in overlay_server.SITES if s in st.session_state["overlay_sites"]]
    if len(_overlay_sites) == len(overlay_server.SITES):
        _overlay_sites = []  # every site: keep the URL short
    _overlay_query = "&".join(
        ([f"ch={_overlay_ch}"] if _overlay_ch != overlay_server.DEFAULT_CHANNEL else [])
        + ([f"site={','.join(_overlay_sites)}"] if _overlay_sites else [])
    )
    _overlay_url = _overlay_link(_overlay_query)
    st.info(t(
        "**How to use**: Add a Browser Source in OBS pointing to `{url}`. "
        "Keep the dashboard open for live updates.", url=_overlay_url,
    ))
    if _via_dashboard:
        st.caption(t(
            "This server only lets browsers reach the dashboard's own address, so these overlay links open the "
            "dashboard in overlay-only mode (?view=overlay). If its background isn't transparent in OBS, add "
            "this to the Browser Source's Custom CSS: {css}",
            css="body, .stApp { background: transparent !important; }",
        ))
    elif OVERLAY_HOST in _loopback:
        if not OVERLAY_PUBLIC_URL and _req_host not in _loopback:
            st.warning(t(
                "This overlay URL uses the address you opened the dashboard with ({host}), but the overlay only "
                "accepts connections from this computer. Set OVERLAY_HOST=0.0.0.0 in .env and restart so OBS can load it.",
                host=_req_host,
            ))
        else:
            st.caption(t("The overlay only accepts connections from this computer. If OBS runs on another machine, set OVERLAY_HOST=0.0.0.0 in .env and restart."))

    # Standalone overlay: the overlay server reads the sites itself, no dashboard needed.
    _yt_source = st.session_state["yt_watch_channel"] or st.session_state["yt_chat_input"]
    _yt_channel = ytw.channel_url(_yt_source or "")
    if _yt_channel.startswith("https://www.youtube.com/@"):
        _yt_source = _yt_channel.rsplit("/", 1)[1]
    _standalone = {
        "youtube": (_yt_source or "").strip(),
        "bilibili": str(st.session_state["bili_room_id"] or "").strip(),
        "missevan": me.parse_room_id(str(st.session_state["me_room_id"] or "")),
    }
    _standalone = {k: v for k, v in _standalone.items() if v and (not _overlay_sites or k in _overlay_sites)}
    with _overlay_quick:
        st.markdown("**" + t("🖥️ Standalone overlay for OBS") + "**")
        if not _standalone:
            st.info(t("Enter a YouTube channel, Bilibili room or MissEvan room in the 📡 Stream Monitoring tab "
                      "to get your overlay link."))
    if _standalone:
        _params = dict(_standalone)
        if not st.session_state["overlay_show_username"]:
            _params["names"] = 0
        if st.session_state["translate_enabled"]:
            _params["tr"] = st.session_state["translate_target"]
        _text = {"text": overlay_text} if st.session_state["overlay_visible"] and overlay_text else {}
        # n= / sc= are always listed so they're easy to find and edit by hand in OBS. 0 turns a section off,
        # so Super Chats and chat can go on separate OBS screens, each using the whole Browser Source.
        _variants = [
            (t("All (Super Chats & gifts on top, chat below)"), {"n": overlay_count, "sc": overlay_sc_count, **_text}),
            (t("Super Chats & gifts only"), {"n": 0, "sc": overlay_sc_count or 3}),
            (t("Chat only"), {"n": overlay_count, "sc": 0, **_text}),
        ]
        with _overlay_quick:
            _links = [(_label, _overlay_link(urlencode({**_params, **_extra}, safe="@,"))) for _label, _extra in _variants]
            # With sc=0 in the settings, "All" is the same as "Chat only"; keep the clearer label.
            if _links[0][1] in {url for _, url in _links[1:]}:
                _links = _links[1:]
            for _i, (_label, _standalone_url) in enumerate(_links):
                st.caption(f"**{_label}**")
                _url_col, _open_col = st.columns([6, 1], vertical_alignment="center")
                _url_col.code(_standalone_url, language=None)
                _open_col.link_button(t("↗ Open"), _standalone_url, width="stretch", key=f"overlay_open_{_i}")
            st.caption(t(
                "Copy the link (point at it, then click the copy icon on its right). In OBS: Sources ＋ → Browser → paste it as the URL "
                "(Width 400, Height 600) → OK. It keeps working after you close this page, as long as the "
                "dashboard program is running. The overlay settings below change this link."
            ))
            st.caption(t(
                "Want Super Chats and chat in different places or scenes? Add one Browser Source with the "
                "\"Super Chats & gifts only\" link and another with the \"Chat only\" link."
            ))
            with st.expander(t("What can I change in this link?")):
                st.caption(t(
                    "This URL reads the chat by itself, like a logged-out viewer, as long as the overlay server runs — "
                    "you can close the dashboard. Edit the youtube= (@handle, channel or video link), bilibili= and "
                    "missevan= (room ID or link) values to show any channel. Options: n= chat lines, sc= Super Chats & gifts "
                    "(0 hides that part; the other then uses the whole height), "
                    "names=0 hides usernames, tr=en adds translations, text= custom message. "
                    "Bilibili hides viewer names from logged-out readers, so they appear masked."
                ))
                st.caption(t(
                    "While this dashboard is open and reading the same rooms, the standalone overlay shows exactly the "
                    "Recent Chat Preview below (your login, filters and blocked users included)."
                ))
    def _on_overlay(m: dict) -> bool:
        return not _overlay_sites or m.get("platform") in _overlay_sites

    overlay_paid = [
        m for m in st.session_state["paid_messages"] if m.get("text") and _on_overlay(m)
    ][-overlay_sc_count:] if overlay_sc_count else []

    st.divider()

    # Recent chat overlay preview
    st.markdown("#### " + t("Recent Chat Preview (last {n} messages)", n=overlay_count))
    recent = [
        m for m in st.session_state["chat_messages"]
        if m.get("type") in ("textMessageEvent", "danmaku") and m.get("text") and _on_overlay(m)
    ][-overlay_count:]
    if st.session_state["translate_enabled"]:
        tr.prefetch([m["text"] for m in overlay_paid + recent if m.get("type") != "gift"],
                    st.session_state["translate_target"])

    def _preview_row(m: dict, style: str) -> str:
        plat_color = {"youtube": "#ff4444", "missevan": "#ff7a45"}.get(m.get("platform", ""), "#23ade5")
        translated = (
            tr.get_translation(m["text"], st.session_state["translate_target"])
            if st.session_state["translate_enabled"] and m.get("type") != "gift" else ""
        )
        translation_html = f'<div style="color:#9fd3ff">{html_lib.escape(translated)}</div>' if translated else ""
        author_html = (
            f'<div style="color:{plat_color};font-weight:700;">{html_lib.escape(m.get("author", ""))}</div>'
            if st.session_state["overlay_show_username"] else ""
        )
        return (
            f'<div style="color:#fff;margin-bottom:4px;font-size:13px;{style}">'
            f'{author_html}'
            f'<div>{emotes.text_to_html(m["text"], m.get("emotes"), m.get("sticker_url", ""), m.get("sticker_caption", False))}</div>'
            f'{translation_html}'
            f"</div>"
        )

    preview_html = '<div style="background:rgba(0,0,0,0.7);padding:8px;border-radius:8px;width:360px;font-family:sans-serif;">'
    if overlay_paid:
        preview_html += '<div style="border-bottom:2px solid rgba(255,215,0,0.6);margin-bottom:8px;padding-bottom:4px;">'
        sc_style = "background:rgba(120,0,0,0.75);border-left:4px solid #ffd700;border-radius:6px;padding:4px 8px;"
        gift_style = "background:rgba(80,20,110,0.75);border-left:4px solid #ff8adf;border-radius:6px;padding:4px 8px;"
        for m in overlay_paid:
            preview_html += _preview_row(m, gift_style if m.get("type") == "gift" else sc_style)
        preview_html += "</div>"
    for m in recent:
        preview_html += _preview_row(m, "")
    if st.session_state["overlay_visible"] and overlay_text:
        preview_html += (
            f'<div style="color:#ffd700;font-weight:700;margin-top:8px;border-top:1px solid #555;padding-top:6px;">'
            f'{html_lib.escape(overlay_text)}'
            f"</div>"
        )
    preview_html += "</div>"
    st.markdown(preview_html, unsafe_allow_html=True)

    try:
        overlay_server.ensure_started().publish(overlay_server.snapshot(
            st.session_state["chat_messages"],
            st.session_state["translate_enabled"],
            st.session_state["translate_target"],
            tr.get_translation,
            overlay_text if st.session_state["overlay_visible"] else "",
            st.session_state["overlay_show_username"],
            overlay_count,
            overlay_sc_count,
            st.session_state["paid_messages"],
        ), _overlay_ch, source=overlay_server.overlay_feeds.parse_key(
            {site: [value] for site, value in _standalone.items()}
        ))
    except OSError as exc:
        st.error(t("Couldn't start the chat overlay on port {port}: {err}", port=overlay_server.PORT, err=str(exc)))

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_analytics:
    st.subheader(t("📊 Stream Analytics"))

    history = st.session_state["viewer_history"]
    all_msgs = st.session_state["chat_messages"]

    # ── Viewer count chart ────────────────────────────────────────────────────
    if history:
        df_v = pd.DataFrame(history)
        fig = go.Figure()
        if "YouTube" in df_v.columns:
            fig.add_trace(go.Scatter(x=df_v["time"], y=df_v["YouTube"], name="YouTube", line=dict(color="#ff0000")))
        if "Bilibili" in df_v.columns:
            fig.add_trace(go.Scatter(x=df_v["time"], y=df_v["Bilibili"], name="Bilibili", line=dict(color="#23ade5")))
        if "MissEvan" in df_v.columns:
            fig.add_trace(go.Scatter(x=df_v["time"], y=df_v["MissEvan"].fillna(0), name="MissEvan", line=dict(color="#ff7a45")))
        fig.update_layout(title=t("Viewer Count Over Time"), xaxis_title=t("Time"), yaxis_title=t("Viewers"), template="plotly_dark", height=300)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info(t("Viewer history will appear here once streaming starts."))

    # ── Chat statistics ───────────────────────────────────────────────────────
    if all_msgs:
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        yt_msgs  = [m for m in all_msgs if m.get("platform") == "youtube"]
        bi_msgs  = [m for m in all_msgs if m.get("platform") == "bilibili"]
        me_msgs  = [m for m in all_msgs if m.get("platform") == "missevan"]
        sc_msgs  = [m for m in all_msgs if "super" in m.get("type","").lower()]
        col_stat1.metric(t("Total messages"), len(all_msgs))
        col_stat2.metric(t("YouTube messages"), len(yt_msgs))
        col_stat3.metric(t("Bilibili danmaku"), len(bi_msgs))
        col_stat4.metric(t("MissEvan messages"), len(me_msgs))

        st.metric(t("Super Chats / SC"), len(sc_msgs))

        # ── Message rate chart ────────────────────────────────────────────────
        st.subheader(t("Message Rate (per minute)"))
        try:
            df_m = pd.DataFrame(all_msgs)
            # Bilibili/MissEvan use epoch-second strings, YouTube uses ISO 8601.
            raw_ts = df_m["timestamp"].fillna("").astype(str)
            is_epoch = raw_ts.str.fullmatch(r"\d+")
            df_m["ts"] = pd.to_datetime(raw_ts.where(~is_epoch), format="ISO8601", errors="coerce", utc=True)
            df_m.loc[is_epoch, "ts"] = pd.to_datetime(
                pd.to_numeric(raw_ts[is_epoch]), unit="s", utc=True
            )
            df_m = df_m.dropna(subset=["ts"])
            if not df_m.empty:
                df_m = df_m.set_index("ts").sort_index()
                rate = df_m.resample("1min").size().rename("messages")
                fig2 = go.Figure(go.Bar(x=rate.index.strftime("%H:%M"), y=rate.values, marker_color="#7c4dff"))
                fig2.update_layout(title=t("Messages per Minute"), template="plotly_dark", height=250)
                st.plotly_chart(fig2, width="stretch")
        except Exception:
            pass

        # ── Top chatters ──────────────────────────────────────────────────────
        st.subheader(t("Top Chatters"))
        df_c = pd.DataFrame(all_msgs)
        if "author" in df_c.columns:
            top = (
                df_c.groupby(["author", "platform"])
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
                .head(15)
            )
            st.dataframe(top, width="stretch", hide_index=True)
    else:
        st.info(t("Chat stats will appear once messages arrive."))

    # ── Hotspots for clipping ─────────────────────────────────────────────────
    st.subheader(t("🔥 Hotspots for clipping"))
    st.caption(t(
        "Moments when chat, gifts and Super Chats spike well above this stream's usual activity, timed from "
        "the stream start so you can cut them from the recording. Covers messages received while this "
        "dashboard page is open."
    ))
    _log = st.session_state["activity_log"]
    if not _log:
        st.info(t("Hotspots will appear once messages arrive."))
    else:
        _site_names = {"youtube": "YouTube", "bilibili": "Bilibili", "missevan": t("MissEvan")}
        _origins = {f"site:{s}": v for s, v in st.session_state["stream_starts"].items()}
        _origins["first"] = min(e["ts"] for e in _log)
        # A remembered choice can vanish (e.g. that site's stream start is gone after a reconnect).
        if st.session_state.get("hl_origin") not in (*_origins, "custom"):
            st.session_state["hl_origin"] = "first"
        hc = st.columns(4)
        _origin_key = hc[0].selectbox(
            t("Time 0 (start of the recording)"), [*_origins, "custom"],
            format_func=lambda k: t("{site} stream start", site=_site_names.get(k[5:], k[5:])) if k.startswith("site:")
            else t("First message received") if k == "first" else t("Custom clock time"),
            key="hl_origin",
            help=t("Clip times count from here. Pick the site whose recording you are cutting."),
        )
        if _origin_key == "custom":
            _tz = _chat_tz()
            _first_local = datetime.fromtimestamp(_origins["first"], tz=_tz or datetime.now().astimezone().tzinfo)
            _clock = hc[0].time_input(t("Recording started at"), value=_first_local.time().replace(microsecond=0),
                                      step=1, key="hl_origin_clock")
            _origin = _first_local.replace(hour=_clock.hour, minute=_clock.minute, second=_clock.second).timestamp()
        else:
            _origin = _origins.get(_origin_key, _origins["first"])
        _window = hc[1].number_input(t("Window (seconds)"), 10, 300, 30, step=10, key="hl_window")
        _sens = hc[2].slider(t("Sensitivity"), 1.0, 5.0, 2.0, 0.5, key="hl_sens",
                             help=t("How far above the usual activity a moment must be. Higher = fewer, bigger hotspots."))
        _top = hc[3].number_input(t("Max hotspots"), 1, 100, 20, key="hl_top")
        rc = st.columns(4)
        _pre = rc[0].number_input(t("Lead-in (seconds)"), 0, 300, 20, step=5, key="hl_pre",
                                  help=t("Chat reacts after the moment happens, so clips start this much earlier."))
        _post = rc[1].number_input(t("Tail (seconds)"), 0, 300, 10, step=5, key="hl_post")
        _fps = rc[2].selectbox(t("EDL frame rate"), [30, 60, 25, 50, 24], key="hl_fps")
        _hour = rc[3].selectbox(t("EDL timeline start"), [0, 1], index=1, key="hl_hour",
                                format_func=lambda h: f"{h:02d}:00:00:00",
                                help=t("DaVinci Resolve timelines start at 01:00:00:00 by default."))

        clips = hl.find_highlights(_log, window=int(_window), sensitivity=float(_sens), top=int(_top),
                                   pre_roll=int(_pre), post_roll=int(_post))
        if not clips:
            st.info(t("No hotspots yet — chat hasn't spiked above its usual level. Try a lower sensitivity."))
        else:
            _tz = _chat_tz()

            def _clock_str(epoch: float) -> str:
                return datetime.fromtimestamp(epoch, tz=_tz or datetime.now().astimezone().tzinfo).strftime("%H:%M:%S")

            rows = [{
                "#": n,
                t("Start"): hl.offset(c["start"] - _origin),
                t("End"): hl.offset(c["end"] - _origin),
                t("Length (s)"): int(c["end"] - max(c["start"], _origin)),
                t("Peak"): hl.offset(c["peak"] - _origin),
                t("Clock time"): _clock_str(c["start"]),
                t("Heat"): c["score"],
                t("Messages"): c["chat"],
                t("Gifts / SC"): c["paid"],
                t("Sites"): ", ".join(_site_names.get(p, p) for p in c["platforms"]),
                t("Hot phrases"): hl.summary(c),
            } for n, c in enumerate(clips, 1)]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            _stamp = datetime.fromtimestamp(_origin).strftime("%Y%m%d_%H%M")
            _txt = "\n".join(
                f'{r[t("Start")]} - {r[t("End")]}  #{r["#"]}  {t("Heat")} {r[t("Heat")]} · '
                f'{t("Messages")} {r[t("Messages")]} · {t("Gifts / SC")} {r[t("Gifts / SC")]}  {r[t("Hot phrases")]}'
                for r in rows
            ) + "\n"
            dc = st.columns(3)
            dc[0].download_button(t("⬇️ CSV (Excel)"), hl.to_csv(rows), f"hotspots_{_stamp}.csv",
                                  "text/csv", width="stretch")
            dc[1].download_button(t("⬇️ Timestamps (.txt)"), _txt.encode("utf-8"), f"hotspots_{_stamp}.txt",
                                  "text/plain", width="stretch")
            dc[2].download_button(t("⬇️ Markers (.edl)"),
                                  hl.to_edl(clips, _origin, fps=int(_fps), hour=int(_hour), title=f"Hotspots {_stamp}"),
                                  f"hotspots_{_stamp}.edl", "text/plain", width="stretch")
            st.caption(t(
                "EDL: in DaVinci Resolve, put the recording on a timeline, then right-click the timeline in the "
                "Media Pool > Timelines > Import > Timeline Markers from EDL. Each hotspot becomes a red marker "
                "spanning the clip."
            ))

    # ── Blocked message log ───────────────────────────────────────────────────
    with st.expander(t("🛡️ Filtered / blocked messages")):
        blocked = st.session_state["blocked_msgs"]
        if blocked:
            for m in reversed(blocked[-50:]):
                st.markdown(
                    f"**{m.get('author','')}**: {m.get('text','')} "
                    f"— <span style='color:#f44;'>{m.get('filter_reason','')}</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.info(t("No blocked messages."))

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: FILTERS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_filters:
    filt: ChatFilter = st.session_state["filter"]
    st.subheader(t("🛡️ Chat Filters"))

    col_kw, col_user = st.columns(2)

    with col_kw:
        st.markdown("#### " + t("Keyword / Regex Block Patterns"))
        st.caption(t("Each pattern is a Python regex (case-insensitive by default)."))
        patterns = filt.block_patterns
        if patterns:
            for pat in patterns:
                c1, c2 = st.columns([8, 1])
                c1.code(pat)
                if c2.button("✕", key=f"del_pat_{pat}"):
                    filt.remove_block_pattern(pat)
                    st.rerun()
        else:
            st.info(t("No keyword filters."))

        with st.form("add_pattern", clear_on_submit=True):
            new_pat = st.text_input(t("New pattern (regex)"))
            if st.form_submit_button(t("Add")) and new_pat:
                filt.add_block_pattern(new_pat)
                st.rerun()

        st.markdown("#### " + t("Allow Patterns (override block)"))
        for pat in filt.allow_patterns:
            c1, c2 = st.columns([8, 1])
            c1.code(pat)
            if c2.button("✕", key=f"del_allow_{pat}"):
                filt.remove_allow_pattern(pat)
                st.rerun()
        with st.form("add_allow_pattern", clear_on_submit=True):
            new_allow = st.text_input(t("New allow pattern"))
            if st.form_submit_button(t("Add allow pattern")) and new_allow:
                filt.add_allow_pattern(new_allow)
                st.rerun()

    with col_user:
        st.markdown("#### " + t("Blocked Users"))
        st.caption(t("Saved to chat_filters.json and kept after restarting the app."))
        blocked = filt.blocked_users
        blocked_names = filt.blocked_names
        if blocked or blocked_names:
            for key, name in sorted(blocked.items(), key=lambda kv: (kv[1] or kv[0]).lower()):
                platform, _, uid = key.rpartition(":")
                site = _PLATFORM_NAMES.get(platform, t("Any platform"))
                c1, c2 = st.columns([8, 1], vertical_alignment="center")
                c1.markdown(f"**{html_lib.escape(name) or '—'}** · {site} · `{uid}`")
                if c2.button("✕", key=f"del_uid_{key}", help=t("Unblock")):
                    filt.unblock_user(key)
                    st.rerun()
            for name in blocked_names:
                c1, c2 = st.columns([8, 1], vertical_alignment="center")
                c1.markdown(f"**{html_lib.escape(name)}** · {t('by name')}")
                if c2.button("✕", key=f"del_name_{name}", help=t("Unblock")):
                    filt.unblock_name(name)
                    st.rerun()
        else:
            st.info(t("No blocked users."))

        with st.form("block_user_form", clear_on_submit=True):
            new_uid = st.text_input(t("Block by user ID / channel ID"))
            if st.form_submit_button(t("Block")) and new_uid:
                filt.block_user(new_uid)
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: COOKIES
# ═══════════════════════════════════════════════════════════════════════════════

def _cookie_verify(site_label: str, cookies: dict) -> Optional[dict]:
    if site_label == "Bilibili":
        return bc.verify_bilibili_login(cookies) if "SESSDATA" in cookies else None
    if site_label == "MissEvan":
        return me.verify_login(cookies) if cookies else None
    return ytw.verify_login(cookies) if cookies else None


_COOKIE_SITES = {"YouTube": "youtube", "Bilibili": "bilibili", "MissEvan": "missevan"}


def _saved_login(site: str) -> Optional[dict]:
    """{"ok", "name"} for the current user's saved login on `site`, or None when there is none."""
    if not user_login.get(site):
        return None
    if site == "youtube":
        state, name_key = _cached_yt_cookie_login(_login_key("youtube"), ytw.selected_page_id()), "name"
    elif site == "bilibili":
        state, name_key = _cached_bili_login(_login_key("bilibili")), "uname"
    else:
        state, name_key = _me_login_state() or {}, "username"
    return {"ok": bool(state.get("is_login")), "name": state.get(name_key, ""),
            "unknown": bool(state.get("error"))}


def _clear_all_logins() -> None:
    for site in _COOKIE_SITES.values():
        bc.clear_login(site)
    for key in ("_yt_saved_name", "_yt_saved_msg", "_me_saved_msg", "_me_saved_uid", "yt_send_as"):
        st.session_state.pop(key, None)
    st.toast(t("Deleted all your logins."))


def _read_pasted_cookies(raw: str) -> None:
    """Pick the site, then parse and verify pasted cookies; the outcome goes to session state."""
    raw = raw or ""
    detected = bc.detect_site(raw) if raw.strip() else None
    if detected:
        st.session_state["cookie_site"] = detected
    site_label = st.session_state.get("cookie_site") or next(iter(bc.SITES))
    if (raw, site_label) == st.session_state.get("_cookie_last_raw") and st.session_state.get("cookie_result"):
        return  # already read (e.g. the box lost focus, then Read cookies was clicked)
    st.session_state.pop("cookie_result", None)
    st.session_state.pop("_cookie_error", None)
    st.session_state["_cookie_last_raw"] = (raw, site_label)
    if not raw.strip():
        return
    try:
        cookies = bc.parse_cookie_text(raw, bc.SITES[site_label])
        if not cookies:
            raise bc.CookieReadError(t("No cookies for {site} found in that text.", site=site_label))
        st.session_state["cookie_result"] = {
            "browser": t("the pasted cookies"), "site": site_label, "cookies": cookies,
            "verify": _cookie_verify(site_label, cookies),
        }
    except bc.CookieReadError as exc:
        st.session_state["_cookie_error"] = str(exc)


def _on_cookie_read() -> None:
    uploaded = st.session_state.get("cookie_upload")
    raw = (uploaded.getvalue().decode("utf-8", errors="replace") if uploaded
           else st.session_state.get("cookie_paste", ""))
    _read_pasted_cookies(raw)


def _clear_cookie_box() -> None:
    st.session_state["cookie_paste"] = ""
    for key in ("cookie_result", "_cookie_error", "_cookie_last_raw"):
        st.session_state.pop(key, None)


_CLIPBOARD_JS = """
export default function(component) {
    const { setTriggerValue, parentElement, data } = component;
    const button = parentElement.querySelector("button");
    button.textContent = data.label;
    button.onclick = async () => {
        try {
            setTriggerValue("text", await navigator.clipboard.readText());
        } catch (err) {
            setTriggerValue("error", String((err && err.name) || err));
        }
    };
}
"""
_CLIPBOARD_CSS = """
button { font: inherit; color: #fff; background: #ff4b4b; border: 1px solid #ff4b4b; border-radius: .5rem;
         padding: .25rem .75rem; min-height: 2.5rem; cursor: pointer; }
button:hover { background: #ff3333; border-color: #ff3333; }
"""


@st.cache_resource
def _clipboard_paste_button():
    # A real click in the page: browsers only allow reading the clipboard on a user gesture.
    return st.components.v2.component("clipboard_paste", html="<button type='button'></button>",
                                      css=_CLIPBOARD_CSS, js=_CLIPBOARD_JS)


with tab_cookies:
    st.subheader(t("🍪 Import login cookies"))
    st.caption(t(
        "Your logins are yours only: other people opening this dashboard don't see or use them. "
        "They are kept encrypted in this browser, so they survive a refresh; use 🚪 Clear login to forget them."
    ))

    # ── Saved logins with quick delete ────────────────────────────────────────
    st.markdown("**" + t("🔑 Your saved logins") + "**")
    _any_saved = False
    for _col, (_label, _site) in zip(st.columns(len(_COOKIE_SITES)), _COOKIE_SITES.items()):
        _saved = _saved_login(_site)
        _any_saved = _any_saved or _saved is not None
        with _col.container(border=True):
            if _saved is None:
                _line = t("— not logged in")
            elif _saved["ok"]:
                _line = "✅ " + (_saved["name"] or t("logged in"))
            elif _saved["unknown"]:
                _line = t("❔ saved (couldn't check)")
            else:
                _line = t("⚠️ expired")
            st.markdown(f"**{_label}** · {_line}")
            st.button(
                t("🗑️ Delete"), key=f"cookie_delete_{_site}", disabled=_saved is None, width="stretch",
                on_click=_clear_login, args=(_label, _site),
                help=t("Forget your login cookies for this site (also removed from this browser)."),
            )
    if _any_saved:
        st.button(t("🗑️ Delete all logins"), key="cookie_delete_all", type="tertiary", on_click=_clear_all_logins)

    st.divider()
    _src_browser, _src_paste = t("🧭 Browser on this computer"), t("📋 Paste / upload cookies")
    # Reading a browser's cookie store means the *server's* browser, so only offer it to the server's own user.
    _cookie_sources = [_src_browser, _src_paste] if _is_local_client() else [_src_paste]
    cookie_source = st.radio(
        t("Source"), _cookie_sources, key="cookie_source", horizontal=True,
        help=t("Use Paste / upload when the app runs on another computer or a server, "
               "where it can't see your browser."),
    )

    if cookie_source == _src_paste:
        st.caption(t(
            "In your own browser, export the site's cookies with an extension such as "
            "\"Get cookies.txt LOCALLY\" or \"Cookie-Editor\" (Export → JSON or Netscape), or copy the "
            "Cookie request header from DevTools (F12 → Network → any request to the site). "
            "Then click 📋 Paste from clipboard — the site is detected and the cookies are checked right away."
        ))
        _paste_row = st.container(horizontal=True, vertical_alignment="center")
        with _paste_row:
            _clip = _clipboard_paste_button()(
                key="cookie_clip", data={"label": t("📋 Paste from clipboard")}, width="content",
                on_text_change=lambda: None, on_error_change=lambda: None,
            )
            st.button(t("🧹 Clear box"), key="cookie_clear_box", on_click=_clear_cookie_box)
        if _clip.get("text") is not None:
            st.session_state["cookie_paste"] = _clip["text"]
            st.session_state.pop("_cookie_last_raw", None)
            _read_pasted_cookies(_clip["text"])
        elif _clip.get("error"):
            st.warning(t("This browser didn't allow reading the clipboard. Click in the box below and press "
                         "Ctrl+V instead."))
    site_label = st.selectbox(
        t("Site"), list(bc.SITES), key="cookie_site",
        help=t("Picked automatically when the pasted cookies show which site they are for."),
    )

    if cookie_source == _src_paste:
        st.text_area(t("Cookies"), key="cookie_paste", height=120, on_change=_on_cookie_read,
                     placeholder="SESSDATA=…; bili_jct=…   /   cookies.txt   /   [{\"name\": …}]")
        st.file_uploader(t("…or upload an exported file"), type=["txt", "json"], key="cookie_upload",
                         on_change=_on_cookie_read)
        st.button(t("Read cookies"), type="primary", key="cookie_parse", on_click=_on_cookie_read)
        if st.session_state.get("_cookie_error"):
            st.error(st.session_state["_cookie_error"])
    elif not bc.BROWSER_COOKIE_LIB_OK:
        st.error(t("browser-cookie3 is not installed. Run `pip install browser-cookie3`."))
    else:
        st.caption(t(
            "Reads cookies from a browser installed on this computer. Values never leave this "
            "machine except when verifying the login with the site itself."
        ))
        browser_label = st.selectbox(t("Browser"), list(bc.BROWSERS), key="cookie_browser")
        st.caption(t(
            "Chrome/Edge on Windows encrypt cookies with app-bound encryption and may require "
            "running the app as administrator. Firefox works without elevation. Close the "
            "browser if its cookie database is locked."
        ))

        if st.button(t("Read cookies"), type="primary"):
            try:
                cookies = bc.read_cookies(bc.BROWSERS[browser_label], bc.SITES[site_label])
                st.session_state["cookie_result"] = {
                    "browser": browser_label, "site": site_label, "cookies": cookies,
                    "verify": _cookie_verify(site_label, cookies),
                }
            except bc.CookieReadError as exc:
                st.session_state.pop("cookie_result", None)
                st.error(str(exc))

    result = st.session_state.get("cookie_result")
    if result:
        cookies = result["cookies"]
        st.markdown(t("**{n} cookies** found for {site} in {browser}.", n=len(cookies), site=result["site"], browser=result["browser"]))

        if result["site"] == "Bilibili":
            rows = [
                {t("Cookie"): name, t("Value"): bc.mask(cookies[name]) if name in cookies else t("❌ missing")}
                for name in bc.BILIBILI_LOGIN_COOKIES
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

            verify = result["verify"]
            if verify and verify["is_login"]:
                st.success(t("Logged in as **{uname}** (UID {mid}).", uname=verify["uname"], mid=verify["mid"]))
            elif verify:
                st.warning(t("Bilibili reports these cookies are not logged in (expired or signed out)."))
            else:
                st.warning(t("No SESSDATA cookie found — log in to bilibili.com in this browser first."))

            if "SESSDATA" in cookies and "bili_jct" in cookies:
                if st.button(t("✅ Use these cookies"), key="bili_save_browser"):
                    bc.save_bilibili_credentials(cookies)
                    msg = _cookie_applied_msg()
                    old = st.session_state.get("bili_listener")
                    if old:
                        # Credentials are bound at connect time, so reconnect to use the new login.
                        old.stop()
                        new_listener = bili.DanmakuListener(str(old.room_id))
                        if new_listener.start():
                            st.session_state["bili_listener"] = new_listener
                            msg += t(" Bilibili listener reconnected with the new login.")
                    st.success(msg)
        elif result["site"] == "MissEvan":
            _render_missevan_verify(result["verify"], cookies, "me_save_browser")
        else:
            found = [name for name in bc.YOUTUBE_LOGIN_COOKIES if name in cookies]
            verify = result["verify"]
            if verify and verify["is_login"]:
                st.success(t("Logged in to YouTube as **{name}**.", name=verify["name"]))
                if st.button(t("✅ Use these cookies"), key="yt_save_browser"):
                    ytw.save_login(cookies)
                    st.session_state["_yt_saved_name"] = verify["name"]
                    st.session_state["_yt_saved_msg"] = _cookie_applied_msg()
                if st.session_state.get("_yt_saved_name") == verify["name"]:
                    st.success(st.session_state.get("_yt_saved_msg", "") + " "
                               + t("You can now send YouTube chat."))
                st.caption(t(
                    "Cookie login is unofficial (it works like youtube.com itself) and may break if YouTube "
                    "changes it."
                ))
            elif verify and verify.get("error"):
                st.error(verify["error"])
            elif found:
                st.warning(t("YouTube reports these cookies are not logged in (expired or signed out)."))
            else:
                st.warning(t("No YouTube login cookies found — log in to youtube.com in this browser first."))

        with st.expander(t("All cookie names (values masked)")):
            st.dataframe(
                pd.DataFrame([{t("Cookie"): k, t("Value"): bc.mask(v)} for k, v in sorted(cookies.items())]),
                hide_index=True,
                width="stretch",
            )

_read_saved_settings()
_sync_login_cookie()
_save_settings()
_emit_live_alerts()
_emit_browser_tts()

# ──────────────────────────────────────────────────────────────────────────────
# Auto-refresh: a browser-side timer reruns the app. Sleeping + st.rerun() on the
# server would swallow button clicks made while the script was sleeping.
# ──────────────────────────────────────────────────────────────────────────────
@st.fragment(run_every=CHAT_POLL_INTERVAL)
def _auto_refresh():
    if st.session_state.pop("_full_run", False):
        return  # part of a normal full run; only the timer ticks should rerun the app
    st.rerun()


st.session_state["_full_run"] = True
_auto_refresh()
