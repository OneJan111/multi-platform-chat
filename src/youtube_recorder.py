"""Record a YouTube live stream with yt-dlp and FFmpeg."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

_RETRY_DELAY = 5
_INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def resolve_live_source(video_id: str) -> dict:
    """Resolve a live YouTube video to a muxed source URL and request headers."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError(
            "YouTube recording requires yt-dlp. Install the project requirements."
        ) from exc

    options = {
        "format": "best[acodec!=none][vcodec!=none]/bestvideo+bestaudio",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "socket_timeout": 15,
        "retries": 2,
        "fragment_retries": 2,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}",
            download=False,
        )
    if not info:
        raise RuntimeError("yt-dlp did not return stream information.")
    formats = info.get("requested_formats") or [info]
    available = [
        item for item in formats
        if item.get("url")
    ]
    muxed = next(
        (
            item for item in available
            if item.get("acodec") != "none"
            and item.get("vcodec") != "none"
        ),
        None,
    )
    if muxed is not None:
        sources = [muxed]
    else:
        video = next(
            (item for item in available if item.get("vcodec") != "none"),
            None,
        )
        audio = next(
            (item for item in available if item.get("acodec") != "none"),
            None,
        )
        sources = [video, audio] if video and audio and video is not audio else []
    if not sources:
        raise RuntimeError(
            "No complete live audio/video stream was found for this YouTube video."
        )
    return {
        "sources": [
            {
                "url": source["url"],
                "headers": source.get("http_headers") or info.get("http_headers") or {},
            }
            for source in sources
        ],
    }


def _safe_name(value: str, limit: int = 100) -> str:
    cleaned = _INVALID_NAME_CHARS.sub("_", str(value or "")).strip().rstrip(".")
    return cleaned[:limit].strip() or "_"


def recording_path(
    root: Path | str, video_id: str, name: str, title: str, when: datetime
) -> Path:
    stamp = when.strftime("%Y%m%d-%H%M%S-") + f"{when.microsecond // 1000:03d}"
    folder = _safe_name(f"{video_id}-{name}" if name else video_id)
    return Path(root) / folder / (
        f"录制-{video_id}-{stamp}-{_safe_name(title)}.mkv"
    )


class YouTubeRecorder:
    """Record one YouTube live stream until stopped or the room goes offline."""

    def __init__(
        self,
        video_id: str,
        output_dir: Path | str,
        source_resolver: Callable[[], dict],
        name: str = "",
        title: str = "",
        ffmpeg_path: str | None = None,
        retry_delay: float = _RETRY_DELAY,
    ):
        self.video_id = str(video_id)
        self.output_dir = Path(output_dir)
        self.name = name
        self.title = title
        self._source_resolver = source_resolver
        self._ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        self._retry_delay = retry_delay
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._current_file_bytes = 0
        self._state = {
            "status": "Idle",
            "file": "",
            "files": [],
            "total_bytes": 0,
            "started_at": 0.0,
            "error": "",
        }

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.is_running:
            return
        if not self._ffmpeg_path:
            raise RuntimeError("FFmpeg was not found. Install FFmpeg and add it to PATH.")
        self._stop.clear()
        self._set(status="Starting", error="", started_at=time.time())
        self._thread = threading.Thread(
            target=self._run,
            name=f"youtube-recorder-{self.video_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, wait: float = 0.0) -> None:
        self._stop.set()
        with self._process_lock:
            process = self._process
            if process and process.poll() is None:
                process.terminate()
        if wait and self._thread:
            self._thread.join(wait)

    def snapshot(self) -> dict:
        with self._lock:
            state = dict(self._state)
            state["files"] = list(self._state["files"])
        state["running"] = self.is_running
        return state

    def _set(self, **values) -> None:
        with self._lock:
            self._state.update(values)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                source = self._source_resolver()
                inputs = source.get("sources") or []
                if not inputs or any(not item.get("url") for item in inputs):
                    raise RuntimeError("yt-dlp did not return complete live stream URLs.")
            except Exception as exc:
                if "not live" in str(exc).lower() or "stream ended" in str(exc).lower():
                    self._set(status="Stream ended", error="")
                    return
                self._set(status="Retrying", error=f"Could not get the stream URL: {exc}")
                self._stop.wait(self._retry_delay)
                continue
            if self._stop.is_set():
                break

            started = time.time()
            path = recording_path(
                self.output_dir,
                self.video_id,
                self.name,
                self.title,
                datetime.fromtimestamp(started),
            )
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                command = [self._ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error"]
                for item in inputs:
                    headers = item.get("headers") or {}
                    header_value = "".join(
                        f"{key}: {value}\r\n" for key, value in headers.items()
                    )
                    if header_value:
                        command.extend(["-headers", header_value])
                    command.extend(["-i", str(item["url"])])
                if len(inputs) == 1:
                    command.extend(["-map", "0"])
                else:
                    command.extend(["-map", "0:v:0", "-map", "1:a:0"])
                command.extend([
                    "-c", "copy", "-f", "matroska", "-y", str(path),
                ])
                with tempfile.TemporaryFile() as error_log:
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=error_log,
                    )
                    with self._process_lock:
                        self._process = process
                    with self._lock:
                        self._state["files"].append(str(path))
                        self._state.update(
                            status="Recording",
                            file=str(path),
                            started_at=started,
                            error="",
                        )
                        self._current_file_bytes = 0

                    while process.poll() is None and not self._stop.wait(0.5):
                        self._update_file_size(path)
                    if self._stop.is_set() and process.poll() is None:
                        process.terminate()
                    try:
                        return_code = process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        return_code = process.wait(timeout=5)
                    self._update_file_size(path)
                    with self._process_lock:
                        self._process = None

                    if self._stop.is_set():
                        self._set(status="Stopped")
                        return
                    if return_code != 0:
                        error_log.flush()
                        error_log.seek(0)
                        detail = error_log.read().decode(
                            "utf-8", errors="replace"
                        )[-1000:].strip()
                        for item in inputs:
                            detail = detail.replace(str(item["url"]), "[stream URL]")
                        self._set(
                            status="Reconnecting",
                            error=detail or "FFmpeg could not read the live stream.",
                        )
                    else:
                        self._set(status="Reconnecting", error="")
            except Exception as exc:
                with self._process_lock:
                    self._process = None
                if self._stop.is_set():
                    self._set(status="Stopped")
                    return
                log.exception("YouTube recording failed for video %s.", self.video_id)
                self._set(status="Reconnecting", error=f"{type(exc).__name__}: {exc}")
            self._stop.wait(self._retry_delay)

        self._set(status="Stopped")

    def _update_file_size(self, path: Path) -> None:
        try:
            size = path.stat().st_size
        except OSError:
            return
        with self._lock:
            self._state["total_bytes"] += size - self._current_file_bytes
            self._current_file_bytes = size
