import os
import runpy
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import desktop_app
from src import tts


class TtsQueueConfigTests(unittest.TestCase):
    def test_defaults_custom_values_and_invalid_limits(self):
        names = {
            "TTS_QUEUE_LIMIT": 20,
            "TTS_PRIORITY_QUEUE_LIMIT": 50,
            "TTS_TASK_LIMIT": 20,
            "TTS_AUDIO_QUEUE_LIMIT": 20,
        }
        path = Path(__file__).resolve().parents[1] / "src" / "config.py"
        for name, default in names.items():
            for value in (None, "2", "0", "-1", "invalid"):
                with self.subTest(name=name, value=value):
                    env = {} if value is None else {name: value}
                    with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
                        if value in ("0", "-1", "invalid"):
                            with self.assertRaises(ValueError):
                                runpy.run_path(str(path))
                        else:
                            config = runpy.run_path(str(path))
                            self.assertEqual(config[name], default if value is None else 2)

    def test_offline_lanes_drop_oldest_at_configured_limits(self):
        import collections

        worker = Mock()
        worker.is_alive.return_value = True
        with patch.object(tts, "_worker", worker), \
                patch.object(tts, "_normal_q", collections.deque()), \
                patch.object(tts, "_priority_q", collections.deque()), \
                patch.object(tts, "_MAX_QUEUE", 2), \
                patch.object(tts, "_MAX_PRIORITY_QUEUE", 1):
            with self.assertLogs("src.tts", level="WARNING"):
                for text in ("one", "two", "three"):
                    tts._enqueue(text, 150, 1.0, "en")
                    tts._enqueue(text, 150, 1.0, "en", priority=True)
            self.assertEqual([item[0] for item in tts._normal_q], ["two", "three"])
            self.assertEqual([item[0] for item in tts._priority_q], ["three"])


@unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
class DesktopTtsQueueLimitTests(unittest.TestCase):
    def test_pending_tasks_are_bounded_and_slots_release_on_completion(self):
        window = SimpleNamespace(
            _tts_task_slots=threading.BoundedSemaphore(1),
            _run_task=Mock(),
            statusBar=Mock(return_value=Mock()),
            _task_bridges=[],
        )
        window._tts_task_finished = lambda: (
            desktop_app._DesktopWindow._tts_task_finished(window)
        )
        function, callback = Mock(), Mock()
        desktop_app._DesktopWindow._run_tts_task(window, function, callback)
        desktop_app._DesktopWindow._run_tts_task(window, function, callback)
        self.assertEqual(window._run_task.call_count, 1)
        window.statusBar().showMessage.assert_called_once()
        release = window._run_task.call_args.kwargs["on_finished"]
        desktop_app._DesktopWindow._task_finished(
            window, Mock(), b"audio", None, callback, release
        )
        callback.assert_called_once_with(b"audio")
        desktop_app._DesktopWindow._run_tts_task(window, function, callback)
        self.assertEqual(window._run_task.call_count, 2)

    def test_failed_synthesis_releases_slot(self):
        slots = threading.BoundedSemaphore(1)
        slots.acquire()
        window = SimpleNamespace(_task_bridges=[], _show_error=Mock())
        desktop_app._DesktopWindow._task_finished(
            window, Mock(), None, ValueError("failed"), None, slots.release
        )
        self.assertTrue(slots.acquire(blocking=False))
        window._show_error.assert_called_once()

    def test_audio_buffer_drops_oldest_at_limit(self):
        window = SimpleNamespace(
            _audio_queue=[b"old", b"recent"],
            config=SimpleNamespace(TTS_AUDIO_QUEUE_LIMIT=2),
            _audio_player=Mock(),
            statusBar=Mock(return_value=Mock()),
        )
        desktop_app._DesktopWindow._play_audio_bytes(window, b"new")
        self.assertEqual(window._audio_queue, [b"recent", b"new"])
        window.statusBar().showMessage.assert_called_once()
