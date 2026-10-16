"""Minimal live monitor for the platforms configured in .env.

Run with:
    streamlit run simple_app.py
"""
from __future__ import annotations

import html
import json
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from src import bilibili as bili
from src import browser_cookies as bc
from src import config as app_config
from src import emotes
from src import gifts as gift_utils
from src import i18n
from src import missevan as me
from src import translate as tr
from src import youtube as yt
from src import youtube_web as ytw
from src.config import CHAT_POLL_INTERVAL, MAX_CHAT_DISPLAY, ROOM_STATUS_POLL_INTERVAL
from src.tts import (
    LANGUAGES as TTS_LANGUAGES,
    format_announcement,
    is_emoji_only,
    is_gift,
    is_paid,
    matches_language,
    strip_emoji,
)

st.set_page_config(page_title="Live Chat Monitor", page_icon="🎙️", layout="wide")


def _configured_platforms() -> dict[str, str]:
    """Return configured sources; invalid configured room IDs remain visible as errors."""
    sources = {}
    if app_config.YOUTUBE_CHANNEL.strip():
        sources["youtube"] = app_config.YOUTUBE_CHANNEL.strip()
    if app_config.BILIBILI_ROOM_ID.strip():
        sources["bilibili"] = bili.parse_room_id(app_config.BILIBILI_ROOM_ID)
    if app_config.MISSEVAN_ROOM_ID.strip():
        sources["missevan"] = me.parse_room_id(app_config.MISSEVAN_ROOM_ID)
    return sources


_SOURCES = _configured_platforms()
_PLATFORM_NAMES = {"youtube": "YouTube", "bilibili": "Bilibili", "missevan": "MissEvan"}
_STATUS_INTERVAL = max(1, ROOM_STATUS_POLL_INTERVAL)


def _page_language() -> str:
    return st.session_state.get("simple_page_language", "en")


def _t(text: str, **kwargs) -> str:
    return i18n.translate(text, _page_language(), **kwargs)


def _translation_target() -> str:
    return {"en": "en", "zh": "zh-CN", "ja": "ja"}[_page_language()]


def _format_message_time(timestamp: str, browser_timezone: str = "") -> str:
    if not timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return ""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    try:
        target_zone = ZoneInfo(browser_timezone) if browser_timezone else None
    except (ZoneInfoNotFoundError, ValueError):
        target_zone = None
    return dt.astimezone(target_zone).strftime("%H:%M:%S")


def _track_live_status(site: str, live: bool, title: str = "") -> None:
    states = st.session_state["simple_live_states"]
    previous = states.get(site)
    states[site] = live
    if previous is False and live and st.session_state["simple_notify_live"]:
        states.setdefault("_notifications", []).append({
            "site": _PLATFORM_NAMES[site],
            "title": title,
        })


