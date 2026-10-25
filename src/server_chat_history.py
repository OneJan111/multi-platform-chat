"""In-memory chat history shared by Streamlit sessions in one server process."""
from __future__ import annotations

import threading
import time
import logging

from src import bilibili as bili
from src import missevan as me
from src import youtube as yt
from src import youtube_web as ytw
from src.config import SIMPLE_CHAT_POLL_INTERVAL, SIMPLE_STATUS_POLL_INTERVAL
from src.tts import is_gift, is_paid

_LOGGER = logging.getLogger(__name__)


class ServerChatHistory:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chat: list[dict] = []
        self._gifts: list[dict] = []
        self._profit_totals: dict[str, float] = {}
        self._message_ids: set[str] = set()

    def append(self, msg: dict, *, is_gift: bool) -> bool:
        message_id = msg.get("id")
        dedupe_key = f"{msg.get('platform', '')}:{message_id}" if message_id else ""
        with self._lock:
            if dedupe_key and dedupe_key in self._message_ids:
                return False
            if dedupe_key:
                self._message_ids.add(dedupe_key)
            (self._gifts if is_gift else self._chat).append(msg)
            if is_gift:
                self._record_profit(msg)
        return True

    def append_many(self, messages: list[dict], *, is_backlog: bool = False) -> None:
        for msg in messages:
            if msg.get("type") == "enter":
                continue
            msg.setdefault("_simple_arrived", time.time_ns())
            if is_backlog:
                msg.setdefault("history", True)
            self.append(msg, is_gift=is_paid(msg) or is_gift(msg))

    def chat(self) -> list[dict]:
        with self._lock:
            return list(self._chat)

    def gifts(self) -> list[dict]:
        with self._lock:
            return list(self._gifts)

    def profit_totals(self) -> dict[str, float]:
        with self._lock:
            return dict(self._profit_totals)

    def _record_profit(self, msg: dict) -> None:
        currency, value = msg.get("currency"), msg.get("value")
        if not currency or not value:
            return
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return
        if amount > 0:
            self._profit_totals[currency] = self._profit_totals.get(currency, 0.0) + amount


class ServerChatPoller:
    def __init__(self, history: ServerChatHistory, sources: dict[str, str]) -> None:
        self._history = history
        self._sources = sources
        self._channel = ytw.channel_url(sources.get("youtube", ""))
        self._video_id = "" if self._channel else yt.extract_video_id(sources.get("youtube", ""))
        self._chat_id = ""
        self._page_token = ""
        self._youtube_backlog_loaded = False
        self._last_status = 0.0
        self._status_polling_paused = threading.Event()
        self._bili_listener = None
        self._me_listener = None
        self._listener_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="server-chat-poller", daemon=True)
        self._start_listeners()
        self._thread.start()

    def _start_listeners(self) -> None:
        if self._sources.get("bilibili"):
            self._bili_listener = bili.DanmakuListener(self._sources["bilibili"])
            if not self._bili_listener.start():
                _LOGGER.error(
                    "Bilibili listener couldn't start: %s", self._bili_listener.error
                )
                self._bili_listener = None
        if self._sources.get("missevan"):
            self._me_listener = me.MissEvanListener(self._sources["missevan"])
            if not self._me_listener.start():
                _LOGGER.error(
                    "MissEvan listener couldn't start: %s", self._me_listener.error
                )
                self._me_listener = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                _LOGGER.exception("Unexpected error polling server chat")
            self._stop.wait(SIMPLE_CHAT_POLL_INTERVAL)

    @property
    def status_polling_paused(self) -> bool:
        return self._status_polling_paused.is_set()

    def pause_status_polling(self) -> None:
        self._status_polling_paused.set()

    def stop(self) -> None:
        self._stop.set()
        for listener in (self._bili_listener, self._me_listener):
            if listener:
                listener.stop()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def restart_bilibili(self) -> None:
        with self._listener_lock:
            if self._bili_listener:
                self._history.append_many(self._bili_listener.pop_messages())
                self._bili_listener.stop()
            self._bili_listener = bili.DanmakuListener(self._sources["bilibili"])
            if not self._bili_listener.start():
                _LOGGER.error(
                    "Bilibili listener couldn't start: %s", self._bili_listener.error
                )
                self._bili_listener = None

    def poll_once(self) -> None:
        now = time.monotonic()
        if not self.status_polling_paused and (
            now - self._last_status >= SIMPLE_STATUS_POLL_INTERVAL
        ):
            self._last_status = now
            try:
                live = self._refresh_youtube()
                live = self._refresh_room_status() or live
                if live:
                    self.pause_status_polling()
            except Exception:
                _LOGGER.exception("Unexpected error refreshing YouTube live chat")

        if self._chat_id and self._video_id:
            try:
                first_fetch = not self._youtube_backlog_loaded
                messages, self._page_token, _ = yt.get_chat_messages(
                    self._chat_id, self._page_token
                )
                self._history.append_many(messages, is_backlog=first_fetch)
                self._youtube_backlog_loaded = True
            except Exception:
                _LOGGER.exception("Unexpected error polling YouTube chat")

        with self._listener_lock:
            bili_listener = self._bili_listener
            me_listener = self._me_listener
        if bili_listener:
            try:
                self._history.append_many(bili_listener.pop_messages())
            except Exception:
                _LOGGER.exception("Unexpected error polling Bilibili chat")
        if me_listener:
            try:
                self._history.append_many(me_listener.pop_messages())
            except Exception:
                _LOGGER.exception("Unexpected error polling MissEvan chat")

    def _refresh_youtube(self) -> bool:
        join_video_id = ""
        is_live = False
        if self._channel:
            info = ytw.find_live_video(self._channel)
            if info.get("live") and info.get("video_id"):
                is_live = True
                video_id = info["video_id"]
                if video_id != self._video_id:
                    self._reset_youtube_chat()
                self._video_id = video_id
                join_video_id = video_id
            elif self._chat_id and self._video_id:
                current = ytw.get_video_status(self._video_id)
                if current and current.get("broadcast") != "live":
                    self._reset_youtube_chat()
        elif self._video_id:
            info = yt.get_video_live_status(self._video_id)
            if info and info.get("broadcast") == "live":
                is_live = True
                join_video_id = self._video_id
            elif info:
                self._reset_youtube_chat()

        if join_video_id and not self._chat_id:
            self._chat_id, _ = yt.resolve_live_chat_id(join_video_id)
            self._page_token = ""
            self._youtube_backlog_loaded = False
        return is_live

    def _refresh_room_status(self) -> bool:
        is_live = False
        if self._sources.get("bilibili"):
            info = bili.get_room_info(self._sources["bilibili"])
            is_live = bool(info and info.get("live_status") == 1)
        if self._sources.get("missevan"):
            info = me.get_room_info(self._sources["missevan"])
            is_live = bool(info and info.get("live")) or is_live
        return is_live

    def _reset_youtube_chat(self) -> None:
        self._chat_id = ""
        self._page_token = ""
        self._youtube_backlog_loaded = False
        if self._channel:
            self._video_id = ""
