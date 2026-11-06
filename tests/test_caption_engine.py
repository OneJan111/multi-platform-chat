import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from src import caption_engine as engine


class CaptionEngineTests(unittest.TestCase):
    def session(self, **kwargs):
        return engine.StreamingTranscriber(
            "bilibili", "123", lambda: {
                "url": "https://example.test/live.flv", "headers": {"User-Agent": "test-agent"},
            }, "zh-CN", ffmpeg_path="ffmpeg", **kwargs,
        )

    def test_recognition_translation_and_source_time(self):
        session = self.session()
        recognizer = Mock()
        recognizer.recognize.return_value = engine.Recognition("hello", "en")
        with patch("src.translate.translate", return_value=("你好", "en")) as translate:
            session._recognize_segment(recognizer, 1.25, [0.1] * 512)
        translate.assert_called_once_with("hello", "zh-CN")
        result = session.snapshot()["segments"][0]
        self.assertEqual((result["original"], result["translated"], result["start_seconds"]),
                         ("hello", "你好", 1.25))
        self.assertEqual(result["detected_language"], "en")

    def test_same_language_disabled_translation_and_empty_speech(self):
        session = self.session()
        recognizer = Mock()
        with patch("src.translate.translate") as translate:
            recognizer.recognize.return_value = engine.Recognition("你好", "zh")
            session._recognize_segment(recognizer, 0, [])
            session.configure_translation(False, "ja")
            session._recognize_segment(recognizer, 1, [])
            recognizer.recognize.return_value = engine.Recognition("", "en")
            session._recognize_segment(recognizer, 2, [])
        translate.assert_not_called()
        self.assertEqual(len(session.snapshot()["segments"]), 2)

    def test_translation_errors_remain_visible_with_original_text(self):
        session = self.session()
        recognizer = Mock()
        recognizer.recognize.return_value = engine.Recognition("hello", "en")
        with patch("src.translate.translate", side_effect=RuntimeError("service unavailable")):
            session._recognize_segment(recognizer, 0, [])
        result = session.snapshot()["segments"][0]
        self.assertEqual(result["original"], "hello")
        self.assertEqual(result["translation_error"], "service unavailable")

    def test_pcm_stream_is_segmented_and_tail_is_flushed(self):
        frames = []
        commands = []

        class FakeEngine:
            def __init__(self, model, options=None):
                self.model = model

            def feed(self, samples, final=False):
                frames.append((samples, final))
                return [(1.25, [0.25] * 600)] if final else []

            def recognize(self, samples):
                return engine.Recognition("hello from stream", "en")

        class FakeProcess:
            def __init__(self, command, **kwargs):
                commands.append(command)
                self.stdout = io.BytesIO(np.zeros(1150, dtype="<i2").tobytes())

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        session = self.session()
        with patch.object(engine, "SpeechEngine", FakeEngine), \
             patch.object(engine.subprocess, "Popen", FakeProcess), \
             patch("src.translate.translate", return_value=("你好", "en")):
            session.start()
            session._thread.join(3)
        self.assertFalse(session._thread.is_alive())
        self.assertEqual(session.snapshot()["status"], "ended")
        self.assertEqual(session.snapshot()["segments"][0]["translated"], "你好")
        self.assertEqual([len(samples) for samples, _ in frames], [512, 512, 512])
        self.assertEqual([final for _, final in frames], [False, False, True])
        self.assertIn("User-Agent: test-agent\r\n", commands[0])
        self.assertEqual(commands[0][-3:], ["-f", "s16le", "pipe:1"])
        self.assertIsNone(session._process)

    def test_missing_model_and_bad_source_fail_explicitly(self):
        session = self.session()
        with patch.object(engine, "SpeechEngine", side_effect=RuntimeError("models missing")):
            session.start()
            session._thread.join(3)
        self.assertEqual(session.snapshot()["status"], "failed")
        self.assertIn("models missing", session.snapshot()["error"])
        session = self.session()
        session._source_resolver = lambda: None
        session._run()
        self.assertIn("invalid source", session.snapshot()["error"])

    def test_model_selection_and_target_are_validated(self):
        with self.assertRaisesRegex(ValueError, "Unsupported speech model"):
            self.session(model_size="invalid")
        with self.assertRaisesRegex(ValueError, "translation target"):
            engine.StreamingTranscriber("bilibili", "123", lambda: "", "invalid")

    def test_vad_backlog_overflow_fails_instead_of_dropping_speech(self):
        class FakeEngine:
            def __init__(self, model, options=None):
                pass

            def feed(self, samples, final=False):
                return [(0, [0.1])] * 10000

            def recognize(self, samples):
                return engine.Recognition("", "en")

        process = Mock()
        process.stdout = io.BytesIO(bytes(1024))
        process.poll.return_value = 0
        process.wait.return_value = 0
        session = self.session()
        with patch.object(engine, "SpeechEngine", FakeEngine), \
             patch.object(engine.subprocess, "Popen", return_value=process):
            session.start()
            session._thread.join(3)
        self.assertEqual(session.snapshot()["status"], "failed")
        self.assertIn("queue is full", session.snapshot()["error"])

    def test_model_search_uses_local_folder_without_source_imports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "models" / "vad").mkdir(parents=True)
            (root / "models" / "vad" / "silero_vad.onnx").write_bytes(b"model")
            with patch.object(engine, "__file__", str(root / "src" / "caption_engine.py")):
                self.assertEqual(engine.models_root(), root / "models")

    def test_api_translation_uses_session_options_and_bounded_context(self):
        options = engine.CaptionOptions(
            provider="openai_compatible", api_base="http://localhost:1234/v1",
            api_model="my-model", api_key="fixture-key", background="Game stream",
            glossary="HP: health", context_sentences=1,
        )
        session = self.session(options=options)
        recognizer = Mock()
        recognizer.recognize.return_value = engine.Recognition("hello", "en")
        with patch("src.openai_compatible_translate.translate_batch", return_value=[("你好", "")]) as api, \
             patch("src.translate.translate") as dashboard_translate:
            session._recognize_segment(recognizer, 0, [])
            session._recognize_segment(recognizer, 1, [])
        dashboard_translate.assert_not_called()
        self.assertEqual(api.call_args_list[0].kwargs["context"], ())
        self.assertEqual(api.call_args.kwargs, {
            "api_base": options.api_base, "api_key": "fixture-key", "model": "my-model",
            "background": "Game stream", "glossary": "HP: health", "context": ("hello",),
        })
        self.assertEqual(session.snapshot()["segments"][-1]["translated"], "你好")
        self.assertNotIn("fixture-key", str(session.snapshot()))

    def test_api_failure_cannot_echo_key_into_transcript_or_logs(self):
        session = self.session(options=engine.CaptionOptions(provider="openai_compatible", api_key="fixture-key"))
        recognizer = Mock()
        recognizer.recognize.return_value = engine.Recognition("hello", "en")
        with patch("src.openai_compatible_translate.translate_batch", side_effect=ValueError("fixture-key")), \
             self.assertLogs(engine.log, level="ERROR") as logs:
            session._recognize_segment(recognizer, 0, [])
        self.assertNotIn("fixture-key", str(session.snapshot()) + str(logs.output))
        self.assertIn("API request failed", session.snapshot()["segments"][0]["translation_error"])

    def test_source_language_is_passed_to_whisper(self):
        recognizer = engine.SpeechEngine.__new__(engine.SpeechEngine)
        recognizer.options = engine.CaptionOptions(source_language="zh")
        recognizer.recognizer = None
        recognizer.whisper = Mock()
        recognizer.whisper.transcribe.return_value = ([Mock(text="你好")], Mock(language="zh"))
        result = recognizer.recognize([0.1])
        self.assertEqual(result.text, "你好")
        self.assertEqual(recognizer.whisper.transcribe.call_args.kwargs["language"], "zh")

    def test_invalid_engine_options_fail_before_model_loading(self):
        for options in (engine.CaptionOptions(source_language="invalid"),
                        engine.CaptionOptions(context_sentences=9),
                        engine.CaptionOptions(models_path="relative"),
                        engine.CaptionOptions(api_base="https://example.test?key=hidden"),
                        engine.CaptionOptions(api_model="has spaces")):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.session(options=options)
        with self.assertRaisesRegex(ValueError, "Whisper"):
            self.session(options=engine.CaptionOptions(source_language="zh"))


if __name__ == "__main__":
    unittest.main()
