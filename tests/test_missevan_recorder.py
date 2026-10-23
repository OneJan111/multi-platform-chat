import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.missevan_recorder import MissEvanRecorder, recording_path


class MissEvanRecordingPathTests(unittest.TestCase):
    def test_recording_path_sanitizes_names_and_uses_mkv(self):
        path = recording_path(
            "root", "123", "主播", 'Hi: a/b?*"', datetime(2026, 1, 2, 3, 4, 5, 678000)
        )
        self.assertEqual(
            path,
            Path("root") / "123-主播" / "录制-123-20260102-030405-678-Hi_ a_b___.mkv",
        )


class MissEvanRecorderTests(unittest.TestCase):
    def test_records_stream_then_stops_when_room_goes_offline(self):
        urls = iter(["https://cdn.example.test/live.m3u8"])

        def resolve_url():
            try:
                return next(urls)
            except StopIteration:
                raise RuntimeError("The MissEvan room is not live.")

        class FinishedProcess:
            def __init__(self, command, **_kwargs):
                self.return_code = 0
                Path(command[-1]).write_bytes(b"recorded")
                self.command = command

            def poll(self):
                return self.return_code

            def wait(self, timeout=None):
                return self.return_code

        with tempfile.TemporaryDirectory() as folder, \
                patch("src.missevan_recorder.subprocess.Popen", FinishedProcess):
            recorder = MissEvanRecorder(
                "123",
                folder,
                resolve_url,
                name="Streamer",
                title="Live",
                ffmpeg_path="ffmpeg",
                retry_delay=0,
            )
            recorder.start()
            recorder._thread.join(timeout=3)

            state = recorder.snapshot()
            self.assertEqual(state["status"], "Stream ended")
            self.assertFalse(state["running"])
            self.assertEqual(len(state["files"]), 1)
            self.assertEqual(Path(state["files"][0]).read_bytes(), b"recorded")
            self.assertEqual(state["total_bytes"], len(b"recorded"))
            self.assertEqual(Path(state["file"]).suffix, ".mkv")

    def test_stop_terminates_live_ffmpeg_process(self):
        class RunningProcess:
            def __init__(self, command, **_kwargs):
                self.return_code = None
                Path(command[-1]).write_bytes(b"recording")

            def poll(self):
                return self.return_code

            def terminate(self):
                self.return_code = 0

            def wait(self, timeout=None):
                return self.return_code

        with tempfile.TemporaryDirectory() as folder, \
                patch("src.missevan_recorder.subprocess.Popen", RunningProcess):
            recorder = MissEvanRecorder(
                "123",
                folder,
                lambda: "https://cdn.example.test/live.m3u8",
                ffmpeg_path="ffmpeg",
            )
            recorder.start()
            deadline = time.time() + 3
            while recorder.snapshot()["status"] != "Recording" and time.time() < deadline:
                time.sleep(0.01)

            recorder.stop(wait=3)

            self.assertFalse(recorder.is_running)
            self.assertEqual(recorder.snapshot()["status"], "Stopped")


if __name__ == "__main__":
    unittest.main()
