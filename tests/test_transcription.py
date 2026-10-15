import os
import runpy
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from src import bilibili, missevan, transcription


class TranscriptionConfigTests(unittest.TestCase):
    def test_transcription_is_hidden_by_default_and_requires_true(self):
        config_path = Path(__file__).resolve().parents[1] / "src" / "config.py"
        for value, expected in ((None, False), ("false", False), ("true", True), (" TRUE ", True)):
            with self.subTest(value=value), patch.dict(os.environ, {}, clear=True), \
                    patch("dotenv.load_dotenv"):
                if value is not None:
                    os.environ["TRANSCRIPTION_ENABLED"] = value
                settings = runpy.run_path(str(config_path))
                self.assertEqual(settings["TRANSCRIPTION_ENABLED"], expected)


class TranscriptionSourceTests(unittest.TestCase):
    def test_translation_runs_only_when_detected_language_differs_from_target(self):
        self.assertFalse(transcription.language_differs_from_target("zh", "zh-CN"))
        self.assertFalse(transcription.language_differs_from_target("en-US", "en"))
        self.assertTrue(transcription.language_differs_from_target("en", "ja"))
        self.assertFalse(transcription.language_differs_from_target("", "en"))

    def test_resolve_youtube_audio_url_uses_audio_format(self):
        class FakeYDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self, url, download):
                self.url = url
                self.download = download
                return {
                    "requested_formats": [
                        {"url": "https://example.test/video", "acodec": "none"},
                        {
                            "url": "https://example.test/audio",
                            "acodec": "opus",
                            "http_headers": {"User-Agent": "test-agent"},
                        },
                    ],
                }

        with patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=FakeYDL)}):
            result = transcription.resolve_youtube_audio_source("https://www.youtube.com/watch?v=abc")
        self.assertEqual(result, {
            "url": "https://example.test/audio",
            "headers": {"User-Agent": "test-agent"},
        })

    def test_extract_bilibili_live_stream_url(self):
        info = {
            "live_status": 1,
            "playurl_info": {
                "playurl": {
                    "stream": [{
                        "format": [{
                            "codec": [{
                                "base_url": "/live/room.flv",
                                "url_info": [{
                                    "host": "https://cdn.example.test/",
                                    "extra": "?token=secret",
                                }],
                            }]
                        }]
                    }]
                }
            },
        }
        self.assertEqual(
            transcription.extract_bilibili_audio_url(info),
            "https://cdn.example.test/live/room.flv?token=secret",
        )

    def test_extract_bilibili_rejects_offline_room(self):
        with self.assertRaisesRegex(RuntimeError, "not live"):
            transcription.extract_bilibili_audio_url({"live_status": 0})

    def test_extract_bilibili_legacy_durl_stream_url(self):
        self.assertEqual(
            transcription.extract_bilibili_audio_url(
                {"live_status": 1},
                {"durl": [
                    {"url": "https://cdn.example.test/live.flv?token=first"},
                    {"url": "https://cdn.example.test/live-backup.flv?token=second"},
                ]},
            ),
            "https://cdn.example.test/live.flv?token=first",
        )

    def test_extract_bilibili_rejects_missing_stream_url(self):
        with self.assertRaisesRegex(RuntimeError, "no usable live stream URL"):
            transcription.extract_bilibili_audio_url({"live_status": 1}, {"durl": []})

    def test_bilibili_stream_resolver_uses_captured_user_cookies(self):
        class FakeRoom:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def get_room_play_info(self):
                return "play-info-coroutine"

            def get_room_play_url(self):
                return "play-url-coroutine"

        play_info = {
            "live_status": 1,
        }
        play_url = {"durl": [{"url": "https://cdn.example.test/live/room.flv?token=ok"}]}
        credential = object()
        cookies = {
            "SESSDATA": "session",
            "bili_jct": "csrf",
            "buvid3": "device",
            "DedeUserID": "user",
        }
        with patch.object(bilibili, "live", types.SimpleNamespace(LiveRoom=FakeRoom), create=True), \
                patch.object(bilibili, "BILIBILI_LIB_OK", True), \
                patch.object(bilibili, "_credential", return_value=credential) as make_credential, \
                patch.object(bilibili, "_run", side_effect=[play_info, play_url]) as run:
            result = bilibili.get_live_audio_url("123", cookies)
        make_credential.assert_called_once_with(("session", "csrf", "device", "user"))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result, "https://cdn.example.test/live/room.flv?token=ok")

    def test_missevan_stream_url_requires_live_room(self):
        response = unittest.mock.Mock()
        response.json.return_value = {
            "code": 0,
            "info": {
                "room": {
                    "status": {"open": True},
                    "channel": {"hls_pull_url": "https://cdn.example.test/live.m3u8"},
                }
            },
        }
        with patch("src.missevan.requests.get", return_value=response):
            self.assertEqual(
                missevan.get_live_audio_url("123"),
                "https://cdn.example.test/live.m3u8",
            )

        response.json.return_value["info"]["room"]["status"]["open"] = False
        with patch("src.missevan.requests.get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "not live"):
                missevan.get_live_audio_url("123")


class TranscriptionWorkerTests(unittest.TestCase):
    def test_faster_whisper_decodes_wav_with_supported_pyav(self):
        from faster_whisper.audio import decode_audio

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "silence.wav"
            with wave.open(str(audio_path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(b"\0\0" * 1600)

            audio = decode_audio(str(audio_path))

        self.assertEqual(len(audio), 1600)

    def test_worker_recognizes_and_translates_closed_audio_segments(self):
        class FakeModel:
            def transcribe(self, path, **kwargs):
                self.audio_path = path
                return (
                    [types.SimpleNamespace(text="hello from the stream")],
                    types.SimpleNamespace(language="en"),
                )

        commands = []

        class FakeProcess:
            def __init__(self, command, **kwargs):
                commands.append(command)
                self.return_code = 0
                Path(command[-1].replace("%06d", "000000")).write_bytes(b"wav")

            def poll(self):
                return self.return_code

            def wait(self, timeout=None):
                return self.return_code

        model = FakeModel()
        with patch.object(transcription, "_load_model", return_value=model), \
                patch.object(transcription.subprocess, "Popen", FakeProcess), \
                patch("src.translate.translate", return_value=("你好", "en")) as translate_text:
            session = transcription.LiveTranscriber(
                platform="youtube",
                source_id="video-id",
                source_resolver=lambda: {
                    "url": "https://example.test/live.m3u8",
                    "headers": {"User-Agent": "test-agent"},
                },
                target_language="zh-CN",
                ffmpeg_path="ffmpeg",
            )
            session.start()
            thread = session._thread
            thread.join(timeout=3)

        snapshot = session.snapshot()
        self.assertEqual(snapshot["status"], "ended")
        self.assertEqual(len(snapshot["segments"]), 1)
        self.assertEqual(snapshot["segments"][0]["original"], "hello from the stream")
        self.assertEqual(snapshot["segments"][0]["translated"], "你好")
        self.assertIn("-headers", commands[0])
        self.assertIn("User-Agent: test-agent\r\n", commands[0])
        translate_text.assert_called_once_with("hello from the stream", "zh-CN")

    def test_worker_skips_translation_when_audio_matches_target_language(self):
        class FakeModel:
            def transcribe(self, path, **kwargs):
                return [types.SimpleNamespace(text="你好，欢迎")], types.SimpleNamespace(language="zh")

        class FakeProcess:
            def __init__(self, command, **kwargs):
                self.return_code = 0
                Path(command[-1].replace("%06d", "000000")).write_bytes(b"wav")

            def poll(self):
                return self.return_code

            def wait(self, timeout=None):
                return self.return_code

        with patch.object(transcription, "_load_model", return_value=FakeModel()), \
                patch.object(transcription.subprocess, "Popen", FakeProcess), \
                patch("src.translate.translate") as translate_text:
            session = transcription.LiveTranscriber(
                platform="missevan",
                source_id="room-id",
                source_resolver=lambda: "https://example.test/live.m3u8",
                target_language="zh-CN",
                ffmpeg_path="ffmpeg",
            )
            session.start()
            session._thread.join(timeout=3)

        translate_text.assert_not_called()
        snapshot = session.snapshot()
        self.assertEqual(snapshot["status"], "ended")
        self.assertEqual(snapshot["segments"][0]["original"], "你好，欢迎")
        self.assertEqual(snapshot["segments"][0]["translated"], "")

    def test_worker_skips_translation_until_translation_is_started(self):
        class FakeModel:
            def transcribe(self, path, **kwargs):
                return [types.SimpleNamespace(text="hello")], types.SimpleNamespace(language="en")

        class FakeProcess:
            def __init__(self, command, **kwargs):
                self.return_code = 0
                Path(command[-1].replace("%06d", "000000")).write_bytes(b"wav")

            def poll(self):
                return self.return_code

            def wait(self, timeout=None):
                return self.return_code

        with patch.object(transcription, "_load_model", return_value=FakeModel()), \
                patch.object(transcription.subprocess, "Popen", FakeProcess), \
                patch("src.translate.translate") as translate_text:
            session = transcription.LiveTranscriber(
                platform="youtube",
                source_id="video-id",
                source_resolver=lambda: "https://example.test/live.m3u8",
                target_language="zh-CN",
                translation_enabled=False,
                ffmpeg_path="ffmpeg",
            )
            session.start()
            session._thread.join(timeout=3)

        translate_text.assert_not_called()
        self.assertEqual(session.snapshot()["segments"][0]["translated"], "")

    def test_translation_settings_can_be_updated_during_transcription(self):
        session = transcription.LiveTranscriber(
            platform="youtube",
            source_id="video-id",
            source_resolver=lambda: "https://example.test/live.m3u8",
            target_language="en",
            translation_enabled=False,
            ffmpeg_path="ffmpeg",
        )
        session.configure_translation(True, "ja")
        self.assertTrue(session.translation_enabled)
        self.assertEqual(session.target_language, "ja")

    def test_start_reports_missing_ffmpeg(self):
        with patch("src.transcription.shutil.which", return_value=None):
            session = transcription.LiveTranscriber(
                platform="bilibili",
                source_id="123",
                source_resolver=lambda: "https://example.test/live.flv",
                target_language="en",
            )
        with self.assertRaisesRegex(RuntimeError, "FFmpeg was not found"):
            session.start()


if __name__ == "__main__":
    unittest.main()
