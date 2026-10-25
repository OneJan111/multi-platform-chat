import unittest
import tracemalloc
import os
import runpy
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import desktop_app
from desktop_app import _memory_collection_metrics, _memory_process_metrics


class _FakePsutil:
    class Error(Exception):
        pass


class DesktopMemoryMonitorTests(unittest.TestCase):
    def test_allocation_trace_config_defaults_off_and_accepts_true(self):
        path = Path(desktop_app.__file__).parent / "src" / "config.py"
        for value, expected in ((None, False), ("true", True), ("false", False)):
            env = {} if value is None else {"MEMORY_TRACE_ENABLED": value}
            with self.subTest(value=value), \
                    patch.dict(os.environ, env, clear=True), \
                    patch("dotenv.load_dotenv"):
                self.assertEqual(
                    runpy.run_path(str(path))["MEMORY_TRACE_ENABLED"], expected
                )

    def test_allocation_trace_reports_growth_and_throttles_snapshots(self):
        trace = desktop_app._MemoryAllocationTrace()
        try:
            baseline = trace.sample(0)
            self.assertTrue(baseline["baseline"])
            self.assertIsNone(trace.sample(59))
            allocations = [bytearray(128 * 1024) for _ in range(10)]
            metrics = trace.metrics()
            self.assertGreaterEqual(
                metrics["python_traced_current_bytes"], 128 * 1024 * 10
            )
            result = trace.sample(60)
            self.assertFalse(result["baseline"])
            self.assertEqual(result["interval_seconds"], 60)
            self.assertLessEqual(len(result["top_growth"]), 10)
            self.assertTrue(any(
                item["file"] == __file__
                and item["size_delta_bytes"] >= 128 * 1024 * 10
                for item in result["top_growth"]
            ))
            self.assertEqual(len(allocations), 10)
        finally:
            trace.close()

    def test_allocation_trace_does_not_stop_existing_tracer(self):
        already_tracing = tracemalloc.is_tracing()
        if not already_tracing:
            tracemalloc.start(1)
        try:
            trace = desktop_app._MemoryAllocationTrace()
            trace.close()
            self.assertTrue(tracemalloc.is_tracing())
        finally:
            if not already_tracing:
                tracemalloc.stop()

    def test_collection_metrics_report_retained_items_and_bytes(self):
        window = SimpleNamespace(
            _messages=[{}, {}],
            _paid=[{}],
            _joins=[],
            _activity=[1, 2, 3],
            _hotspot_events=[1],
            _chat_image_cache={
                "image": ("image/png", b"1234"),
                "invalid": None,
            },
            _chat_images_pending={"next"},
            _audio_queue=[b"123", b"45"],
            _task_bridges=[object(), object()],
            _bilibili_avatar_cache={"42": "url"},
            _bilibili_avatars_pending={"43"},
            _memory_work_counters={"feed_rows_reused_total": 100},
            _transcription_sessions=[],
            _segments=[{}, {}],
            _monitor_targets=[{}, {}],
            _worker=SimpleNamespace(_listeners={"room": object()}),
            _recorders={
                "running": SimpleNamespace(is_running=True),
                "stopped": SimpleNamespace(is_running=False),
            },
        )

        metrics = _memory_collection_metrics(window)

        self.assertEqual(metrics["chat_messages"], 2)
        self.assertEqual(metrics["paid_messages"], 1)
        self.assertEqual(metrics["activity_entries"], 3)
        self.assertEqual(metrics["chat_image_cache_bytes"], 4)
        self.assertEqual(metrics["tts_queue_bytes"], 5)
        self.assertEqual(metrics["transcription_display_segments"], 2)
        self.assertEqual(metrics["chat_listener_count"], 1)
        self.assertEqual(metrics["recording_count"], 1)
        self.assertEqual(metrics["task_callbacks_pending"], 2)
        self.assertEqual(metrics["bilibili_avatar_cache_entries"], 1)
        self.assertEqual(metrics["bilibili_avatars_pending"], 1)
        self.assertEqual(metrics["feed_rows_reused_total"], 100)
        self.assertIn("tts_offline_normal_pending", metrics)

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_qt_metrics_include_parent_owned_bridges_not_in_pending_list(self):
        app = (
            desktop_app.QtWidgets.QApplication.instance()
            or desktop_app.QtWidgets.QApplication([])
        )
        window = desktop_app.QtWidgets.QWidget()
        bridge = desktop_app._TaskBridge(window)
        window._task_bridges = []
        try:
            metrics = _memory_collection_metrics(window)
            self.assertEqual(metrics["task_callbacks_pending"], 0)
            self.assertEqual(metrics["qt_task_bridges_alive"], 1)
            self.assertGreaterEqual(metrics["qt_widgets_total"], 1)
        finally:
            bridge.deleteLater()
            window.deleteLater()
            app.processEvents()

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_completed_tasks_delete_bridges_for_success_and_failure(self):
        app = (
            desktop_app.QtWidgets.QApplication.instance()
            or desktop_app.QtWidgets.QApplication([])
        )
        window = desktop_app.QtWidgets.QWidget()
        window._task_bridges = []
        window._executor = Mock()
        window._show_error = Mock()
        window._task_finished = lambda *args: (
            desktop_app._DesktopWindow._task_finished(window, *args)
        )
        callback = Mock()
        finished = Mock()
        try:
            for index in range(100):
                future = Future()
                if index % 2:
                    future.set_exception(ValueError("test failure"))
                else:
                    future.set_result(b"test audio")
                window._executor.submit.return_value = future
                desktop_app._DesktopWindow._run_task(
                    window, lambda: None, callback, on_finished=finished
                )
            app.processEvents()
            desktop_app.QtCore.QCoreApplication.sendPostedEvents(
                None, desktop_app.QtCore.QEvent.Type.DeferredDelete
            )
            self.assertEqual(window._task_bridges, [])
            self.assertEqual(window.findChildren(desktop_app._TaskBridge), [])
            self.assertEqual(callback.call_count, 50)
            self.assertEqual(window._show_error.call_count, 50)
            self.assertEqual(finished.call_count, 100)
        finally:
            window.deleteLater()
            app.processEvents()

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_bridge_is_deleted_even_if_callback_raises(self):
        app = (
            desktop_app.QtWidgets.QApplication.instance()
            or desktop_app.QtWidgets.QApplication([])
        )
        window = desktop_app.QtWidgets.QWidget()
        bridge = desktop_app._TaskBridge(window)
        window._task_bridges = [bridge]
        try:
            with self.assertRaisesRegex(ValueError, "callback failed"):
                desktop_app._DesktopWindow._task_finished(
                    window, bridge, None, None,
                    Mock(side_effect=ValueError("callback failed")),
                )
            desktop_app.QtCore.QCoreApplication.sendPostedEvents(
                None, desktop_app.QtCore.QEvent.Type.DeferredDelete
            )
            self.assertEqual(window._task_bridges, [])
            self.assertEqual(window.findChildren(desktop_app._TaskBridge), [])
        finally:
            window.deleteLater()
            app.processEvents()

    def test_process_metrics_include_children_and_report_unreadable_child(self):
        class Process:
            def memory_info(self):
                return SimpleNamespace(rss=100)

            def children(self, recursive=True):
                return [ReadableChild(), UnreadableChild()]

            def num_threads(self):
                return 4

        class ReadableChild:
            def memory_info(self):
                return SimpleNamespace(rss=50)

        class UnreadableChild:
            def memory_info(self):
                raise _FakePsutil.Error("process exited")

        metrics = _memory_process_metrics(Process(), _FakePsutil)

        self.assertEqual(metrics["process_tree_rss_bytes"], 150)
        self.assertEqual(metrics["child_process_count"], 2)
        self.assertEqual(metrics["unreadable_child_processes"], 1)
        self.assertEqual(metrics["thread_count"], 4)


if __name__ == "__main__":
    unittest.main()
