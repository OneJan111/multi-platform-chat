"""
Bilibili live stream recorder, modelled on BililiveRecorder
(https://github.com/BililiveRecorder/BililiveRecorder):

- asks getRoomPlayInfo for the room's stream at the preferred quality (qn) and picks the
  http_stream / flv / avc variant, like BililiveRecorder's GetCodecItemInStreamUrlAsync;
- downloads it with the same browser-style headers to
  "{roomid}-{name}/录制-{roomid}-{yyyyMMdd-HHmmss-fff}-{title}.flv";
- starts a new file whenever the stream drops while the room is still live, and stops once
  the room goes offline;
- optionally writes the room's danmaku next to each video in BililiveRecorder's XML format.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from xml.sax.saxutils import escape, quoteattr

import requests

QUALITIES: dict[int, str] = {
    10000: "原画 (Original)",
    400: "蓝光 (Blu-ray)",
    250: "超清 (Ultra HD)",
    150: "高清 (HD)",
    80: "流畅 (Smooth)",
}

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "zh-CN",
    "Origin": "https://live.bilibili.com",
    "Referer": "https://live.bilibili.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0"
    ),
}

_CHUNK = 64 * 1024
_READ_TIMEOUT = 20
_RETRY_DELAY = 5
_INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def fetch_play_info(room_id: str, qn: int, cookies: Optional[dict[str, str]] = None) -> dict:
    """getRoomPlayInfo for `room_id` at quality `qn` (signed by bilibili-api-python)."""
    from bilibili_api import live

    from src import bilibili

    if not bilibili.BILIBILI_LIB_OK:
        raise RuntimeError("Bilibili recording requires bilibili-api-python.")
    values = tuple((cookies or {}).get(k, "") for k in ("SESSDATA", "bili_jct", "buvid3", "DedeUserID"))
    room = live.LiveRoom(room_display_id=int(room_id), credential=bilibili._credential(values))
    try:
        resolution = live.ScreenResolution(int(qn))
    except ValueError:
        resolution = live.ScreenResolution.ORIGINAL
    return bilibili._run(room.get_room_play_info_v2(live_qn=resolution))


def select_flv_stream(play_info: dict) -> tuple[str, int]:
    """Return (url, qn) of the http_stream FLV/AVC stream, falling back to HEVC."""
    if play_info.get("live_status") != 1:
        raise RuntimeError("The Bilibili room is not live.")
    streams = ((play_info.get("playurl_info") or {}).get("playurl") or {}).get("stream") or []
    flv = next(
        (
            fmt
            for stream in streams
            if stream.get("protocol_name") == "http_stream"
            for fmt in stream.get("format") or []
            if fmt.get("format_name") == "flv"
        ),
        None,
    )
    codecs = (flv or {}).get("codec") or []
    for codec_name in ("avc", "hevc"):
        codec = next((c for c in codecs if c.get("codec_name") == codec_name), None)
        if not codec or not codec.get("base_url"):
            continue
        for url_info in codec.get("url_info") or []:
            host = url_info.get("host", "")
            if host:
                return f"{host.rstrip('/')}{codec['base_url']}{url_info.get('extra', '')}", int(
                    codec.get("current_qn") or 0
                )
    raise RuntimeError("Bilibili returned no FLV stream for this room.")


def _safe_name(text: str, limit: int = 80) -> str:
    text = _INVALID_NAME_CHARS.sub("_", str(text or "")).strip().rstrip(".")
    return text[:limit].strip() or "_"


def recording_path(root: Path | str, room_id: str, name: str, title: str, when: datetime) -> Path:
    """BililiveRecorder's default file name template."""
    stamp = when.strftime("%Y%m%d-%H%M%S-") + f"{when.microsecond // 1000:03d}"
    folder = _safe_name(f"{room_id}-{name}" if name else str(room_id))
    return Path(root) / folder / f"录制-{room_id}-{stamp}-{_safe_name(title)}.flv"


