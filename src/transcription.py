"""Local live-audio transcription with FFmpeg and faster-whisper."""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

MODEL_SIZES = ("tiny", "base", "small")
SEGMENT_SECONDS = 8
_MODEL_LOCK = threading.Lock()
_MODELS: dict[str, object] = {}


def language_differs_from_target(source_language: str, target_language: str) -> bool:
    """Compare Whisper's detected language with the configured translation target."""
    source = (source_language or "").strip().lower().split("-", 1)[0]
    target = (target_language or "").strip().lower().split("-", 1)[0]
    return bool(source and target and source != target)


def resolve_youtube_audio_source(video_url: str) -> dict:
    """Resolve the best audio stream for an active YouTube live video."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("YouTube audio extraction requires yt-dlp. Install the project requirements.") from exc

    options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "socket_timeout": 15,
        "retries": 2,
        "fragment_retries": 2,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(video_url, download=False)
    if not info:
        raise RuntimeError("yt-dlp did not return stream information.")
    formats = info.get("requested_formats") or [info]
    audio = next(
        (item for item in formats if item.get("url") and item.get("acodec") != "none"),
        None,
    )
    if not audio:
        raise RuntimeError("No audio stream was found. Confirm the YouTube stream is live and publicly accessible.")
    return {
        "url": audio["url"],
        "headers": audio.get("http_headers") or info.get("http_headers") or {},
    }


def extract_bilibili_audio_url(play_info: dict, play_url: dict | None = None) -> str:
    """Select a signed stream URL from supported Bilibili play-info/play-URL responses."""
    if play_info.get("live_status") != 1:
        raise RuntimeError("The Bilibili room is not live.")

    playurl = (play_info.get("playurl_info") or {}).get("playurl") or {}
    streams = playurl.get("stream") or []
    for stream in streams:
        for media_format in stream.get("format") or []:
            for codec in media_format.get("codec") or []:
                base_url = codec.get("base_url")
                for url_info in codec.get("url_info") or []:
                    host = url_info.get("host", "")
                    extra = url_info.get("extra", "")
                    if host and base_url:
                        return f"{host.rstrip('/')}{base_url}{extra}"

    for stream in (play_url or {}).get("durl") or []:
        url = stream.get("url") if isinstance(stream, dict) else ""
        if url:
            return url
    raise RuntimeError("Bilibili returned no usable live stream URL.")


def _load_model(model_size: str):
    if model_size not in MODEL_SIZES:
        raise ValueError(f"Unsupported Whisper model size: {model_size}")
    with _MODEL_LOCK:
        model = _MODELS.get(model_size)
        if model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "Local transcription requires faster-whisper. Install the project requirements."
                ) from exc
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _MODELS[model_size] = model
        return model


class LiveTranscriber:
    """Capture live audio locally and transcribe segments with a local or injected recognizer."""

    def __init__(
        self,
        platform: str,
        source_id: str,
        source_resolver: Callable[[], str | dict],
        target_language: str,
        model_size: str = "base",
        translation_enabled: bool = True,
        ffmpeg_path: str | None = None,
        segment_recognizer: Callable[[Path], dict] | None = None,
    ):
        if platform not in ("youtube", "bilibili", "missevan"):
            raise ValueError(f"Unsupported transcription platform: {platform}")
        if model_size not in MODEL_SIZES:
            raise ValueError(f"Unsupported Whisper model size: {model_size}")
        self.platform = platform
        self.source_id = source_id
        self.target_language = target_language
        self.translation_enabled = translation_enabled
        self.model_size = model_size
        self._source_resolver = source_resolver
        self._segment_recognizer = segment_recognizer
        self._ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        self._lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._status = "idle"
        self._error = ""
        self._segments: deque[dict] = deque()

    def configure_translation(self, enabled: bool, target_language: str) -> None:
        """Update shared translation settings while this session is transcribing."""
        with self._lock:
            self.translation_enabled = enabled
            self.target_language = target_language

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._status in {
                "resolving_stream", "loading_model", "connecting", "listening", "stopping",
            }

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self._status,
                "error": self._error,
                "segments": list(self._segments),
            }

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("This transcription session is already running.")
            if not self._ffmpeg_path:
                raise RuntimeError("FFmpeg was not found. Install FFmpeg and add it to PATH.")
            self._stop_event.clear()
            self._error = ""
            self._status = "resolving_stream"
            self._thread = threading.Thread(
                target=self._run,
                name=f"transcription-{self.platform}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            if self._status in {
                "resolving_stream", "loading_model", "connecting", "listening",
            }:
                self._status = "stopping"
        with self._process_lock:
            process = self._process
            if process and process.poll() is None:
                process.terminate()

    def _set_status(self, status: str, error: str = "") -> None:
        with self._lock:
            self._status = status
            self._error = error

    def _append_segment(self, segment: dict) -> None:
        with self._lock:
            self._segments.append(segment)

    def _run(self) -> None:
        process = None
        ended_normally = False
        try:
            resolved_source = self._source_resolver()
            if isinstance(resolved_source, str):
                stream_url, headers = resolved_source, {}
            elif isinstance(resolved_source, dict):
                stream_url = resolved_source.get("url", "")
                headers = resolved_source.get("headers") or {}
            else:
                raise RuntimeError("The audio stream resolver returned an unsupported result.")
            if not stream_url:
                raise RuntimeError("The platform did not return an audio stream URL.")
            if not isinstance(headers, dict):
                raise RuntimeError("The audio stream resolver returned invalid HTTP headers.")
            if self._stop_event.is_set():
                self._set_status("stopped")
                return

            self._set_status("loading_model")
            model = None if self._segment_recognizer else _load_model(self.model_size)
            if self._stop_event.is_set():
                self._set_status("stopped")
                return

            self._set_status("connecting")
            with tempfile.TemporaryDirectory(prefix="streaming-transcription-") as temp_dir:
                output_pattern = str(Path(temp_dir) / "segment_%06d.wav")
                command = [
                    self._ffmpeg_path,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel", "error",
                    "-reconnect", "1",
                    "-reconnect_streamed", "1",
                    "-reconnect_delay_max", "5",
                ]
                if headers:
                    header_block = "".join(f"{name}: {value}\r\n" for name, value in headers.items())
                    command.extend(["-headers", header_block])
                command.extend([
                    "-i", stream_url,
                    "-vn",
                    "-ac", "1",
                    "-ar", "16000",
                    "-c:a", "pcm_s16le",
                    "-f", "segment",
                    "-segment_time", str(SEGMENT_SECONDS),
                    "-reset_timestamps", "1",
                    output_pattern,
                ])
                processed: set[str] = set()
                with tempfile.TemporaryFile() as error_log:
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=error_log,
                    )
                    with self._process_lock:
                        self._process = process
                    self._set_status("listening")

                    while process.poll() is None:
                        if self._stop_event.is_set():
                            process.terminate()
                            break
                        files = sorted(Path(temp_dir).glob("segment_*.wav"))
                        for audio_file in files[:-1]:
                            if audio_file.name not in processed:
                                self._transcribe_file(model, audio_file)
                                processed.add(audio_file.name)
                        time.sleep(0.4)

                    try:
                        return_code = process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        return_code = process.wait(timeout=5)
                    if not self._stop_event.is_set() and return_code != 0:
                        error_log.flush()
                        error_log.seek(0)
                        detail = error_log.read().decode("utf-8", errors="replace")[-1200:].strip()
                        if detail:
                            detail = detail.replace(stream_url, "[stream URL]")
                            log.error("FFmpeg transcription input failed: %s", detail)
                        raise RuntimeError(
                            "FFmpeg could not read the live audio stream. Confirm the room is live and try again."
                        )

                    for audio_file in sorted(Path(temp_dir).glob("segment_*.wav")):
                        if audio_file.name not in processed:
                            self._transcribe_file(model, audio_file)
                            processed.add(audio_file.name)
                    ended_normally = not self._stop_event.is_set()

            self._set_status("ended" if ended_normally else "stopped")
        except Exception as exc:
            log.exception("Live transcription failed for %s.", self.platform)
            self._set_status("failed", str(exc))
        finally:
            with self._process_lock:
                self._process = None
            if process and process.poll() is None:
                process.terminate()

    def _transcribe_file(self, model, audio_file: Path) -> None:
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
        try:
            timestamp = datetime.fromtimestamp(audio_file.stat().st_mtime).astimezone().strftime("%H:%M:%S")
            recognized = self._segment_recognizer(audio_file) if self._segment_recognizer else None
            if recognized is None:
                transcribed, info = model.transcribe(str(audio_file), beam_size=5, vad_filter=True)
                parts = [part for part in transcribed if part.text.strip()]
                original = " ".join(part.text.strip() for part in parts).strip()
                detected_language = getattr(info, "language", "")
                segment_offset = parts[0].start if parts else 0
            else:
                original = str(recognized.get("original") or "").strip()
                detected_language = str(recognized.get("detected_language") or "")
                segment_offset = 0
            if not original:
                return
            chunk_index = int(audio_file.stem.removeprefix("segment_"))
            result = {
                "time": timestamp,
                "start_seconds": chunk_index * SEGMENT_SECONDS + segment_offset,
                "original": original,
                "translated": str((recognized or {}).get("translated") or ""),
                "translation_error": "",
                "detected_language": detected_language,
            }
            if recognized is not None:
                self._append_segment(result)
                return
            with self._lock:
                translation_enabled = self.translation_enabled
                target_language = self.target_language
            if translation_enabled and language_differs_from_target(detected_language, target_language):
                try:
                    from src import translate
                    result["translated"], _ = translate.translate(original, target_language)
                except Exception as exc:
                    result["translation_error"] = str(exc)
                    log.exception("Transcription translation failed.")
            self._append_segment(result)
        except Exception as exc:
            log.exception("Whisper failed to transcribe an audio segment.")
            self._append_segment({
                "time": timestamp,
                "original": "",
                "translated": "",
                "translation_error": "",
                "transcription_error": str(exc),
            })
        finally:
            audio_file.unlink(missing_ok=True)
