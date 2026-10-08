"""
Streaming Dashboard – main Streamlit application.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import html as html_lib
import time
from datetime import datetime
from typing import Optional

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
from src import i18n
from src import missevan as me
from src import obs_ctrl as obs
from src import reading
from src import translate as tr
from src import youtube as yt
from src import youtube_web as ytw
from src.config import CHAT_POLL_INTERVAL, MISSEVAN_ROOM_ID
from src.filters import ChatFilter, make_default_filter
from src.tts import (
    LANGUAGES as TTS_LANGUAGES, format_announcement, format_message, is_emoji_only, is_paid,
    matches_language, speak, speak_async, strip_emoji,
)

# ──────────────────────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* Chat bubbles */
.chat-bubble {
    padding: 6px 10px;
    border-radius: 8px;
    margin-bottom: 4px;
    font-size: 0.88rem;
    line-height: 1.4;
    word-break: break-word;
}
.chat-yt   { background: #1a1a2e; border-left: 3px solid #ff0000; }
.chat-bili { background: #1a1a2e; border-left: 3px solid #23ade5; }
.chat-me   { background: #1a1a2e; border-left: 3px solid #ff7a45; }
.chat-gift { background: #2a1a2e !important; }
.chat-thanked { opacity: 0.45; }
.chat-mod  { border-left-color: #ffd700 !important; }
.chat-sc   { background: #3a1a00 !important; border-left-color: #ff6600 !important; }
.chat-superchat { background: #3a0000 !important; border-left-color: #ff0000 !important; }
.chat-translation {
    margin-top: 3px;
    padding-top: 3px;
    border-top: 1px dashed #444;
    color: #9fd3ff;
    font-size: 0.84rem;
}
.chat-translation.pending { color: #777; font-style: italic; }
.chat-reading { line-height: 2.2; }
.chat-reading rt { font-size: 0.62em; color: #ffcc80; letter-spacing: 0; }
.badge {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 4px;
    margin-right: 4px;
    vertical-align: middle;
}
.badge-yt   { background:#ff0000; color:#fff; }
.badge-bili { background:#23ade5; color:#fff; }
.badge-me   { background:#ff7a45; color:#fff; }
.badge-mod  { background:#ffd700; color:#000; }
.badge-owner{ background:#cc0000; color:#fff; }
.badge-sc   { background:#ff6600; color:#fff; }
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
/* ── Responsive layout (PC + tablet) ── */
[data-testid="stMainBlockContainer"] {
    padding: 2.5rem 1.5rem 1rem;
    max-width: 100%;
}
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
/* Gifts header + "Mark all" button may wrap to two lines */
.st-key-paid_feed {
    height: calc(100dvh - 420px) !important;
    max-height: calc(100dvh - 420px) !important;
}
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
    [data-testid="stMainBlockContainer"] { padding: 2.5rem 0.75rem 1rem; }
    .chat-bubble { font-size: 0.85rem; padding: 5px 8px; }
}
/* Touch screens: bigger tap targets */
@media (hover: none) and (pointer: coarse) {
    .st-key-chat_feed button, .st-key-paid_feed button { min-height: 2.6rem; min-width: 2.6rem; }
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

def _init_state():
    defaults = {
        "chat_messages": [],          # unified list of all chat messages
        "yt_page_token": "",
        "bili_listener": None,
        "filter": make_default_filter(),
        "blocked_msgs": [],
        "paid_messages": [],          # gifts / Super Chats, kept apart so chat trimming can't drop them
        "thanked_ids": set(),
        "tts_enabled": False,
        "tts_rate": 150,
        "tts_volume": 1.0,
        "tts_lang": "auto",
        "tts_translate": False,
        "tts_skip_name": False,
        "tts_announce_paid": True,
        "tts_skip_emoji": True,
        "translate_enabled": False,
        "translate_target": "en",
        "sc_reading": "auto",
        "show_enter_events": False,
        "max_chat_display": 200,
        "selected_chat_id": "",
        "yt_chat_input": "",
        "yt_chat_error": "",
        "bili_room_id": "",
        "me_listener": None,
        "me_room_id": MISSEVAN_ROOM_ID,
        "overlay_text": "",
        "overlay_visible": False,
        "last_poll": 0.0,
        "viewer_history": [],         # list of {time, yt, bili}
        "yt_auth_url": "",
        "yt_auth_code": "",
        # ?lang=zh in the URL lets a bookmark or refresh keep the chosen page language.
        "ui_lang": st.query_params.get("lang", "en") if st.query_params.get("lang") in i18n.UI_LANGUAGES else "en",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def t(text: str, **kwargs) -> str:
    return i18n.translate(text, st.session_state["ui_lang"], **kwargs)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _platform_badge(msg: dict) -> str:
    p = msg.get("platform", "")
    if p == "youtube":
        return '<span class="badge badge-yt">YT</span>'
    if p == "missevan":
        return '<span class="badge badge-me">猫耳</span>'
    return '<span class="badge badge-bili">bili</span>'


def _role_badges(msg: dict) -> str:
    parts = []
    if msg.get("is_owner"):
        parts.append('<span class="badge badge-owner">OWNER</span>')
    if msg.get("is_moderator"):
        parts.append('<span class="badge badge-mod">MOD</span>')
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


def _fmt_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except Exception:
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%H:%M:%S")
        except Exception:
            return ts


_RENDER_KEYS: dict[str, int] = {}  # app.py re-executes every run, so this resets per run


def _set_thanked(msg_ids: list[str], thanked: bool):
    ids: set = st.session_state["thanked_ids"]
    if thanked:
        ids.update(msg_ids)
    else:
        ids.difference_update(msg_ids)


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
    author = html_lib.escape(msg.get("author", ""))
    text = msg.get("text", "")
    text_html = html_lib.escape(text)
    if "super" in msg.get("type", "").lower():
        annotated = reading.annotate_html(text, st.session_state["sc_reading"])
        if annotated:
            text_html = f'<span class="chat-reading">{annotated}</span>'
    translation_html = ""
    if st.session_state["translate_enabled"] and text and msg.get("type") != "enter":
        translated = tr.get_translation(text, st.session_state["translate_target"])
        if translated is None:
            translation_html = f'<div class="chat-translation pending">🌐 {t("translating…")}</div>'
        elif translated:
            translation_html = f'<div class="chat-translation">🌐 {html_lib.escape(translated)}</div>'
    html = (
        f'<div class="chat-bubble {bubble}">'
        f'{badges}'
        f'<span style="color:#aaa;font-size:0.75rem;">[{ts}]</span> '
        f'<strong>{author}</strong>: {text_html}'
        f"{translation_html}"
        f"</div>"
    )
    if thank:
        col1, col_thank, col2, col3 = st.columns([7, 1, 1, 1])
        with col_thank:
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
        if st.button("🚫", key=f"ban_{wkey}", help=t("Ban/block user")):
            st.session_state["_pending_ban"] = msg


def _play_tts(text: str, lang: str):
    """Speak now; in gTTS mode keep the clip so the browser player survives auto-refresh."""
    audio = speak(
        text,
        rate=st.session_state["tts_rate"],
        volume=st.session_state["tts_volume"],
        lang=lang,
    )
    if audio:
        st.session_state["_tts_audio"] = audio


def _tts_translating() -> bool:
    """Read translations only when the TTS language is the same as the "Translate to" language."""
    return (
        st.session_state["tts_translate"]
        and st.session_state["tts_lang"] == st.session_state["translate_target"].split("-")[0]
    )


def _speech_for(text: str, src_lang: str) -> tuple[str, str]:
    """(text to speak, voice language). With "Read translated chat" active, speak the translation."""
    if not _tts_translating():
        return text, src_lang
    translated = tr.get_translation(text, st.session_state["translate_target"])
    if translated:
        return translated, st.session_state["tts_lang"]
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
    if not matches_language(text, lang) and not _tts_translating():
        lang = "auto"  # manual replay reads any message, in its own language
    if _tts_translating() and msg.get("type") != "gift":
        tr.prefetch([text], st.session_state["translate_target"], wait=3.0)
        text, lang = _speech_for(text, lang)
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

    # TTS
    if st.session_state["tts_enabled"]:
        skip_emoji = st.session_state["tts_skip_emoji"]
        announce_paid = st.session_state["tts_announce_paid"]
        translating = _tts_translating()
        to_speak: list[tuple[dict, str]] = []
        for m in allowed:
            if m["id"] in history_ids or m.get("history"):
                continue
            paid = announce_paid and is_paid(m)
            if paid or m.get("type") in ("textMessageEvent", "danmaku"):
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
        if to_speak and translating:
            tr.prefetch([text for _, text in to_speak], st.session_state["translate_target"], wait=3.0)
        # Paid events first, so a burst of chat in the same poll can't delay them.
        to_speak.sort(key=lambda item: not (announce_paid and is_paid(item[0])))
        for m, text in to_speak:
            paid = announce_paid and is_paid(m)
            if m.get("type") == "gift":
                lang = "auto"  # gift names are product names; translating them gives nonsense
            else:
                text, lang = _speech_for(text, st.session_state["tts_lang"])
            speak_async(
                format_announcement(m["type"], m["author"], text, lang) if paid
                else _chat_line(m["author"], text, lang),
                rate=st.session_state["tts_rate"],
                volume=st.session_state["tts_volume"],
                lang=lang,
                priority=paid,
            )

    # Update history (skip enter events if hidden)
    show_enter = st.session_state["show_enter_events"]
    for m in allowed:
        if is_paid(m):
            st.session_state["paid_messages"].append(m)
        if not show_enter and m.get("type") == "enter":
            continue
        st.session_state["chat_messages"].append(m)
    if len(st.session_state["paid_messages"]) > 1000:
        st.session_state["paid_messages"] = st.session_state["paid_messages"][-1000:]

    st.session_state["blocked_msgs"].extend(blocked)

    # Cap history
    max_disp = st.session_state["max_chat_display"]
    if len(st.session_state["chat_messages"]) > max_disp * 2:
        st.session_state["chat_messages"] = st.session_state["chat_messages"][-max_disp:]


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


@st.cache_data(ttl=30, show_spinner=False)
def _cached_room_info(room_id: str) -> dict:
    return bili.get_room_info(room_id)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_me_room_info(room_id: str) -> dict:
    return me.get_room_info(room_id)


def _render_missevan_verify(verify: Optional[dict], cookies: dict, key: str):
    if verify and verify["is_login"]:
        st.success(t("Logged in as **{uname}** (UID {mid}).", uname=verify["username"], mid=verify["user_id"]))
        if st.button(t("💾 Save to .env and apply"), key=key):
            me.save_login(cookies)
            st.session_state["_me_saved_uid"] = verify["user_id"]
        if st.session_state.get("_me_saved_uid") == verify["user_id"]:
            st.success(t("Saved MISSEVAN_COOKIE to .env — you can now send chat to MissEvan."))
    elif verify and verify.get("error"):
        st.error(verify["error"])
    else:
        st.warning(t("MissEvan reports these cookies are not logged in — log in at fm.missevan.com first."))


def _status_badge(is_live: bool, detail: str = ""):
    dot, label = ("dot-live", t("LIVE")) if is_live else ("dot-offline", t("Offline"))
    suffix = f" · {detail}" if detail else ""
    st.markdown(
        f'<span class="status-dot {dot}"></span>**{label}**{suffix}',
        unsafe_allow_html=True,
    )


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

    st.title(t("🎙️ Streaming Dashboard"))
    st.divider()

    # ── YouTube auth ──────────────────────────────────────────────────────────
    st.subheader("🔴 YouTube")
    # Handle Google's OAuth redirect: http://localhost:8501/?state=...&code=...
    if "code" in st.query_params:
        ok, err = yt.complete_oauth_flow(
            st.query_params.get("code", ""), st.query_params.get("state", "")
        )
        st.query_params.clear()
        st.query_params["lang"] = st.session_state["ui_lang"]
        st.session_state["yt_auth_url"] = ""
        st.session_state["yt_oauth_result"] = (ok, err)
    elif "error" in st.query_params and "state" in st.query_params:
        err = st.query_params.get("error", "")
        st.query_params.clear()
        st.query_params["lang"] = st.session_state["ui_lang"]
        st.session_state["yt_oauth_result"] = (False, t("Google returned: {err}", err=err))
    oauth_result = st.session_state.pop("yt_oauth_result", None)
    if oauth_result:
        if oauth_result[0]:
            st.success(t("YouTube sign-in complete!"))
        else:
            st.error(oauth_result[1])

    if yt.is_authenticated():
        st.success(t("Authenticated ✓"))
    else:
        if ytw.has_login():
            st.success(t("Signed in with browser cookies ✓ (sending chat)"))
            st.caption(t("OAuth is optional — needed only for ban / delete and your own broadcast stats."))
        else:
            st.warning(t("Not authenticated"))
        if st.button(t("Start YouTube OAuth")):
            url = yt.start_oauth_flow()
            if url:
                st.session_state["yt_auth_url"] = url
            else:
                st.error(t("Set YOUTUBE_CLIENT_ID / CLIENT_SECRET in .env first."))
        if st.session_state["yt_auth_url"]:
            st.link_button(t("Open Google sign-in"), st.session_state["yt_auth_url"])
            st.caption(t(
                "After you approve, Google redirects back here and sign-in completes automatically. "
                "If it doesn't, paste the full redirect URL below."
            ))
            pasted = st.text_input(t("Redirect URL or code"), key="yt_code_input")
            if st.button(t("Submit")) and pasted:
                ok, err = yt.complete_oauth_flow(*yt.parse_redirect(pasted))
                if ok:
                    st.session_state["yt_auth_url"] = ""
                    st.success(t("Authenticated!"))
                    st.rerun()
                else:
                    st.error(err)

    yt_chat_input = st.text_input(
        t("Live stream URL, video ID, or live chat ID"),
        value=st.session_state["yt_chat_input"],
        key="yt_room_input",
        placeholder="https://www.youtube.com/watch?v=…",
    ).strip()
    if yt_chat_input != st.session_state["yt_chat_input"]:
        st.session_state["yt_chat_input"] = yt_chat_input
        # Changing the stream stops the current listener, like the Bilibili room field.
        st.session_state["selected_chat_id"] = ""
        st.session_state["yt_chat_error"] = ""
        st.session_state["yt_page_token"] = ""

    _yt_vid = yt.extract_video_id(yt_chat_input) if yt_chat_input else ""
    if _yt_vid:
        _yt_info = _cached_video_status(_yt_vid)
        if _yt_info:
            _yt_live = _yt_info["broadcast"] == "live"
            _status_badge(
                _yt_live,
                t("{n} watching", n=f"{_yt_info['viewers']:,}") if _yt_live
                else (t("Upcoming") if _yt_info["broadcast"] == "upcoming" else ""),
            )

    if st.session_state["selected_chat_id"]:
        st.success(t("YouTube chat listener active ✓"))
        if yt.is_web_chat(st.session_state["selected_chat_id"]):
            st.caption(t("Reading chat without sign-in. Sign in to send messages or moderate."))
        elif st.session_state["selected_chat_id"] != yt_chat_input:
            st.caption(t("Chat ID: `{chat_id}`", chat_id=st.session_state["selected_chat_id"]))
        if st.button(t("Stop YouTube listener")):
            st.session_state["selected_chat_id"] = ""
            st.session_state["yt_page_token"] = ""
            st.rerun()
    else:
        if st.button(t("Start YouTube listener")) and yt_chat_input:
            chat_id, err = yt.resolve_live_chat_id(yt_chat_input)
            st.session_state["selected_chat_id"] = chat_id
            st.session_state["yt_chat_error"] = err
            st.session_state["yt_page_token"] = ""
            if chat_id:
                st.rerun()
        if st.session_state["yt_chat_error"]:
            st.error(st.session_state["yt_chat_error"])

    st.divider()

    # ── Bilibili ──────────────────────────────────────────────────────────────
    st.subheader("💙 Bilibili")
    bili_room = st.text_input(
        t("Room ID"), value=st.session_state["bili_room_id"], key="bili_room_input"
    ).strip()
    if bili_room != st.session_state["bili_room_id"]:
        st.session_state["bili_room_id"] = bili_room
        # Reset listener
        if st.session_state["bili_listener"]:
            st.session_state["bili_listener"].stop()
            st.session_state["bili_listener"] = None

    if bili_room:
        _bili_info = _cached_room_info(bili_room)
        if _bili_info:
            _bili_live = _bili_info.get("live_status") == 1
            _status_badge(
                _bili_live,
                t("popularity {n}", n=f"{_bili_info.get('online', 0):,}") if _bili_live
                else (t("Playback") if _bili_info.get("live_status") == 2 else ""),
            )

    listener: Optional[bili.DanmakuListener] = st.session_state["bili_listener"]
    if listener and listener._running:
        if listener.connected_uid is None:
            st.info(t("Danmaku listener connecting…"))
        elif listener.is_anonymous:
            st.warning(t(
                "Danmaku listener active, but **anonymous** — Bilibili masks usernames (e.g. 波***). "
                "Import login cookies in the 🍪 Cookies tab."
            ))
        else:
            st.success(t("Danmaku listener active ✓ (logged in, UID {uid})", uid=listener.connected_uid))
        if st.button(t("Stop Bilibili listener")):
            listener.stop()
            st.session_state["bili_listener"] = None
            st.rerun()
    else:
        if not bili.has_login_credentials():
            st.caption(t("No Bilibili login cookies set — chat usernames will be masked."))
        if st.button(t("Start Bilibili listener")) and bili_room:
            l = bili.DanmakuListener(bili_room)
            if l.start():
                st.session_state["bili_listener"] = l
                st.success(t("Listener started!"))
            else:
                st.error(t("bilibili-api-python not installed or connection failed."))

    st.divider()

    # ── MissEvan 猫耳FM ────────────────────────────────────────────────────────
    st.subheader("🐱 MissEvan 猫耳FM")
    me_input = st.text_input(
        t("Room ID or URL"), value=st.session_state["me_room_id"], key="me_room_input",
        placeholder="https://fm.missevan.com/live/869215180",
    )
    me_room = me.parse_room_id(me_input)
    if me_room != st.session_state["me_room_id"]:
        st.session_state["me_room_id"] = me_room
        if st.session_state["me_listener"]:
            st.session_state["me_listener"].stop()
            st.session_state["me_listener"] = None
    if me_input.strip() and not me_room:
        st.error(t("Could not find a room ID in that text."))

    if me_room:
        _me_info = _cached_me_room_info(me_room)
        if _me_info:
            _me_listener_now = st.session_state["me_listener"]
            _me_online = (_me_listener_now.online if _me_listener_now and _me_listener_now.online is not None
                          else _me_info.get("online", 0))
            _status_badge(_me_info.get("live", False),
                          t("{n} online", n=f"{_me_online:,}") if _me_info.get("live") and _me_online else "")
            st.caption(f"{_me_info.get('uname', '')} · {_me_info.get('title', '')}")
        else:
            st.warning(t("MissEvan room not found."))

    me_listener: Optional[me.MissEvanListener] = st.session_state["me_listener"]
    if me_listener and me_listener.running:
        if me_listener.connected:
            st.success(t("MissEvan chat listener active ✓"))
        elif me_listener.error:
            st.warning(me_listener.error)
        else:
            st.info(t("MissEvan chat listener connecting…"))
        if st.button(t("Stop MissEvan listener")):
            me_listener.stop()
            st.session_state["me_listener"] = None
            st.rerun()
    else:
        st.caption(t("Shows chat, gifts, paid questions and joins without login. To send chat, log in via the 🍪 Cookies tab."))
        if st.button(t("Start MissEvan listener")) and me_room:
            l = me.MissEvanListener(me_room)
            if l.start():
                st.session_state["me_listener"] = l
                st.rerun()
            else:
                st.error(l.error)

    st.divider()

    # ── OBS ───────────────────────────────────────────────────────────────────
    st.subheader("🎬 OBS")
    obs_status = obs.get_status()
    if obs_status.get("connected"):
        st.success(t("OBS connected ✓"))
        scenes = obs.get_scenes()
        if scenes:
            cur_scene = obs_status.get("current_scene", "")
            idx = scenes.index(cur_scene) if cur_scene in scenes else 0
            new_scene = st.selectbox(t("Scene"), scenes, index=idx, key="obs_scene_sel")
            if new_scene != cur_scene:
                obs.switch_scene(new_scene)
                st.rerun()
    else:
        st.warning(t("OBS not connected — check OBS_HOST/PORT/PASSWORD in .env"))

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
    _rd_keys = list(reading.MODES)
    st.session_state["sc_reading"] = st.selectbox(
        t("Super Chat reading aid"),
        _rd_keys,
        index=_rd_keys.index(st.session_state["sc_reading"]),
        format_func=lambda k: t(reading.MODES[k]),
        help=t("Shows pinyin / hiragana above Chinese characters in Super Chats so you can read them aloud."),
    )

    st.divider()

    # ── TTS ───────────────────────────────────────────────────────────────────
    st.subheader(t("🔊 Text-to-Speech"))
    st.session_state["tts_enabled"] = st.toggle(
        t("Enable TTS"), value=st.session_state["tts_enabled"]
    )
    _lang_keys = list(TTS_LANGUAGES)
    st.session_state["tts_lang"] = st.selectbox(
        t("Language"),
        _lang_keys,
        index=_lang_keys.index(st.session_state["tts_lang"]),
        format_func=lambda k: t(TTS_LANGUAGES[k][0]),
        help=t("Auto-detect reads every message in its own language. Picking a language only reads chat written in that language."),
    )
    st.session_state["tts_skip_emoji"] = st.checkbox(
        t("Ignore emoji"),
        value=st.session_state["tts_skip_emoji"],
        help=t("Skip emoji-only messages and stickers, and don't read emoji inside messages."),
    )
    st.session_state["tts_announce_paid"] = st.checkbox(
        t("Always announce gifts & Super Chats"),
        value=st.session_state["tts_announce_paid"],
        help=t(
            "Reads gifts, Super Chats and memberships in any language, ahead of normal chat "
            "(normal chat waits until they're done)."
        ),
    )
    st.session_state["tts_skip_name"] = st.checkbox(
        t("Don't read usernames for regular chat"),
        value=st.session_state["tts_skip_name"],
        help=t("Reads only the message text. Gifts and Super Chats still say who sent them."),
    )
    st.session_state["tts_translate"] = st.checkbox(
        t("Read translated chat"),
        value=st.session_state["tts_translate"],
        help=t(
            "When the TTS language matches \"Translate to\" (Translation section), every message is "
            "read translated into that language. Otherwise messages are read in their original language."
        ),
    )
    if st.session_state["tts_translate"] and not _tts_translating():
        st.caption(t(
            "⚠️ Not active: set the TTS language to the same language as \"Translate to\" ({target}).",
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
    st.session_state["show_enter_events"] = st.checkbox(
        t("Show join events"), value=st.session_state["show_enter_events"]
    )
    st.session_state["max_chat_display"] = st.number_input(
        t("Max messages displayed"), 50, 1000, st.session_state["max_chat_display"]
    )

    if st.button(t("🗑️ Clear chat history")):
        st.session_state["chat_messages"] = []
        st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# Main area tabs
# ──────────────────────────────────────────────────────────────────────────────

tab_chat, tab_status, tab_obs, tab_analytics, tab_filters, tab_overlay, tab_cookies = st.tabs(
    [t(x) for x in ("💬 Chat", "📡 Stream Status", "🎬 OBS Control", "📊 Analytics", "🛡️ Filters", "🖥️ Overlay", "🍪 Cookies")]
)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: CHAT
# ═══════════════════════════════════════════════════════════════════════════════

with tab_chat:
    _poll_chat()  # fetch new messages every rerun

    # Handle pending ban from previous rerun
    if "_pending_ban" in st.session_state:
        msg = st.session_state.pop("_pending_ban")
        with st.expander(t("⚠️ Action on {author}", author=msg["author"]), expanded=True):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                timeout_min = st.number_input(t("Timeout (minutes, 0=permanent)"), 0, 1440, 10, key="ban_dur")
            with col_b:
                if st.button(t("🚫 Ban / Timeout"), key="do_ban"):
                    platform = msg.get("platform")
                    if platform == "youtube":
                        chat_id = st.session_state.get("selected_chat_id", "")
                        yt.ban_user(chat_id, msg["author_id"], timeout_min * 60)
                    elif platform == "bilibili":
                        try:
                            bili.block_user(
                                st.session_state["bili_room_id"],
                                int(msg["author_id"]),
                                max(1, timeout_min // 60),
                            )
                        except Exception:
                            pass
                    st.session_state["filter"].block_user(msg["author_id"])
                    st.success(t("Blocked {author}", author=msg["author"]))
            with col_c:
                if st.button(t("🗑️ Delete message"), key="do_del"):
                    if msg.get("platform") == "youtube":
                        yt.delete_chat_message(msg["id"])
                    st.session_state["chat_messages"] = [
                        m for m in st.session_state["chat_messages"] if m["id"] != msg["id"]
                    ]
                    st.rerun()

    # ── Send message ──────────────────────────────────────────────────────────
    yt_chat = st.session_state.get("selected_chat_id", "")
    bili_room_send = st.session_state["bili_room_id"]
    tgt_row = st.container(horizontal=True, vertical_alignment="center", gap="medium")
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
    me_logged_in = me.has_login()
    send_me = tgt_row.checkbox(
        t("MissEvan"), key="send_me", value=True, disabled=not (me_room_send and me_logged_in),
        help=None if me_room_send and me_logged_in
        else t("Log in to MissEvan in the 🍪 Cookies tab first.") if not me_logged_in
        else t("Enter a MissEvan room first."),
    )
    with st.form("send_form", clear_on_submit=True), st.container(key="send_box"):
        send_cols = st.columns([8, 1])
        outgoing = send_cols[0].text_input(t("Message"), label_visibility="collapsed", placeholder=t("Type a message…"))
        submitted = send_cols[1].form_submit_button(t("Send"))
        if submitted and outgoing:
            targets = []
            if send_yt and yt_chat:
                targets.append(("YouTube", lambda: yt.send_chat(
                    yt_chat, yt.extract_video_id(st.session_state["yt_chat_input"]), outgoing)))
            if send_bili and bili_room_send:
                targets.append(("Bilibili", lambda: (bili.send_danmaku(bili_room_send, outgoing), "")))
            if send_me and me_room_send and me_logged_in:
                targets.append(("MissEvan", lambda: me.send_message(me_room_send, outgoing)))
            if not targets:
                st.warning(t("Tick at least one site to send to."))
            for name, send in targets:
                ok, err = send()
                if ok:
                    st.toast(t("Sent to {site} ✓", site=name))
                elif err:
                    st.error(t("Failed to send to {site}: {err}", site=name, err=err))
                else:
                    st.error(t("Failed to send to {site} (check sign-in / login cookies).", site=name))

    st.divider()

    # ── Platform filter ───────────────────────────────────────────────────────
    show_row = st.container(horizontal=True, vertical_alignment="center", gap="large")
    show_yt = show_row.checkbox("YouTube", value=True, key="show_yt")
    show_bili = show_row.checkbox("Bilibili", value=True, key="show_bili")
    show_me = show_row.checkbox(t("MissEvan"), value=True, key="show_me")

    hidden_platforms = {
        p for p, shown in (("youtube", show_yt), ("bilibili", show_bili), ("missevan", show_me)) if not shown
    }
    # Gifts / Super Chats live in their own column; free gifts stay in regular chat.
    msgs = [
        m for m in st.session_state["chat_messages"]
        if m.get("platform") not in hidden_platforms and not is_paid(m)
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

    chat_col, paid_col = st.container(key="chat_paid").columns([3, 2])
    with chat_col:
        st.markdown(f"**💬 {t('Chat')}**")
        with st.container(key="chat_feed"):
            for msg in reversed(visible):
                _render_message(msg, key_prefix="chat")

    with paid_col:
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
        with st.container(key="paid_feed"):
            if not paid_all:
                st.caption(t("No gifts or Super Chats yet."))
            for msg in reversed(paid_all[-200:]):
                _render_message(msg, key_prefix="paid", thank=True)

    # Auto-refresh placeholder
    st.markdown(
        f"<p style='color:#555;font-size:0.75rem'>"
        f"{t('Auto-refreshes every {s}s · {n} messages shown', s=CHAT_POLL_INTERVAL, n=len(msgs))}</p>",
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: STREAM STATUS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_status:
    yt_col, bili_col, me_col = st.columns(3)
    yt_viewers_now = 0
    bili_viewers_now = 0

    # ── YouTube status ────────────────────────────────────────────────────────
    with yt_col:
        st.subheader("🔴 YouTube")
        yt_input = st.session_state["yt_chat_input"]
        video_id = yt.extract_video_id(yt_input)
        if not yt_input:
            st.warning(t("Enter a stream URL in the sidebar."))
        elif not video_id:
            st.info(t("Status needs a stream URL or video ID (a raw chat ID has no video info)."))
        else:
            info = _cached_video_status(video_id)
            if not info:
                st.error(t("Could not fetch stream info (sign in or set YOUTUBE_API_KEY)."))
            elif not info["is_stream"]:
                st.warning(t("That video is not a live stream."))
            else:
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
                    yt_viewers_now = info["viewers"]
                elif info["broadcast"] == "upcoming" and info["scheduled_start"]:
                    st.caption(t("Scheduled: {t}", t=info["scheduled_start"]))

    # ── Bilibili status ───────────────────────────────────────────────────────
    with bili_col:
        st.subheader("💙 Bilibili")
        room_id = st.session_state["bili_room_id"]
        if not room_id:
            st.warning(t("Enter a room ID in the sidebar."))
        else:
            info = _cached_room_info(room_id)
            if not info:
                st.error(t("Could not fetch room info."))
            else:
                live_status = info.get("live_status", 0)
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

    # ── MissEvan status ───────────────────────────────────────────────────────
    me_viewers_now = 0
    with me_col:
        st.subheader("🐱 MissEvan")
        me_room_id = st.session_state["me_room_id"]
        if not me_room_id:
            st.warning(t("Enter a room ID in the sidebar."))
        else:
            info = _cached_me_room_info(me_room_id)
            if not info:
                st.error(t("Could not fetch room info."))
            else:
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

    if yt_viewers_now or bili_viewers_now or me_viewers_now:
        _record_viewer_snapshot(yt_viewers_now, bili_viewers_now, me_viewers_now)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: OBS CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

with tab_obs:
    obs_status = obs.get_status()
    if not obs_status.get("connected"):
        st.warning(t("⚠️ OBS is not connected. Configure OBS WebSocket settings in your .env file."))
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
        with st.form("add_allow_pattern", clear_on_submit=True):
            new_allow = st.text_input(t("New allow pattern"))
            if st.form_submit_button(t("Add allow pattern")) and new_allow:
                filt.add_allow_pattern(new_allow)
                st.rerun()

    with col_user:
        st.markdown("#### " + t("Blocked Users"))
        blocked_ids = filt.blocked_users
        if blocked_ids:
            for uid in list(blocked_ids):
                c1, c2 = st.columns([8, 1])
                c1.code(uid)
                if c2.button("✕", key=f"del_uid_{uid}"):
                    filt.unblock_user(uid)
                    st.rerun()
        else:
            st.info(t("No blocked users."))

        with st.form("block_user_form", clear_on_submit=True):
            new_uid = st.text_input(t("Block by user ID / channel ID"))
            if st.form_submit_button(t("Block")) and new_uid:
                filt.block_user(new_uid)
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: OVERLAY
# ═══════════════════════════════════════════════════════════════════════════════

with tab_overlay:
    st.subheader(t("🖥️ Chat Overlay"))
    st.markdown(
        t("Use the overlay URL in OBS as a **Browser Source** to show a transparent chat on stream.")
    )

    st.info(t(
        "**How to use**: Add a Browser Source in OBS pointing to `http://localhost:8501/overlay` "
        "— or copy the overlay HTML below into a local file and load it as a file URL."
    ))

    # Live overlay text
    overlay_text = st.text_area(
        t("Custom overlay message (shown permanently on stream)"),
        value=st.session_state["overlay_text"],
        height=80,
    )
    st.session_state["overlay_text"] = overlay_text

    st.session_state["overlay_visible"] = st.toggle(
        t("Show custom overlay message"), value=st.session_state["overlay_visible"]
    )

    st.divider()

    # Recent chat overlay preview
    st.markdown("#### " + t("Recent Chat Preview (last 5 messages)"))
    recent = st.session_state["chat_messages"][-5:]
    preview_html = '<div style="background:rgba(0,0,0,0.7);padding:8px;border-radius:8px;width:360px;font-family:sans-serif;">'
    for m in reversed(recent):
        plat_color = {"youtube": "#ff4444", "missevan": "#ff7a45"}.get(m.get("platform", ""), "#23ade5")
        preview_html += (
            f'<div style="color:#fff;margin-bottom:4px;font-size:13px;">'
            f'<span style="color:{plat_color};font-weight:700;">{m.get("author","")}</span>: '
            f'{m.get("text","")}'
            f"</div>"
        )
    if st.session_state["overlay_visible"] and overlay_text:
        preview_html += (
            f'<div style="color:#ffd700;font-weight:700;margin-top:8px;border-top:1px solid #555;padding-top:6px;">'
            f'{overlay_text}'
            f"</div>"
        )
    preview_html += "</div>"
    st.markdown(preview_html, unsafe_allow_html=True)

    st.divider()
    st.markdown("#### " + t("Standalone Overlay HTML"))
    st.caption(t("Save as `overlay.html` and open in OBS Browser Source."))
    overlay_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ margin:0; background:transparent; font-family: 'Segoe UI', sans-serif; }}
  #chat {{ position:fixed; bottom:20px; left:20px; width:350px; max-height:400px;
           overflow:hidden; display:flex; flex-direction:column-reverse; }}
  .msg {{ color:#fff; text-shadow:1px 1px 2px #000; margin-bottom:4px; font-size:14px; animation: fadein 0.3s; }}
  .yt  {{ color:#ff6b6b; font-weight:700; }}
  .bi  {{ color:#5bc8f5; font-weight:700; }}
  @keyframes fadein {{ from {{opacity:0;transform:translateY(10px)}} to {{opacity:1;transform:none}} }}
</style>
</head>
<body>
<div id="chat">
  <div class="msg"><span class="yt">Streamer</span>: Welcome to the stream! 🎉</div>
</div>
</body>
</html>"""
    st.code(overlay_html, language="html")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: COOKIES
