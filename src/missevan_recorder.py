"""Record a live MissEvan HLS stream with FFmpeg."""
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

_INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RETRY_DELAY = 5


def _safe_name(value: str, limit: int = 80) -> str:
    cleaned = _INVALID_NAME_CHARS.sub("_", str(value or "")).strip().rstrip(".")
    return cleaned[:limit].strip() or "_"


def recording_path(
    root: Path | str, room_id: str, name: str, title: str, when: datetime
) -> Path:
    stamp = when.strftime("%Y%m%d-%H%M%S-") + f"{when.microsecond // 1000:03d}"
    folder = _safe_name(f"{room_id}-{name}" if name else str(room_id))
    return Path(root) / folder / f"录制-{room_id}-{stamp}-{_safe_name(title)}.mkv"


class MissEvanRecorder:
    """Record one MissEvan room until it goes offline or recording is stopped."""

    def __init__(
        self,
        room_id: str,
        output_dir: Path | str,
        source_resolver: Callable[[], str],
        name: str = "",
        title: str = "",
        ffmpeg_path: str | None = None,
        retry_delay: float = _RETRY_DELAY,
    ):
        self.room_id = str(room_id)
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
            target=self._run, name=f"missevan-recorder-{self.room_id}", daemon=True
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
                stream_url = self._source_resolver()
                if not stream_url:
                    raise RuntimeError("MissEvan did not return a live stream URL.")
            except Exception as exc:
                if "not live" in str(exc).lower():
                    self._set(status="Stream ended", error="")
                    return
                self._set(status="Retrying", error=f"Could not get the stream URL: {exc}")
                self._stop.wait(self._retry_delay)
                continue
            if self._stop.is_set():
                self._set(status="Stopped")
                return

            started = time.time()
            path = recording_path(
                self.output_dir, self.room_id, self.name, self.title,
                datetime.fromtimestamp(started),
            )
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile() as error_log:
                    process = subprocess.Popen(
                        [
                            self._ffmpeg_path,
                            "-nostdin",
                            "-hide_banner",
                            "-loglevel", "error",
                            "-y",
                            "-i", stream_url,
                            "-map", "0",
                            "-c", "copy",
                            "-f", "matroska",
                            str(path),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=error_log,
                    )
                    with self._process_lock:
                        self._process = process
                    with self._lock:
                        self._state["files"].append(str(path))
                        self._state.update(
                            status="Recording", file=str(path), started_at=started,
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
                        detail = error_log.read().decode("utf-8", errors="replace")[-1000:].strip()
                        detail = detail.replace(stream_url, "[stream URL]")
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
                log.exception("MissEvan recording failed for room %s.", self.room_id)
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
