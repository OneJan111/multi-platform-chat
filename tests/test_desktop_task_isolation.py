import concurrent.futures
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

import desktop_app


@unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
class DesktopTaskIsolationTests(unittest.TestCase):
    def setUp(self):
        self.app = (
            desktop_app.QtWidgets.QApplication.instance()
            or desktop_app.QtWidgets.QApplication([])
        )
        self.window = desktop_app.QtWidgets.QWidget()
        for name in ("_executor", "_tts_executor", "_obs_executor", "_archive_executor"):
            setattr(self.window, name, concurrent.futures.ThreadPoolExecutor(max_workers=1))
        self.window._show_error = Mock()
        self.window._task_finished = lambda *args: desktop_app._DesktopWindow._task_finished(
            self.window, *args
        )
        self.window._run_task = lambda *args, **kwargs: desktop_app._DesktopWindow._run_task(
            self.window, *args, **kwargs
        )
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        for name in ("_executor", "_tts_executor", "_obs_executor", "_archive_executor"):
            getattr(self.window, name).shutdown(wait=True)
        self.app.processEvents()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_for(self, condition):
        deadline = time.monotonic() + 2
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(condition())

    def test_blocked_translation_pool_does_not_block_tts_obs_or_archive(self):
        started = threading.Event()

        def blocked():
            started.set()
            self.release.wait(3)

        self.window._executor.submit(blocked)
        self.assertTrue(started.wait(1))
        callbacks = [Mock(), Mock(), Mock()]
        for name, callback in zip(
            ("_tts_executor", "_obs_executor", "_archive_executor"), callbacks
        ):
            self.window._run_task(
                lambda: "done", callback, executor=getattr(self.window, name)
            )
        self.wait_for(lambda: all(callback.called for callback in callbacks))
        self.assertFalse(self.release.is_set())
        self.window._show_error.assert_not_called()

    def test_archive_is_ordered_nonblocking_and_flushes_on_shutdown(self):
        started = threading.Event()
        order = []

        def blocked_write():
            started.set()
            self.release.wait(3)
            order.append("first")
            return {"ok": True}

        desktop_app._DesktopWindow._run_archive_task(self.window, blocked_write)
        self.assertTrue(started.wait(1))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.txt"

            def second_write():
                path.write_text("saved", encoding="utf-8")
                order.append("second")
                return {"ok": True}

            desktop_app._DesktopWindow._run_archive_task(self.window, second_write)
            callback = Mock()
            self.window._run_task(lambda: "tts", callback, executor=self.window._tts_executor)
            self.wait_for(lambda: callback.called)
            self.assertFalse(path.exists())
            self.release.set()
            self.window._archive_executor.shutdown(wait=True)
            self.assertEqual(order, ["first", "second"])
            self.assertEqual(path.read_text(encoding="utf-8"), "saved")

    def test_archive_failure_is_reported_and_next_operation_runs(self):
        callback = Mock()
        with self.assertLogs("desktop_app", level="ERROR"):
            desktop_app._DesktopWindow._run_archive_task(
                self.window, lambda: {"ok": False, "error": "disk full"}
            )
            self.wait_for(lambda: self.window._show_error.called)
        self.window._show_error.assert_called_once_with("RuntimeError: disk full")
        desktop_app._DesktopWindow._run_archive_task(
            self.window, lambda: {"ok": True}, callback
        )
        self.wait_for(lambda: callback.called)

    def test_tts_submissions_use_dedicated_pool_and_release_slots(self):
        self.window._tts_task_slots = threading.BoundedSemaphore(1)
        self.window._tts_task_finished = lambda: desktop_app._DesktopWindow._tts_task_finished(
            self.window
        )
        self.window._executor.submit(lambda: self.release.wait(3))
        callback = Mock()
        desktop_app._DesktopWindow._run_tts_task(
            self.window, lambda: b"audio", callback
        )
        self.wait_for(lambda: callback.called)
        callback.assert_called_once_with(b"audio")
        self.assertTrue(self.window._tts_task_slots.acquire(blocking=False))
        self.assertFalse(self.release.is_set())

    def test_archive_append_captures_room_metadata_before_submission(self):
        self.window._monitor_targets = [{
            "id": "bilibili:123", "platform": "bilibili",
            "target": "123", "enabled": True,
        }]
        self.window._room_names = {"bilibili:123": "Original room"}
        self.window._archive = Mock()
        self.window._archive.append_messages.return_value = {"ok": True}
        self.window._run_archive_task = lambda *args: desktop_app._DesktopWindow._run_archive_task(
            self.window, *args
        )
        started = threading.Event()

        def block_archive():
            started.set()
            self.release.wait(3)

        self.window._archive_executor.submit(block_archive)
        self.assertTrue(started.wait(1))
        messages = [{
            "_monitor_id": "bilibili:123", "platform": "bilibili",
            "timestamp": "123", "author": "viewer", "text": "hello",
        }]
        desktop_app._DesktopWindow._append_messages_to_archive(self.window, messages)
        self.window._room_names["bilibili:123"] = "New room"
        messages[0]["text"] = "changed"
        self.window._archive.append_messages.assert_not_called()
        self.release.set()
        self.window._archive_executor.shutdown(wait=True)
        self.window._archive.append_messages.assert_called_once_with(
            "bilibili:123",
            [{"timestamp": "123", "platform": "bilibili", "author": "viewer", "text": "hello"}],
            platform="bilibili", room_id="123", channel_id="", room_name="Original room",
        )


if __name__ == "__main__":
    unittest.main()
