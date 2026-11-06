"""HTML streaming recognition adapted from streaming-transcribe-translate.

The reference project's recognition adapters and segmentation parameters are
MIT-licensed; see THIRD_PARTY_NOTICES for attribution and license.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
import logging
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading

from src import transcription

log = logging.getLogger(__name__)
SAMPLE_RATE = 16000
FRAME_SIZE = 512
MODEL_SIZES = ("reazon", *transcription.MODEL_SIZES)


@dataclass(frozen=True)
class CaptionOptions:
    source_language: str = ""
    models_path: str = ""
    provider: str = "dashboard"
    api_base: str = "https://api.openai.com/v1"
    api_model: str = "gpt-4o-mini"
    api_key: str = field(default="", repr=False)
    background: str = ""
    glossary: str = ""
    context_sentences: int = 0

    def validate(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "context_sentences":
                if type(value) is not int or not 0 <= value <= 8:
                    raise ValueError("Previous sentences must be 0-8.")
            elif not isinstance(value, str) or len(value) > (10000 if field.name in ("background", "glossary") else 2000):
                raise ValueError(f"Invalid transcription option: {field.name}")
        if self.source_language not in ("", "ja", "en", "zh", "ko"):
            raise ValueError("Invalid source language.")
        if self.provider not in ("dashboard", "openai_compatible"):
            raise ValueError("Invalid transcription translation provider.")
        if self.models_path and not Path(self.models_path).is_absolute():
            raise ValueError("Speech models folder must be an absolute path.")
        from src.openai_compatible_translate import validate_api_base
        validate_api_base(self.api_base)
        if not self.api_model.strip() or any(char.isspace() for char in self.api_model):
            raise ValueError("Enter the exact translation model ID without spaces.")
        if "\r" in self.api_key or "\n" in self.api_key:
            raise ValueError("Invalid API key.")


TRANSCRIPTION_DEFAULTS = {
    "transcribe_model": "reazon", "transcribe_target_language": "en", "transcribe_translate": True,
    **{f"transcribe_{field.name}": getattr(CaptionOptions(), field.name)
       for field in fields(CaptionOptions) if field.name != "api_key"},
}


def caption_options(settings: dict, api_key: str = "") -> CaptionOptions:
    options = CaptionOptions(
        **{field.name: settings[f"transcribe_{field.name}"]
           for field in fields(CaptionOptions) if field.name != "api_key"}, api_key=api_key)
    options.validate()
    if settings["transcribe_model"] not in MODEL_SIZES:
        raise ValueError("Unsupported speech model.")
    if settings["transcribe_target_language"] not in ("en", "zh-CN", "zh-TW", "ja", "ko"):
        raise ValueError("Invalid transcription translation target.")
    if settings["transcribe_model"] == "reazon" and options.source_language in ("zh", "ko"):
        raise ValueError("Select a Whisper model for Chinese or Korean speech.")
    return options


def models_root(folder: str = "") -> Path:
    if folder:
        root = Path(folder)
        if not (root / "vad" / "silero_vad.onnx").is_file():
            raise RuntimeError("The speech models folder must contain vad\\silero_vad.onnx.")
        return root
    local = Path(__file__).resolve().parents[1] / "models"
    if (local / "vad" / "silero_vad.onnx").is_file():
        return local
    sibling = local.parent.parent / "streaming-transcribe-translate" / "models"
    if (sibling / "vad" / "silero_vad.onnx").is_file():
        return sibling
    raise RuntimeError(
        "Speech models are missing. Copy the asr and vad folders from "
        "streaming-transcribe-translate\\models into this project's models folder."
    )


@dataclass(frozen=True)
class Recognition:
    text: str
    language: str


class SpeechEngine:
    """Local ReazonSpeech / Whisper recognition with streaming Silero ONNX VAD."""

    def __init__(self, model_size: str, options: CaptionOptions | None = None):
        self.options = options or CaptionOptions()
        self.options.validate()
        if model_size not in MODEL_SIZES:
            raise ValueError(f"Unsupported speech model: {model_size}")
        root = models_root(self.options.models_path)
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError("Streaming transcription requires sherpa-onnx. Install requirements.txt.") from exc
        self.whisper = None
        self.recognizer = None
        threads = max(1, min(4, (os.cpu_count() or 2) // 2))
        if model_size == "reazon":
            asr = root / "asr"
            for name in ("encoder.int8.onnx", "decoder.onnx", "joiner.int8.onnx", "tokens.txt"):
                if not (asr / name).is_file():
                    raise RuntimeError(f"Missing ReazonSpeech model file: {asr / name}")
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(asr / "encoder.int8.onnx"), decoder=str(asr / "decoder.onnx"),
                joiner=str(asr / "joiner.int8.onnx"), tokens=str(asr / "tokens.txt"),
                num_threads=threads, sample_rate=SAMPLE_RATE, feature_dim=80,
                decoding_method="greedy_search",
            )
        else:
            local_whisper = root / f"whisper-{model_size}"
            model = str(local_whisper) if (local_whisper / "model.bin").is_file() else model_size
            self.whisper = transcription._load_model(model_size) if model == model_size else self.load_whisper(model)
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(root / "vad" / "silero_vad.onnx")
        config.silero_vad.threshold = 0.5
        config.silero_vad.min_silence_duration = 0.4
        config.silero_vad.min_speech_duration = 0.4
        config.silero_vad.max_speech_duration = 7.0
        config.sample_rate = SAMPLE_RATE
        config.num_threads = threads
        self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)

    @staticmethod
    def load_whisper(path):
        from faster_whisper import WhisperModel
        return WhisperModel(path, device="cpu", compute_type="int8")

    def recognize(self, samples) -> Recognition:
        import numpy as np
        audio = np.asarray(samples, dtype=np.float32)
        if self.recognizer is not None:
            stream = self.recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, audio)
            self.recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            # ReazonSpeech's supplied model supports Japanese and English, without a language field.
            language = "ja" if any("\u3000" <= char <= "\u9fff" for char in text) else "en"
            return Recognition(text, language)
        segments, info = self.whisper.transcribe(
            audio, beam_size=1, condition_on_previous_text=False,
            language=self.options.source_language or None,
        )
        return Recognition(" ".join(part.text.strip() for part in segments if part.text.strip()),
                           info.language)

    def feed(self, samples, *, final=False):
        self.vad.accept_waveform(samples)
        if final:
            self.vad.flush()
        segments = []
        while not self.vad.empty():
            segment = self.vad.front
            segments.append((segment.start / SAMPLE_RATE, list(segment.samples)))
            self.vad.pop()
        return segments


class StreamingTranscriber(transcription.LiveTranscriber):
    """Stream PCM into VAD while recognition / translation consume completed utterances."""

    def __init__(self, platform, source_id, source_resolver, target_language,
                 model_size="reazon", translation_enabled=True, ffmpeg_path=None,
                 options: CaptionOptions | None = None, translation_function=None):
        self.options = options or CaptionOptions()
        self.options.validate()
        if model_size == "reazon" and self.options.source_language in ("zh", "ko"):
            raise ValueError("Select a Whisper model for Chinese or Korean speech.")
        if model_size not in MODEL_SIZES:
            raise ValueError(f"Unsupported speech model: {model_size}")
        if target_language not in ("en", "zh-CN", "zh-TW", "ja", "ko"):
            raise ValueError("Invalid transcription translation target.")
        super().__init__(platform, source_id, source_resolver, target_language,
                         "base", translation_enabled, ffmpeg_path)
        self.model_size = model_size
        self._translation_context = []
        self._translation_function = translation_function

    def _recognize_segment(self, engine, start, samples):
        recognized = engine.recognize(samples)
        if not recognized.text:
            return
        result = {
            "time": datetime.now().astimezone().strftime("%H:%M:%S"),
            "start_seconds": start, "original": recognized.text, "translated": "",
            "translation_error": "", "detected_language": recognized.language,
        }
        with self._lock:
            enabled, target = self.translation_enabled, self.target_language
        if enabled and transcription.language_differs_from_target(recognized.language, target):
            try:
                from src import translate
                if self._translation_function is not None:
                    translated, _ = self._translation_function(
                        recognized.text, target, context=tuple(self._translation_context))
                elif self.options.provider == "openai_compatible":
                    from src import openai_compatible_translate
                    translated, _ = openai_compatible_translate.translate_batch(
                        [recognized.text], target, api_base=self.options.api_base,
                        api_key=self.options.api_key, model=self.options.api_model,
                        background=self.options.background, glossary=self.options.glossary,
                        context=tuple(self._translation_context),
                    )[0]
                else:
                    translated, _ = translate.translate(recognized.text, target)
                if not translated:
                    raise RuntimeError("The translation service returned an empty result.")
                result["translated"] = translated
            except Exception as exc:
                if self.options.provider == "openai_compatible":
                    # Provider errors can echo request headers or credentials.
                    result["translation_error"] = "Translation API request failed. Check the URL, model ID and API key."
                    log.error("Transcription API translation failed (%s).", type(exc).__name__)
                else:
                    result["translation_error"] = str(exc)
                    log.exception("Streaming transcription translation failed.")
        if self.options.context_sentences:
            self._translation_context.append(recognized.text)
            self._translation_context = self._translation_context[-self.options.context_sentences:]
        self._append_segment(result)

    def _run(self):
        process, reader = None, None
        chunks = queue.Queue(maxsize=32)
        reader_done = threading.Event()
        failures = []
        try:
            source = self._source_resolver()
            if not isinstance(source, (str, dict)):
                raise RuntimeError("The audio stream resolver returned an invalid source.")
            url = source if isinstance(source, str) else source.get("url", "")
            headers = (source.get("headers") or {}) if isinstance(source, dict) else {}
            if not url or not isinstance(headers, dict):
                raise RuntimeError("The audio stream resolver returned an invalid source.")
            if self._stop_event.is_set():
                self._set_status("stopped")
                return
            self._set_status("loading_model")
            engine = SpeechEngine(self.model_size, self.options)
            if self._stop_event.is_set():
                self._set_status("stopped")
                return
            self._set_status("connecting")
            command = [self._ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error",
                       "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
            if headers:
                command += ["-headers", "".join(f"{key}: {value}\r\n" for key, value in headers.items())]
            command += ["-i", url, "-vn", "-ar", str(SAMPLE_RATE), "-ac", "1",
                        "-acodec", "pcm_s16le", "-f", "s16le", "pipe:1"]
            with tempfile.TemporaryFile() as error_log:
                process = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=error_log, creationflags=0x08000000 if os.name == "nt" else 0,
                )
                with self._process_lock:
                    self._process = process
                    if self._stop_event.is_set() and process.poll() is None:
                        process.terminate()
                self._set_status("listening")

                def capture():
                    pending = b""
                    try:
                        import numpy as np
                        while not self._stop_event.is_set():
                            data = process.stdout.read(FRAME_SIZE * 2 - len(pending))
                            if not data:
                                break
                            pending += data
                            if len(pending) < FRAME_SIZE * 2:
                                continue
                            samples = np.frombuffer(pending, dtype="<i2").astype(np.float32) / 32768
                            pending = b""
                            for segment in engine.feed(samples):
                                chunks.put_nowait(segment)
                        if not self._stop_event.is_set():
                            if len(pending) % 2:
                                raise RuntimeError("FFmpeg returned incomplete PCM audio.")
                            final = np.zeros(FRAME_SIZE, dtype=np.float32)
                            if pending:
                                tail = np.frombuffer(pending, dtype="<i2").astype(np.float32) / 32768
                                final[:len(tail)] = tail
                            for segment in engine.feed(final, final=True):
                                chunks.put_nowait(segment)
                    except queue.Full:
                        failures.append(RuntimeError(
                            "Transcription cannot keep up with live audio; the utterance queue is full."))
                    except Exception as exc:
                        failures.append(exc)
                    finally:
                        reader_done.set()

                reader = threading.Thread(target=capture, name="html-transcription-audio", daemon=True)
                reader.start()
                while not self._stop_event.is_set():
                    if failures:
                        raise failures[0]
                    try:
                        start, samples = chunks.get(timeout=0.1)
                    except queue.Empty:
                        if reader_done.is_set():
                            break
                        continue
                    self._recognize_segment(engine, start, samples)
                if failures and not self._stop_event.is_set():
                    raise failures[0]
                if self._stop_event.is_set() and process.poll() is None:
                    process.terminate()
                try:
                    code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    code = process.wait(timeout=5)
                    if not self._stop_event.is_set():
                        raise RuntimeError("FFmpeg did not finish reading the audio stream.") from None
                if code and not self._stop_event.is_set():
                    raise RuntimeError("FFmpeg could not read the live audio stream. Confirm the room is live.")
            self._set_status("stopped" if self._stop_event.is_set() else "ended")
        except Exception as exc:
            log.exception("Streaming transcription failed for %s.", self.platform)
            self._set_status("stopped" if self._stop_event.is_set() else "failed",
                             "" if self._stop_event.is_set() else str(exc))
        finally:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if reader:
                reader.join(timeout=3)
            if process and process.stdout:
                process.stdout.close()
            with self._process_lock:
                self._process = None
