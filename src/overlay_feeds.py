"""Standalone overlay feeds: /overlay?youtube=@handle&bilibili=ROOM&missevan=ROOM reads chat itself.

No dashboard or login is needed: the overlay server connects to each site anonymously, the same
way a logged-out viewer would. Every Browser Source asking for the same sites shares one feed;
feeds nobody has asked for in IDLE_SECONDS are stopped.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import NamedTuple, Optional

from src import user_login

IDLE_SECONDS = 120
MAX_FEEDS = 20
KEEP_PER_SITE = 50          # chat and paid events kept per site (the overlay shows at most 50)
YT_CHANNEL_CHECK = 60       # seconds between "is the channel live?" checks
BILI_RETRY = 30             # seconds before reconnecting a dropped Bilibili listener


class FeedKey(NamedTuple):
    youtube: str = ""       # channel URL (https://www.youtube.com/@x) or 11-char video ID
    bilibili: str = ""      # room ID
    missevan: str = ""      # room ID

    def __bool__(self) -> bool:
        return any(self)


def parse_key(query: dict[str, list[str]]) -> FeedKey:
    """Normalise ?youtube=…&bilibili=…&missevan=… (links, @handles, IDs); invalid values are dropped."""
    def first(*names: str) -> str:
        for name in names:
            value = (query.get(name) or [""])[0].strip()
            if value:
                return value
        return ""

    from src import bilibili, missevan, youtube_web

    yt_value = first("youtube", "yt")
    youtube = ""
    if yt_value:
        youtube = youtube_web.channel_url(yt_value)
        if not youtube:
            from src.youtube import extract_video_id
            youtube = extract_video_id(yt_value)
    return FeedKey(
        youtube=youtube,
        bilibili=bilibili.parse_room_id(first("bilibili", "bili")),
        missevan=missevan.parse_room_id(first("missevan", "me", "maoer")),
    )


class Feed:
    """Reads the sites of one FeedKey in background threads and keeps the latest messages."""

    def __init__(self, key: FeedKey):
        from src.filters import make_default_filter

        self.key = key
        self.last_used = time.time()
        self._lock = threading.Lock()
        self._chat: dict[str, deque] = {}
        self._paid: dict[str, deque] = {}
        self._stop = threading.Event()
        self._filter = make_default_filter()
        self._bili = None
        self._bili_retry_at = 0.0
        self._me = None
        self._threads: list[threading.Thread] = []

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self.key.youtube:
            self._spawn(self._youtube_loop, "youtube")
        if self.key.bilibili or self.key.missevan:
            if self.key.missevan:
                from src.missevan import MissEvanListener
                with user_login.using({}):  # anonymous: never borrow a dashboard user's login
                    self._me = MissEvanListener(self.key.missevan)
                self._me.start()
            self._spawn(self._pump_loop, "pump")

    def stop(self) -> None:
        self._stop.set()
        for listener in (self._bili, self._me):
            if listener:
                listener.stop()

    def _spawn(self, target, name: str) -> None:
        thread = threading.Thread(target=target, name=f"overlay-feed-{name}", daemon=True)
        thread.start()
        self._threads.append(thread)

    # ── messages ───────────────────────────────────────────────────────────────

    def add(self, messages: list[dict]) -> None:
        from src.tts import is_gift, is_paid

        if not messages:
            return
        with self._lock:
            allowed, _ = self._filter.filter_messages(messages)
            for msg in allowed:
                site = msg.get("platform", "")
                if is_paid(msg) or is_gift(msg):
                    self._paid.setdefault(site, deque(maxlen=KEEP_PER_SITE)).append(msg)
                elif msg.get("type") in ("textMessageEvent", "danmaku"):
                    self._chat.setdefault(site, deque(maxlen=KEEP_PER_SITE)).append(msg)

    def messages(self) -> tuple[list[dict], list[dict]]:
        """(chat, paid) in arrival order; marks the feed as in use."""
        self.last_used = time.time()
        with self._lock:
            chat = sorted((m for q in self._chat.values() for m in q), key=_order)
            paid = sorted((m for q in self._paid.values() for m in q), key=_order)
        return chat, paid

    # ── site readers ───────────────────────────────────────────────────────────

    def _pump_loop(self) -> None:
        """Move Bilibili / MissEvan messages into the feed; reconnect Bilibili when it drops."""
        from src.bilibili import DanmakuListener

        while not self._stop.is_set():
            if self.key.bilibili and (self._bili is None or not self._bili.running):
                if self._bili is not None:
                    self.add(_stamp(self._bili.pop_messages()))
                if time.time() >= self._bili_retry_at:
                    self._bili_retry_at = time.time() + BILI_RETRY
                    with user_login.using({}):
                        self._bili = DanmakuListener(self.key.bilibili)
                    self._bili.start()
            if self._bili is not None:
                self.add(_stamp(self._bili.pop_messages()))
            if self._me is not None:
                self.add(_stamp(self._me.pop_messages()))
            self._stop.wait(1)

    def _youtube_loop(self) -> None:
        from src import youtube_web

        channel = self.key.youtube if "://" in self.key.youtube else ""
        while not self._stop.is_set():
            video = self.key.youtube if not channel else ""
            if channel:
                info = youtube_web.find_live_video(channel)
                video = info["video_id"] if info.get("live") else ""
                if not video:
                    self._stop.wait(YT_CHANNEL_CHECK)
                    continue
            self._read_youtube(video, follow_channel=bool(channel))
            if not channel:
                self._stop.wait(10)  # a single video: retry in case its chat opens later

    def _read_youtube(self, video: str, follow_channel: bool) -> None:
        from src import youtube_web

        continuation, seen = "", OrderedDict()
        checked = time.time()
        while not self._stop.is_set():
            msgs, continuation, wait_ms = youtube_web.get_messages(video, continuation, seen=seen)
            self.add(_stamp(msgs))
            if follow_channel and time.time() - checked >= YT_CHANNEL_CHECK:
                checked = time.time()
                status = youtube_web.get_video_status(video)
                if status and status.get("broadcast") != "live":
                    return  # stream ended: go back to watching the channel
            if not continuation and not msgs:
                if follow_channel:
                    self._stop.wait(wait_ms / 1000)
                    continue
                return
            self._stop.wait(max(2.0, min(wait_ms / 1000, 10.0)))


def _stamp(messages: list[dict]) -> list[dict]:
    now = time.time_ns()
    for i, msg in enumerate(messages):
        msg.setdefault("_arrived", now + i)
    return messages


def _order(msg: dict) -> int:
    return msg.get("_arrived", 0)


# ── feed registry ─────────────────────────────────────────────────────────────

_feeds: dict[FeedKey, Feed] = {}
_lock = threading.Lock()
_reaper: Optional[threading.Thread] = None


def get(key: FeedKey) -> Optional[Feed]:
    """The running feed for `key`, starting it if needed; None when MAX_FEEDS are already busy."""
    global _reaper
    if not key:
        return None
    with _lock:
        _reap_locked()
        feed = _feeds.get(key)
        if feed is None:
            if len(_feeds) >= MAX_FEEDS:
                return None
            feed = _feeds[key] = Feed(key)
            feed.start()
        if _reaper is None or not _reaper.is_alive():
            _reaper = threading.Thread(target=_reap_forever, name="overlay-feed-reaper", daemon=True)
            _reaper.start()
        return feed


def _reap_locked() -> None:
    cutoff = time.time() - IDLE_SECONDS
    for key in [k for k, f in _feeds.items() if f.last_used < cutoff]:
        _feeds.pop(key).stop()


def _reap_forever() -> None:
    while True:
        time.sleep(30)
        with _lock:
            _reap_locked()
            if not _feeds:
                return


def stop_all() -> None:
    with _lock:
        for feed in _feeds.values():
            feed.stop()
        _feeds.clear()
