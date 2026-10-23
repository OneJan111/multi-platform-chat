import unittest
from types import SimpleNamespace

from desktop_app import _memory_collection_metrics, _memory_process_metrics


class _FakePsutil:
    class Error(Exception):
        pass


class DesktopMemoryMonitorTests(unittest.TestCase):
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