# ═══════════════════════════════════════════════════════════════════════════════

with tab_cookies:
    st.subheader(t("🍪 Import login cookies from browser"))
    st.caption(t(
        "Reads cookies from a browser installed on this computer. Values never leave this "
        "machine except when verifying the login with the site itself."
    ))
    if not bc.BROWSER_COOKIE_LIB_OK:
        st.error(t("browser-cookie3 is not installed. Run `pip install browser-cookie3`."))
    else:
        col_browser, col_site = st.columns(2)
        with col_browser:
            browser_label = st.selectbox(t("Browser"), list(bc.BROWSERS), key="cookie_browser")
        with col_site:
            site_label = st.selectbox(t("Site"), list(bc.SITES), key="cookie_site")
        st.caption(t(
            "Chrome/Edge on Windows encrypt cookies with app-bound encryption and may require "
            "running the app as administrator. Firefox works without elevation. Close the "
            "browser if its cookie database is locked."
        ))

        if st.button(t("Read cookies"), type="primary"):
            try:
                cookies = bc.read_cookies(bc.BROWSERS[browser_label], bc.SITES[site_label])
                st.session_state["cookie_result"] = {
                    "browser": browser_label,
                    "site": site_label,
                    "cookies": cookies,
                    "verify": bc.verify_bilibili_login(cookies)
                    if site_label == "Bilibili" and "SESSDATA" in cookies
                    else me.verify_login(cookies)
                    if site_label == "MissEvan" and cookies
                    else ytw.verify_login(cookies)
                    if site_label == "YouTube" and cookies
                    else None,
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
                    {t("Cookie"): name, t("Env var"): env, t("Value"): bc.mask(cookies[name]) if name in cookies else t("❌ missing")}
                    for name, env in bc.BILIBILI_ENV_KEYS.items()
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
                    if st.button(t("💾 Save to .env and apply")):
                        saved = bc.save_bilibili_credentials(cookies)
                        msg = t("Saved {keys} to .env.", keys=", ".join(saved))
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
                    if st.button(t("💾 Save to .env and apply"), key="yt_save_browser"):
                        ytw.save_login(cookies)
                        st.session_state["_yt_saved_name"] = verify["name"]
                    if st.session_state.get("_yt_saved_name") == verify["name"]:
                        st.success(t("Saved YOUTUBE_COOKIE to .env — you can now send YouTube chat without OAuth."))
                    st.caption(t(
                        "Cookie login is unofficial (it works like youtube.com itself) and may break if YouTube "
                        "changes it. OAuth sign-in, if set up, is used first."
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

# ──────────────────────────────────────────────────────────────────────────────
# Auto-refresh via st.rerun
# ──────────────────────────────────────────────────────────────────────────────
time.sleep(CHAT_POLL_INTERVAL)
st.rerun()
