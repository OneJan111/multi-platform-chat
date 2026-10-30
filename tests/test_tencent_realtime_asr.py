import base64
import hashlib
import hmac
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from src.tencent_realtime_asr import build_asr_url, recognize_wav_segment


class FakeWebSocket:
    def __init__(self):
        self.frames = [
            json.dumps({"code": 0, "message": "success"}),
            json.dumps({
                "code": 0,
                "result": {
                    "index": 1,
                    "slice_type": 2,
                    "voice_text_str": "こんにちは",
                },
            }),
            json.dumps({"code": 0, "final": 1}),
        ]
        self.sent_audio = []
        self.sent_control = []
        self.timeout = None
        self.closed = False

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self):
        return self.frames.pop(0)

    def send_binary(self, frame):
        self.sent_audio.append(frame)

    def send(self, message):
        self.sent_control.append(message)

    def close(self):
        self.closed = True


class TencentRealtimeASRTests(unittest.TestCase):
    def test_signed_url_uses_tencent_hmac_sha1_parameters(self):
        url = build_asr_url(
            "1234567890",
            "test-secret-id",
            "test-secret-key",
            "ja",
            timestamp=1700000000,
            nonce=12345,
            voice_id="voice-test",
        )
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        unsigned = {key: values[0] for key, values in params.items() if key != "signature"}
        canonical = "&".join(f"{key}={unsigned[key]}" for key in sorted(unsigned))
        signed_text = f"asr.cloud.tencent.com/asr/v2/1234567890?{canonical}"
        digest = hmac.new(
            b"test-secret-key",
            signed_text.encode("utf-8"),
            hashlib.sha1,
        ).digest()

        self.assertEqual(parsed.scheme, "wss")
        self.assertEqual(unsigned["engine_model_type"], "16k_ja")
        self.assertEqual(unsigned["voice_format"], "1")
        self.assertEqual(
            params["signature"][0],
            base64.b64encode(digest).decode("ascii"),
        )

    def test_wav_pcm_is_streamed_and_final_recognition_is_returned(self):
        fake_socket = FakeWebSocket()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "segment.wav"
            with wave.open(str(path), "wb") as audio_file:
                audio_file.setnchannels(1)
                audio_file.setsampwidth(2)
                audio_file.setframerate(16000)
                audio_file.writeframes(b"\0\0" * 8000)

            with patch(
                "src.tencent_realtime_asr.websocket.create_connection",
                return_value=fake_socket,
            ) as connect:
                text, duration = recognize_wav_segment(
                    path,
                    "ja",
                    "1234567890",
                    "test-secret-id",
                    "test-secret-key",
                )

        self.assertEqual(text, "こんにちは")
        self.assertEqual(duration, 0.5)
        self.assertEqual(sum(map(len, fake_socket.sent_audio)), 16000)
        self.assertEqual(fake_socket.sent_control, ['{"type": "end"}'])
        self.assertTrue(fake_socket.closed)
        self.assertIn("engine_model_type=16k_ja", connect.call_args.args[0])

    def test_rejects_unsupported_language_and_missing_credentials(self):
        with self.assertRaisesRegex(ValueError, "source language"):
            build_asr_url("1234567890", "id", "key", "en")
        with self.assertRaisesRegex(ValueError, "required"):
            build_asr_url("", "id", "key", "ja")


if __name__ == "__main__":
    unittest.main()
