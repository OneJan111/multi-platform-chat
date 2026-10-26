import sys
import tempfile
import time
import types
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import desktop_app
from src import youtube_recorder


class _YoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def extract_info(self, url, download):
        self.url = url
        self.download = download
        return self.info


class YouTubeSourceTests(unittest.TestCase):
    def test_record_toggle_persists_enabled_state(self):
        settings = Mock()
        settings.status.return_value = (
            desktop_app.QtCore.QSettings.Status.NoError
        )
        window = SimpleNamespace(
            _monitor_targets=[{
                "id": "youtube:channel",
                "platform": "youtube",
                "target": "https://youtube.com/@channel",
            }],
            _record_enabled_ids=set(),
            _settings=settings,
            _live_states={},
            _stop_recording=Mock(),
            _show_error=Mock(),
        )
        window._save_record_enabled_ids = lambda: (
            desktop_app._DesktopWindow._save_record_enabled_ids(window)
        )

        desktop_app._DesktopWindow._set_recording(
            window, "youtube:channel", True
        )
        self.assertIn("youtube:channel", window._record_enabled_ids)
        settings.setValue.assert_called_with(
            "record_enabled_ids", ["youtube:channel"]
        )
        settings.sync.assert_called_once_with()

        settings.reset_mock()
        desktop_app._DesktopWindow._set_recording(
            window, "youtube:channel", False
        )
        self.assertNotIn("youtube:channel", window._record_enabled_ids)
        settings.setValue.assert_called_once_with("record_enabled_ids", [])
        settings.sync.assert_called_once_with()

    def test_resolves_muxed_stream_and_headers(self):
        class YoutubeDL(_YoutubeDL):
            info = {
                "url": "https://stream.example/live",
                "acodec": "opus",
                "vcodec": "av01",
                "http_headers": {"User-Agent": "test"},
            }

        with patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=YoutubeDL)}):
            source = youtube_recorder.resolve_live_source("video123")

        self.assertEqual(
            source["sources"],
            [{
                "url": "https://stream.example/live",
                "headers": {"User-Agent": "test"},
            }],
        )

    def test_resolves_separate_live_audio_and_video_formats(self):
        video = {"url": "https://stream.example/video", "vcodec": "av01", "acodec": "none"}
        audio = {"url": "https://stream.example/audio", "vcodec": "none", "acodec": "opus"}

        class YoutubeDL(_YoutubeDL):
            info = {"requested_formats": [video, audio]}

        with patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=YoutubeDL)}):
            source = youtube_recorder.resolve_live_source("video123")

        self.assertEqual(
            [item["url"] for item in source["sources"]],
            ["https://stream.example/video", "https://stream.example/audio"],
        )

    def test_recording_path_sanitizes_stream_metadata(self):
        path = youtube_recorder.recording_path(
            "root",
            "video123",
            "Channel/Name",
            'Live: "title"',
            datetime(2026, 1, 2, 3, 4, 5, 678000),
        )

        self.assertEqual(
            path,
            Path("root")
            / "video123-Channel_Name"
            / "录制-video123-20260102-030405-678-Live_ _title_.mkv",
        )


class YouTubeRecorderTests(unittest.TestCase):
    def test_missing_ffmpeg_is_reported(self):
        recorder = youtube_recorder.YouTubeRecorder(
            "video123",
            "recordings",
            lambda: {"sources": [{"url": "https://stream.example/live"}]},
            ffmpeg_path="",
        )
        recorder._ffmpeg_path = None

        with self.assertRaisesRegex(RuntimeError, "FFmpeg was not found"):
            recorder.start()

    def test_stop_terminates_ffmpeg_and_tracks_output(self):
        processes = []

        class FakeProcess:
            def __init__(self, command, **_kwargs):
                self.command = command
                self.returncode = None
                self.output = Path(command[-1])
                self.output.parent.mkdir(parents=True, exist_ok=True)
                self.output.write_bytes(b"video")
                processes.append(self)

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 0

            def wait(self, timeout=None):
                return self.returncode

        with tempfile.TemporaryDirectory() as folder, patch(
            "src.youtube_recorder.subprocess.Popen", FakeProcess
        ):
            recorder = youtube_recorder.YouTubeRecorder(
                "video123",
                folder,
                lambda: {
                    "sources": [{
                        "url": "https://stream.example/live",
                        "headers": {"User-Agent": "test"},
                    }],
                },
                ffmpeg_path="ffmpeg",
            )
            recorder.start()
            deadline = time.time() + 5
            while not processes and time.time() < deadline:
                time.sleep(0.01)
            self.assertTrue(processes)
            recorder.stop(wait=5)

            state = recorder.snapshot()
            self.assertEqual(state["status"], "Stopped")
            self.assertEqual(state["total_bytes"], 5)
            self.assertEqual(len(state["files"]), 1)
            self.assertIn("User-Agent: test\r\n", processes[0].command)
            self.assertIn("-map", processes[0].command)
            self.assertIn("0", processes[0].command)
            self.assertIn("copy", processes[0].command)
            self.assertIn("matroska", processes[0].command)


@unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
class YouTubeRecordingIntegrationTests(unittest.TestCase):
    def test_selected_live_youtube_room_creates_and_starts_recorder(self):
        target = {
            "id": "youtube:channel",
            "platform": "youtube",
            "target": "https://youtube.com/@channel",
            "enabled": True,
        }
        window = SimpleNamespace(
            _monitor_targets=[target],
            _recorders={},
            _worker=SimpleNamespace(
                _youtube={"youtube:channel": {"video_id": "livevideo01"}}
            ),
            record_folder=SimpleNamespace(text=lambda: "recordings"),
            _room_names={"youtube:channel": "Channel"},
            _room_titles={"youtube:channel": "Live"},
            _record_enabled_ids=set(),
            _refresh_recording_status=lambda: None,
            _show_error=lambda message: self.fail(message),
            _refresh_monitor_cards=lambda: None,
        )
        with patch(
            "src.youtube_recorder.YouTubeRecorder"
        ) as recorder_factory:
            instance = recorder_factory.return_value
            desktop_app._DesktopWindow._start_recording(window, "youtube:channel")

        recorder_factory.assert_called_once()
        self.assertEqual(recorder_factory.call_args.args[:2], ("livevideo01", "recordings"))
        instance.start.assert_called_once_with()
        self.assertIn("youtube:channel", window._record_enabled_ids)


if __name__ == "__main__":
    unittest.main()
