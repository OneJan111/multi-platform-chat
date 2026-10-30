import unittest
from unittest.mock import Mock, patch

from edgeone_collector import EdgeOneCollector
from src.server_chat_history import ServerChatHistory


class EdgeOneCollectorTests(unittest.TestCase):
    def make_collector(self, sources=None):
        return EdgeOneCollector(
            "https://pages.example.com",
            "collector-token-" + "x" * 32,
            sources=sources or {"bilibili": "123", "youtube": "channel"},
        )

    def test_audio_source_priority_is_bilibili_then_youtube_then_missevan(self):
        collector = self.make_collector({
            "bilibili": "123",
            "youtube": "https://www.youtube.com/@creator",
            "missevan": "456",
        })
        live = {
            "bilibili": (True, "123"),
            "youtube": (True, "video-id"),
            "missevan": (True, "456"),
        }

        selected = collector._choose_audio_source(live)

        self.assertEqual(selected[:2], ("bilibili", "123"))

        live["bilibili"] = (False, "")
        selected = collector._choose_audio_source(live)
        self.assertEqual(selected[:2], ("youtube", "video-id"))

        live["youtube"] = (False, "")
        selected = collector._choose_audio_source(live)
        self.assertEqual(selected[:2], ("missevan", "456"))

    def test_chat_cursors_advance_only_after_successful_edge_sync(self):
        collector = self.make_collector()
        collector.history = ServerChatHistory()
        collector.history.append_many([
            {"id": "1", "platform": "youtube", "text": "first"},
            {"id": "2", "platform": "youtube", "text": "second"},
        ])
        collector._request = Mock(side_effect=[RuntimeError("offline"), {}])

        with self.assertRaisesRegex(RuntimeError, "offline"):
            collector._sync_chat()
        self.assertEqual(collector._chat_cursor, 0)

        collector._request = Mock(return_value={})
        collector._sync_chat()
        self.assertEqual(collector._chat_cursor, 2)
        payload = collector._request.call_args.kwargs["payload"]
        self.assertEqual([item["id"] for item in payload["messages"]], ["1", "2"])

    def test_idle_sync_does_not_repeat_kv_writes(self):
        collector = self.make_collector()
        collector._request = Mock(return_value={})

        collector._sync_chat()
        collector._sync_chat()

        self.assertEqual(collector._request.call_count, 1)

    def test_environment_kill_switch_setting_stops_current_transcriber(self):
        collector = self.make_collector()
        transcriber = Mock()
        transcriber._thread = None
        collector.transcriber = transcriber
        collector._transcription_key = ("bilibili", "123", "ja")

        collector._sync_transcriber({"transcriptionEnabled": False})

        transcriber.stop.assert_called_once_with()
        self.assertIsNone(collector.transcriber)
        self.assertEqual(collector._active_source, "")

    def test_recognized_text_is_forwarded_without_uploading_audio(self):
        collector = self.make_collector()
        collector._request = Mock(return_value={
            "original": "こんにちは",
            "translated": "你好",
        })
        with patch(
            "edgeone_collector.tencent_realtime_asr.recognize_wav_segment",
            return_value=("こんにちは", 8.0),
        ) as recognize, patch.dict(
            "os.environ",
            {
                "TENCENT_ASR_APP_ID": "1234567890",
                "TENCENT_ASR_SECRET_ID": "asr-id",
                "TENCENT_ASR_SECRET_KEY": "asr-key",
            },
        ):
            result = collector._recognize_segment(
                Mock(), "ja", "bilibili"
            )

        recognize.assert_called_once_with(
            recognize.call_args.args[0],
            "ja",
            "1234567890",
            "asr-id",
            "asr-key",
        )
        payload = collector._request.call_args.kwargs["payload"]
        self.assertEqual(payload["original"], "こんにちは")
        self.assertEqual(payload["audioDuration"], 8.0)
        self.assertNotIn("audioBase64", payload)
        self.assertEqual(result["translated"], "你好")

    def test_starts_only_the_highest_priority_live_platform(self):
        collector = self.make_collector({
            "bilibili": "123",
            "youtube": "https://www.youtube.com/@creator",
        })
        live = {
            "bilibili": (True, "123"),
            "youtube": (True, "video-id"),
        }
        with patch("edgeone_collector.transcription.LiveTranscriber") as make_transcriber:
            collector._sync_transcriber(
                {"transcriptionEnabled": True, "audioLanguage": "ja"},
                live,
            )

        make_transcriber.assert_called_once()
        self.assertEqual(make_transcriber.call_args.kwargs["platform"], "bilibili")
        self.assertEqual(make_transcriber.call_args.kwargs["target_language"], "zh-CN")
        make_transcriber.return_value.start.assert_called_once_with()
        self.assertEqual(collector._active_source, "bilibili")


if __name__ == "__main__":
    unittest.main()