def _init_state() -> None:
    defaults = {
        "simple_chat": [],
        "simple_gifts": [],
        "simple_profit_totals": {},
        "simple_last_poll": 0.0,
        "simple_last_status": 0.0,
        "simple_yt_channel": "",
        "simple_yt_video_id": "",
        "simple_yt_chat_id": "",
        "simple_yt_page_token": "",
        "simple_yt_backlog_loaded": False,
        "simple_yt_status": {},
        "simple_yt_error": "",
        "simple_bili_listener": None,
        "simple_bili_error": "",
        "simple_bili_login_name": "",
        "simple_bili_cookie": "",
        "simple_bili_cookie_error": "",
        "simple_me_listener": None,
        "simple_me_error": "",
        "simple_room_status": {},
        "simple_live_states": {},
        "simple_notify_live": True,
        "simple_tts_queue": [],
        "simple_tts_pending": [],
        "simple_translation_enabled": False,
        "simple_page_language": "en",
        "simple_tts_enabled": False,
        "simple_tts_language": "auto",
        "simple_tts_rate": 150,
        "simple_tts_volume": 1.0,
        "simple_tts_translate": False,
        "simple_tts_read_chat": True,
        "simple_tts_read_gifts": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if "youtube" in _SOURCES and not st.session_state["simple_yt_channel"] \
            and not st.session_state["simple_yt_video_id"]:
        configured = _SOURCES["youtube"]
        channel = ytw.channel_url(configured)
        if channel:
            st.session_state["simple_yt_channel"] = channel
        else:
            st.session_state["simple_yt_video_id"] = yt.extract_video_id(configured)
            if not st.session_state["simple_yt_video_id"]:
                st.session_state["simple_yt_error"] = "The configured YouTube URL isn't a channel or video URL."

    if "bilibili" in _SOURCES and not _SOURCES["bilibili"]:
        st.session_state["simple_bili_error"] = "The configured Bilibili room ID is invalid."
    elif "bilibili" in _SOURCES and st.session_state["simple_bili_listener"] is None \
            and not st.session_state["simple_bili_error"]:
        listener = bili.DanmakuListener(_SOURCES["bilibili"])
        if listener.start():
            st.session_state["simple_bili_listener"] = listener
        else:
            st.session_state["simple_bili_error"] = (
                "Bilibili listener couldn't start. Install bilibili-api-python and restart the app."
            )

    if "missevan" in _SOURCES and not _SOURCES["missevan"]:
        st.session_state["simple_me_error"] = "The configured MissEvan room ID is invalid."
    elif "missevan" in _SOURCES and st.session_state["simple_me_listener"] is None \
            and not st.session_state["simple_me_error"]:
        listener = me.MissEvanListener(_SOURCES["missevan"])
        if listener.start():
            st.session_state["simple_me_listener"] = listener
        else:
            st.session_state["simple_me_error"] = listener.error or "MissEvan listener couldn't start."


_init_state()


def _import_bilibili_cookie() -> None:
    raw = st.session_state["simple_bili_cookie"].strip()
    st.session_state["simple_bili_cookie_error"] = ""
    if not raw:
        return
    try:
        cookies = bc.parse_cookie_text(raw, bc.SITES["Bilibili"])
    except bc.CookieReadError as exc:
        st.session_state["simple_bili_cookie_error"] = str(exc)
        return
    if not cookies.get("SESSDATA"):
        st.session_state["simple_bili_cookie_error"] = _t("Cookie must include SESSDATA.")
        return

    result = bc.verify_bilibili_login(cookies)
    if result.get("error"):
        st.session_state["simple_bili_cookie_error"] = _t(
            "Couldn't verify Bilibili login: {error}", error=result["error"]
        )
        return
    if not result.get("is_login"):
        st.session_state["simple_bili_cookie_error"] = _t(
            "These cookies aren't logged in or have expired."
        )
        return

    bc.save_bilibili_credentials(cookies)
    st.session_state["simple_bili_login_name"] = result.get("uname") or ""
    st.session_state["simple_bili_cookie"] = ""

    if _SOURCES.get("bilibili"):
        old_listener = st.session_state["simple_bili_listener"]
        if old_listener:
            _accept_messages(old_listener.pop_messages())
            old_listener.stop()
        listener = bili.DanmakuListener(_SOURCES["bilibili"])
        if listener.start():
            st.session_state["simple_bili_listener"] = listener
            st.session_state["simple_bili_error"] = ""
        else:
            st.session_state["simple_bili_listener"] = None
            st.session_state["simple_bili_error"] = (
                "Bilibili listener couldn't start. Install bilibili-api-python and restart the app."
            )


def _refresh_youtube() -> None:
    now = time.monotonic()
    if now - st.session_state["simple_last_status"] < _STATUS_INTERVAL:
        return
    st.session_state["simple_last_status"] = now

    channel = st.session_state["simple_yt_channel"]
    video_id = st.session_state["simple_yt_video_id"]
    join_video_id = ""
    if channel:
        info = ytw.find_live_video(channel)
        st.session_state["simple_yt_status"] = info
        if not info.get("error"):
            st.session_state["simple_yt_error"] = ""
            _track_live_status("youtube", bool(info.get("live")), info.get("title", ""))
        if info.get("live") and info.get("video_id"):
            video_id = info["video_id"]
            if video_id != st.session_state["simple_yt_video_id"]:
                st.session_state["simple_yt_chat_id"] = ""
                st.session_state["simple_yt_page_token"] = ""
                st.session_state["simple_yt_backlog_loaded"] = False
            st.session_state["simple_yt_video_id"] = video_id
            join_video_id = video_id
        elif st.session_state["simple_yt_chat_id"]:
            current = ytw.get_video_status(st.session_state["simple_yt_video_id"])
            if current and current.get("broadcast") != "live":
                st.session_state["simple_yt_chat_id"] = ""
                st.session_state["simple_yt_page_token"] = ""
                st.session_state["simple_yt_backlog_loaded"] = False
                st.session_state["simple_yt_video_id"] = ""
                video_id = ""
    elif video_id:
        info = yt.get_video_live_status(video_id)
        st.session_state["simple_yt_status"] = info
        if info and info.get("broadcast") == "live":
            join_video_id = video_id
            st.session_state["simple_yt_error"] = ""
            _track_live_status("youtube", True, info.get("title", ""))
        elif info:
            _track_live_status("youtube", False, info.get("title", ""))
            st.session_state["simple_yt_chat_id"] = ""
            st.session_state["simple_yt_page_token"] = ""
            st.session_state["simple_yt_backlog_loaded"] = False
        elif not info:
            st.session_state["simple_yt_error"] = "Couldn't fetch YouTube stream status."

    if join_video_id and not st.session_state["simple_yt_chat_id"]:
        chat_id, error = yt.resolve_live_chat_id(join_video_id)
        st.session_state["simple_yt_chat_id"] = chat_id
        st.session_state["simple_yt_error"] = error
        st.session_state["simple_yt_page_token"] = ""
    elif st.session_state["simple_yt_chat_id"]:
        st.session_state["simple_yt_error"] = ""


def _refresh_room_status() -> None:
    statuses = st.session_state["simple_room_status"]
    if _SOURCES.get("bilibili"):
        info = bili.get_room_info(_SOURCES["bilibili"])
        statuses["bilibili"] = info
        if info:
            _track_live_status("bilibili", info.get("live_status") == 1, info.get("uname") or info.get("title", ""))
    if _SOURCES.get("missevan"):
        info = me.get_room_info(_SOURCES["missevan"])
        statuses["missevan"] = info
        if info:
            _track_live_status("missevan", bool(info.get("live")), info.get("uname") or info.get("title", ""))


def _emit_live_notifications() -> None:
    notifications = st.session_state["simple_live_states"].get("_notifications", [])
    if not notifications:
        return
    st.session_state["simple_live_states"]["_notifications"] = []
    payload = json.dumps(notifications, ensure_ascii=False).replace("</", "<\\/")
    st.html(
        """<script>(() => {
          const w = window.parent || window;
          if (!('Notification' in w) || w.Notification.permission !== 'granted') return;
          for (const item of __ITEMS__) {
            const body = item.title ? `${item.site} is live: ${item.title}` : `${item.site} is live`;
            new w.Notification('Live Chat Monitor', {body, tag: `${item.site}:${item.title}`});
          }
        })();</script>""".replace("__ITEMS__", payload),
        unsafe_allow_javascript=True,
    )


def _notification_permission_button() -> None:
    st.html(
        f'<button id="simple-notification-permission" style="padding:4px 10px;border-radius:6px;cursor:pointer;'
        f'border:1px solid rgba(128,128,128,.5);background:transparent;color:inherit;font:inherit">'
        f'{_t("🔔 Allow browser notifications")}</button>'
        '<script>(() => {'
        'const b = document.getElementById("simple-notification-permission");'
        'if (!b) return;'
        f'const done = {json.dumps(_t("🔔 Browser notifications enabled"))};'
        'if (!("Notification" in window)) { b.disabled = true; b.textContent = '
        f'{json.dumps(_t("Browser notifications are not supported"))}; return; }}'
        'if (Notification.permission === "granted") { b.textContent = done; b.disabled = true; return; }'
        'b.onclick = () => Notification.requestPermission().then(p => {'
        ' if (p === "granted") { b.textContent = done; b.disabled = true; } });'
        '})();</script>',
        unsafe_allow_javascript=True,
    )


def _queue_speech(msg: dict) -> None:
    paid = is_paid(msg)
    if not st.session_state["simple_tts_enabled"]:
        return
    if paid and not st.session_state["simple_tts_read_gifts"]:
        return
    if not paid and (not st.session_state["simple_tts_read_chat"] or msg.get("type") != "danmaku"
                     and msg.get("type") != "textMessageEvent"):
        return

    text = msg.get("text", "")
    if not paid:
        if is_emoji_only(msg):
            return
        text = strip_emoji(text, msg.get("platform", "")) or text

    lang = "auto" if is_gift(msg) else st.session_state["simple_tts_language"]
    if not paid and not st.session_state["simple_tts_translate"] \
            and not matches_language(text, lang):
        return
    if st.session_state["simple_tts_translate"] and st.session_state["simple_translation_enabled"] \
            and not is_gift(msg):
        target = _translation_target()
        translated = tr.get_translation(text, target)
        if translated is None:
            speech_msg = {**msg, "text": text}
            st.session_state["simple_tts_pending"].append({"msg": speech_msg, "paid": paid})
            return
        if translated:
            text, lang = translated, target.split("-")[0]

    line = (
        format_announcement(msg.get("type", ""), msg.get("author", ""), text, lang)
        if paid else text
    )
    st.session_state["simple_tts_queue"].append({
        "id": str(msg.get("id") or f"{msg.get('platform')}:{time.time_ns()}"),
        "text": line,
        "lang": TTS_LANGUAGES.get(lang, TTS_LANGUAGES["auto"])[2],
        "rate": st.session_state["simple_tts_rate"] / 150,
        "volume": st.session_state["simple_tts_volume"],
        "priority": paid,
    })


def _flush_tts_pending() -> None:
    waiting = []
    for item in st.session_state["simple_tts_pending"]:
        msg = item["msg"]
        if not st.session_state["simple_tts_enabled"] or (
            item["paid"] and not st.session_state["simple_tts_read_gifts"]
        ) or (
            not item["paid"] and not st.session_state["simple_tts_read_chat"]
        ):
            continue
        paid = item["paid"]
        if st.session_state["simple_tts_translate"] and st.session_state["simple_translation_enabled"]:
            target = _translation_target()
            translated = tr.get_translation(msg.get("text", ""), target)
            if translated is None:
                waiting.append(item)
                continue
        else:
            translated = ""
            target = ""
        text = translated or msg.get("text", "")
        lang = target.split("-")[0] if translated else st.session_state["simple_tts_language"]
        line = (
            format_announcement(msg.get("type", ""), msg.get("author", ""), text, lang)
            if paid else text
        )
        st.session_state["simple_tts_queue"].append({
            "id": str(msg.get("id") or f"{msg.get('platform')}:{time.time_ns()}"),
            "text": line,
            "lang": TTS_LANGUAGES.get(lang, TTS_LANGUAGES["auto"])[2],
            "rate": st.session_state["simple_tts_rate"] / 150,
            "volume": st.session_state["simple_tts_volume"],
            "priority": paid,
        })
    st.session_state["simple_tts_pending"] = waiting


def _accept_messages(messages: list[dict], *, is_backlog: bool = False) -> None:
    for msg in messages:
        if msg.get("type") == "enter":
            continue
        msg.setdefault("_simple_arrived", time.time_ns())
        if is_paid(msg) or is_gift(msg):
            st.session_state["simple_gifts"].append(msg)
            _record_profit(msg)
        else:
            st.session_state["simple_chat"].append(msg)
        if not is_backlog and not msg.get("history"):
            _queue_speech(msg)
    st.session_state["simple_chat"] = st.session_state["simple_chat"][-MAX_CHAT_DISPLAY:]
    st.session_state["simple_gifts"] = st.session_state["simple_gifts"][-MAX_CHAT_DISPLAY:]


def _record_profit(msg: dict) -> None:
    currency, value = msg.get("currency"), msg.get("value")
    if not currency or not value:
        return
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return
    if amount > 0:
        totals = st.session_state["simple_profit_totals"]
        totals[currency] = totals.get(currency, 0.0) + amount


def _poll_messages() -> None:
    now = time.monotonic()
    if now - st.session_state["simple_last_poll"] < CHAT_POLL_INTERVAL:
        return
    st.session_state["simple_last_poll"] = now

    video_id = st.session_state["simple_yt_video_id"]
    chat_id = st.session_state["simple_yt_chat_id"]
    if chat_id and video_id:
        first_fetch = not st.session_state["simple_yt_backlog_loaded"]
        messages, token, _ = yt.get_chat_messages(chat_id, st.session_state["simple_yt_page_token"])
        st.session_state["simple_yt_page_token"] = token
        st.session_state["simple_yt_backlog_loaded"] = True
        _accept_messages(messages, is_backlog=first_fetch)

    bili_listener: Optional[bili.DanmakuListener] = st.session_state["simple_bili_listener"]
    if bili_listener:
        _accept_messages(bili_listener.pop_messages())

    me_listener: Optional[me.MissEvanListener] = st.session_state["simple_me_listener"]
    if me_listener:
        _accept_messages(me_listener.pop_messages())

    if st.session_state["simple_translation_enabled"]:
        texts = [
            msg.get("text", "")
            for msg in (*st.session_state["simple_chat"][-80:], *st.session_state["simple_gifts"][-80:])
            if msg.get("text")
        ]
        tr.prefetch(texts, _translation_target())
    _flush_tts_pending()


def _speech_script() -> None:
    items = st.session_state["simple_tts_queue"]
    st.session_state["simple_tts_queue"] = []
    if not items:
        return
    payload = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    st.html(
        """<script>(() => {
          const w = window.parent || window, synth = w.speechSynthesis;
          if (!synth) return;
          const P = w.__mpcSimpleTts || (w.__mpcSimpleTts = {seen: new Set(), queue: [], speaking: false});
          const next = () => {
            if (P.speaking || synth.speaking) return;
            const item = P.queue.shift();
            if (!item) return;
            const u = new w.SpeechSynthesisUtterance(item.text);
            u.lang = item.lang || ''; u.rate = item.rate; u.volume = item.volume;
            P.speaking = true;
            u.onend = u.onerror = () => { P.speaking = false; setTimeout(next, 50); };
            synth.speak(u);
          };
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
        })();</script>""".replace("__ITEMS__", payload),
        unsafe_allow_javascript=True,
    )


def _source_username(site: str, info: dict) -> str:
    name = info.get("channel") if site == "youtube" else info.get("uname")
    if name:
        return str(name)
    configured = _SOURCES.get(site, "").strip().rstrip("/")
    fallback = configured.rsplit("/", 1)[-1].lstrip("@")
    return fallback or _PLATFORM_NAMES[site]


def _status_line(site: str, info: dict) -> None:
    label = _PLATFORM_NAMES[site]
    if site == "youtube" and not info:
        error = st.session_state["simple_yt_error"]
        text = (
            _t("{site}: {error}", site=label, error=error) if error
            else _t("{site}: checking status…", site=label)
        )
        live = False
    elif site == "youtube":
        if info.get("error"):
            text, live = _t("{site}: {error}", site=label, error=info["error"]), False
        else:
            live = info.get("live") if st.session_state["simple_yt_channel"] else (
                info.get("broadcast") == "live"
            )
            title = info.get("title", "")
            viewers = info.get("viewers", 0)
            detail = f" · {viewers:,} viewers" if live and viewers else ""
            if live:
                text = _t("🟢 {site} live{detail} — {title}", site=label, detail=detail, title=title)
            elif info.get("upcoming") or info.get("broadcast") == "upcoming":
                text = _t("🕒 {site} upcoming — {title}", site=label, title=title)
            elif info.get("ended"):
                text = _t("⚫ Stream ended — waiting for {username}", username=_source_username("youtube", info))
            else:
                text = _t("⚫ Waiting for {username}", username=_source_username("youtube", info))
            if st.session_state["simple_yt_error"]:
                text += f" · {st.session_state['simple_yt_error']}"
    else:
        listener = st.session_state[f"simple_{'bili' if site == 'bilibili' else 'me'}_listener"]
        error = st.session_state[f"simple_{'bili' if site == 'bilibili' else 'me'}_error"]
        info = st.session_state["simple_room_status"].get(site, {})
        live = False
        if info:
            live = info.get("live_status") == 1 if site == "bilibili" else bool(info.get("live"))
            if live:
                title = info.get("title", "")
                viewers = info.get("online", 0)
                detail = f" · {viewers:,} viewers" if viewers else ""
                text = _t("🟢 {site} live{detail} — {title}", site=label, detail=detail, title=title)
            else:
                text = _t("⚫ Waiting for {username}", username=_source_username(site, info))
        elif site in st.session_state["simple_room_status"]:
            text = _t("{site}: {error}", site=label, error=_t("couldn't fetch room status."))
        else:
            text = _t("{site}: {message}", site=label, message=_t("checking status…"))
        if error:
            text += f" · {error}"
        if listener:
            connected = (
                listener.running and listener.connected_uid is not None
                if site == "bilibili" else listener.running and listener.connected
            )
            if not connected:
                text += f" · {_t('connecting/retrying')}"

    color = "#42d392" if live else "inherit"
    escaped = html.escape(text)
    st.markdown(
        f'<div title="{escaped}" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
        f'max-width:100%;line-height:1.5;color:{color}">{escaped}</div>',
        unsafe_allow_html=True,
    )


def _feed_messages_html(messages: list[dict], browser_timezone: str) -> str:
    if not messages:
        return f'<div class="simple-feed-empty">{html.escape(_t("Waiting for messages…"))}</div>'
    cards = []
    for msg in reversed(messages[-MAX_CHAT_DISPLAY:]):
        platform = _PLATFORM_NAMES.get(msg.get("platform", ""), msg.get("platform", ""))
        raw_text = str(msg.get("text", ""))
        text = (
            emotes.text_to_html(
                raw_text,
                msg.get("emotes"),
                msg.get("sticker_url", ""),
                msg.get("sticker_caption", False),
            )
            if app_config.RENDER_CHAT_IMAGES
            else html.escape(raw_text)
        )
        stamp = _format_message_time(str(msg.get("timestamp", "")), browser_timezone)
        header = html.escape(f"{platform} · {msg.get('author', '')}" + (f" · {stamp}" if stamp else ""))
        translated = ""
        if st.session_state["simple_translation_enabled"] and msg.get("text"):
            result = tr.get_translation(msg["text"], _translation_target())
            if result:
                translated = f'<div class="simple-feed-translated">{html.escape(result)}</div>'
        cards.append(
            '<article class="simple-feed-card">'
            f'<div class="simple-feed-meta">{header}</div>'
            f'<div class="simple-feed-text">{text}</div>{translated}</article>'
        )
    return "".join(cards)


def _render_feeds() -> None:
    try:
        browser_timezone = st.context.timezone
    except (AttributeError, RuntimeError):
        browser_timezone = ""
    totals = st.session_state["simple_profit_totals"]
    summary = " · ".join(
        gift_utils.format_amount(currency, amount)
        for currency, amount in sorted(totals.items())
    ) or "—"
    gifts_html = _feed_messages_html(st.session_state["simple_gifts"], browser_timezone)
    chat_html = _feed_messages_html(st.session_state["simple_chat"], browser_timezone)
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            padding-top: 3.75rem;
            padding-bottom: 0;
        }
        .simple-feeds {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            grid-template-rows: minmax(0, 1fr);
            gap: 1rem;
            height: calc(100dvh - 3.75rem);
            min-height: 0;
        }
        .simple-feed-panel {
            display: flex;
            flex-direction: column;
            min-width: 0;
            min-height: 0;
        }
        .simple-feeds h2.simple-feed-title {
            margin: 0 0 .25rem;
            padding: 0;
            font-size: 1.25rem;
            font-weight: 600;
            line-height: 1.3;
        }
        .simple-feed-summary { margin: 0 0 .5rem; font-size: .85rem; opacity: .7; }
        .simple-feed-scroll {
            flex: 1 1 0;
            min-height: 0;
            overflow-y: auto;
            overscroll-behavior: contain;
        }
        .simple-feed-card {
            border: 1px solid rgba(128,128,128,.25);
            border-radius: .5rem;
            padding: .5rem;
            margin: .25rem 0;
        }
        .simple-feed-meta { font-size: .8rem; opacity: .7; margin-bottom: .25rem; }
        .simple-feed-text { white-space: pre-wrap; overflow-wrap: anywhere; }
        .simple-feed-translated { color: #60a5fa; white-space: pre-wrap; overflow-wrap: anywhere; }
        .simple-feed-empty { opacity: .7; }
        @media (max-width: 768px) {
            .simple-feeds {
                grid-template-columns: minmax(0, 1fr);
                grid-template-rows: minmax(0, 2fr) minmax(0, 3fr);
            }
        }
        </style>
        """
        f'<div class="simple-feeds">'
        '<section class="simple-feed-panel">'
        f'<h2 class="simple-feed-title">{html.escape("🎁 " + _t("Gifts & Super Chats"))}</h2>'
        f'<div class="simple-feed-summary">{html.escape(_t("Total profit (session): {amount}", amount=summary))}</div>'
        f'<div class="simple-feed-scroll">{gifts_html}</div>'
        '</section><section class="simple-feed-panel">'
        f'<h2 class="simple-feed-title">{html.escape("💬 " + _t("Chat"))}</h2>'
        f'<div class="simple-feed-scroll">{chat_html}</div>'
        '</section></div>',
        unsafe_allow_html=True,
    )


@st.fragment(run_every=_STATUS_INTERVAL)
def _update_status() -> None:
    _refresh_youtube()
    _refresh_room_status()
    _emit_live_notifications()
    for site in _SOURCES:
        _status_line(site, st.session_state["simple_yt_status"] if site == "youtube" else {})


with st.sidebar:
    st.header(_t("🎙️ Live Chat Monitor"))
    st.selectbox(
        _t("Language"),
        list(i18n.UI_LANGUAGES),
        format_func=lambda key: i18n.UI_LANGUAGES[key],
        key="simple_page_language",
    )
    st.divider()
    st.header(_t("Bilibili login"))
    st.text_input(
        _t("Bilibili cookie (paste Cookie header)"),
        key="simple_bili_cookie",
        type="password",
        on_change=_import_bilibili_cookie,
        help=_t("Paste the Bilibili Cookie header. It is verified before being saved."),
    )
    if st.session_state["simple_bili_login_name"]:
        st.success(_t("Logged in to Bilibili as {name}.", name=st.session_state["simple_bili_login_name"]))
    if st.session_state["simple_bili_cookie_error"]:
        st.error(st.session_state["simple_bili_cookie_error"])

if not _SOURCES:
    st.warning(_t(
        "No channels or room IDs are configured. Set YOUTUBE_CHANNEL, BILIBILI_ROOM_ID, or MISSEVAN_ROOM_ID "
        "in `.env` and restart."
    ))
else:
    with st.sidebar:
        _update_status()
        st.divider()
        st.header(_t("Translation"))
        st.toggle(
            _t("Translate chat"),
            key="simple_translation_enabled",
            help=_t("Translate every chat and gift message into the selected page language."),
        )
        st.divider()
        st.header(_t("Notifications"))
        st.toggle(_t("Notify when a channel goes live"), key="simple_notify_live")
        _notification_permission_button()
        st.divider()
        st.header(_t("🔊 Text-to-Speech"))
        st.toggle(_t("Enable TTS"), key="simple_tts_enabled")
        st.selectbox(
            _t("Speech language"),
            list(TTS_LANGUAGES),
            format_func=lambda key: _t(TTS_LANGUAGES[key][0]),
            key="simple_tts_language",
        )
        st.toggle(_t("Read translated chat"), key="simple_tts_translate")
        st.toggle(_t("Read chat messages"), key="simple_tts_read_chat")
        st.toggle(_t("Read gifts and Super Chats"), key="simple_tts_read_gifts")
        st.slider(_t("Speech speed (WPM)"), 80, 300, key="simple_tts_rate")
        st.slider(_t("Speech volume"), 0.0, 1.0, key="simple_tts_volume")
        st.caption(_t("Speech uses this browser's voices. Click the page once if your browser blocks audio."))


@st.fragment(run_every=max(1, CHAT_POLL_INTERVAL))
def _update_chat() -> None:
    _poll_messages()
    _speech_script()
    _render_feeds()


if _SOURCES:
    _update_chat()