class DanmakuXmlWriter:
    """Danmaku file in BililiveRecorder's XML layout (playable with DanmakuFactory etc.)."""

    def __init__(self, path: Path, room_id: str, name: str, title: str, started: float):
        self.path = path
        self._started = started
        self._lock = threading.Lock()
        start = datetime.fromtimestamp(started).astimezone().isoformat()
        self._file = open(path, "w", encoding="utf-8", newline="\n")
        self._file.write(
            '<?xml version="1.0" encoding="utf-8"?>\n<i>'
            "<chatserver>chat.bilibili.com</chatserver><chatid>0</chatid><mission>0</mission>"
            "<maxlimit>1000</maxlimit><state>0</state><real_name>0</real_name><source>0</source>\n"
            f'<BililiveRecorderRecordInfo roomid={quoteattr(str(room_id))} name={quoteattr(name)} '
            f"title={quoteattr(title)} start_time={quoteattr(start)} />\n"
        )
        self._file.flush()

    def add(self, message: dict, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        offset = max(0.0, now - self._started)
        user = quoteattr(str(message.get("author", "")))
        uid = quoteattr(str(message.get("author_id", "")))
        text = str(message.get("text", ""))
        kind = message.get("type")
        if kind == "danmaku":
            color = message.get("color", 16777215)
            try:
                color = int(color)
            except (TypeError, ValueError):
                color = 16777215
            line = (
                f'<d p="{offset:.3f},1,25,{color},{int(now * 1000)},0,{escape(str(message.get("author_id", "")))},0" '
                f"user={user}>{escape(text)}</d>\n"
            )
        elif kind == "superchat":
            line = (
                f'<sc ts="{offset:.3f}" user={user} uid={uid} '
                f'price="{message.get("value", 0):g}">{escape(text)}</sc>\n'
            )
        elif kind == "gift":
            line = (
                f'<gift ts="{offset:.3f}" user={user} uid={uid} giftname={quoteattr(text)} '
                f'giftcount="{int(message.get("gift_count", 1) or 1)}" />\n'
            )
        else:
            return
        with self._lock:
            if not self._file.closed:
                self._file.write(line)
                self._file.flush()

    def close(self) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.write("</i>\n")
                self._file.close()


class BilibiliRecorder:
    """Record one Bilibili room in a background thread until it goes offline or is stopped."""

    def __init__(
        self,
        room_id: str,
        output_dir: Path | str,
        quality: int = 10000,
        cookies: Optional[dict[str, str]] = None,
        name: str = "",
        title: str = "",
        save_danmaku: bool = True,
        fetch: Callable[[str, int, Optional[dict]], dict] = fetch_play_info,
        session: Optional[requests.Session] = None,
        retry_delay: float = _RETRY_DELAY,
    ):
        self.room_id = str(room_id)
        self.output_dir = Path(output_dir)
        self.quality = int(quality)
        self.cookies = dict(cookies or {})
        self.name = name
        self.title = title
        self.save_danmaku = save_danmaku
        self._fetch = fetch
        self._session = session or requests.Session()
        self._retry_delay = retry_delay
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._response = None
        self._danmaku: Optional[DanmakuXmlWriter] = None
        self._state = {
            "status": "Idle",
            "file": "",
            "files": [],
            "bytes": 0,
            "total_bytes": 0,
            "started_at": 0.0,
            "qn": 0,
            "error": "",
        }

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._set(status="Starting", error="", started_at=time.time())
        self._thread = threading.Thread(
            target=self._run, name=f"bili-recorder-{self.room_id}", daemon=True
        )
        self._thread.start()

    def stop(self, wait: float = 0.0) -> None:
        self._stop.set()
        response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if wait and self._thread:
            self._thread.join(wait)

    def snapshot(self) -> dict:
        with self._lock:
            state = dict(self._state)
            state["files"] = list(self._state["files"])
        state["running"] = self.is_running
        return state

    def add_danmaku(self, message: dict) -> None:
        writer = self._danmaku
        if writer is not None:
            writer.add(message)

    def _set(self, **values) -> None:
        with self._lock:
            self._state.update(values)

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    info = self._fetch(self.room_id, self.quality, self.cookies)
                except Exception as exc:
                    self._set(status="Retrying", error=f"Could not get the stream URL: {exc}")
                    self._stop.wait(self._retry_delay)
                    continue
                if info.get("live_status") != 1:
                    self._set(status="Stream ended", error="")
                    return
                try:
                    url, qn = select_flv_stream(info)
                except Exception as exc:
                    self._set(status="Retrying", error=str(exc))
                    self._stop.wait(self._retry_delay)
                    continue
                self._set(qn=qn)
                try:
                    self._download(url)
                except Exception as exc:
                    if self._stop.is_set():
                        break
                    self._set(error=f"{type(exc).__name__}: {exc}")
                if not self._stop.is_set():
                    self._set(status="Reconnecting")
                    self._stop.wait(min(self._retry_delay, 2))
            self._set(status="Stopped")
        finally:
            self._response = None

    def _download(self, url: str) -> None:
        headers = dict(HEADERS)
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items() if v)
        response = self._session.get(url, headers=headers, stream=True, timeout=(10, _READ_TIMEOUT))
        self._response = response
        try:
            response.raise_for_status()
            chunks = response.iter_content(_CHUNK)
            first = next(chunks, b"")
            if not first.startswith(b"FLV"):
                raise RuntimeError("The stream server did not return FLV data.")
            started = time.time()
            path = recording_path(
                self.output_dir, self.room_id, self.name, self.title, datetime.fromtimestamp(started)
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            if self.save_danmaku:
                self._danmaku = DanmakuXmlWriter(
                    path.with_suffix(".xml"), self.room_id, self.name, self.title, started
                )
            with self._lock:
                self._state["files"].append(str(path))
                self._state.update(status="Recording", file=str(path), bytes=0, error="")
            with open(path, "wb") as output:
                for chunk in _prepend(first, chunks):
                    if self._stop.is_set():
                        break
                    if not chunk:
                        continue
                    output.write(chunk)
                    with self._lock:
                        self._state["bytes"] += len(chunk)
                        self._state["total_bytes"] += len(chunk)
        finally:
            self._response = None
            response.close()
            writer, self._danmaku = self._danmaku, None
            if writer is not None:
                writer.close()


def _prepend(first: bytes, rest):
    yield first
    yield from rest
