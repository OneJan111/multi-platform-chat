import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import desktop_app
from src import bili_recorder


def _play_info(live=1, codecs=None):
    if codecs is None:
        codecs = [
            {"codec_name": "hevc", "current_qn": 10000, "base_url": "/hevc.flv?",
             "url_info": [{"host": "https://h.example", "extra": "x=1"}]},
            {"codec_name": "avc", "current_qn": 250, "base_url": "/avc.flv?",
             "url_info": [{"host": "https://a.example/", "extra": "y=2"}]},
        ]
    return {
        "live_status": live,
        "playurl_info": {"playurl": {"stream": [
            {"protocol_name": "http_hls", "format": [{"format_name": "ts", "codec": []}]},
            {"protocol_name": "http_stream", "format": [{"format_name": "flv", "codec": codecs}]},
        ]}},
    }


class _Response:
    def __init__(self, chunks):
        self._chunks = chunks
        self.closed = False

    def raise_for_status(self):
        pass

    def iter_content(self, _size):
        for chunk in self._chunks:
            if self.closed:
                return
            yield chunk

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.responses.pop(0))


class SelectStreamTests(unittest.TestCase):
    def test_prefers_http_stream_flv_avc(self):
        url, qn = bili_recorder.select_flv_stream(_play_info())
        self.assertEqual(url, "https://a.example/avc.flv?y=2")
        self.assertEqual(qn, 250)

    def test_falls_back_to_hevc(self):
        info = _play_info(codecs=[{"codec_name": "hevc", "current_qn": 400, "base_url": "/h?",
                                   "url_info": [{"host": "https://h", "extra": ""}]}])
        self.assertEqual(bili_recorder.select_flv_stream(info), ("https://h/h?", 400))

    def test_offline_and_missing_streams_raise(self):
        with self.assertRaises(RuntimeError):
            bili_recorder.select_flv_stream(_play_info(live=0))
        with self.assertRaises(RuntimeError):
            bili_recorder.select_flv_stream(_play_info(codecs=[]))


class RecordingPathTests(unittest.TestCase):
    def test_matches_bililive_recorder_template_and_sanitizes(self):
        path = bili_recorder.recording_path(
            "root", "123", "主播", 'Hi: a/b?*"', datetime(2026, 1, 2, 3, 4, 5, 678000)
        )
        self.assertEqual(path, Path("root") / "123-主播" / "录制-123-20260102-030405-678-Hi_ a_b___.flv")


class DanmakuXmlTests(unittest.TestCase):
    def test_writes_valid_xml(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.xml"
            writer = bili_recorder.DanmakuXmlWriter(path, "1", "n&<", "t\"", 1_700_000_100.0)
            writer.add({"type": "danmaku", "author": "a<b", "author_id": "7", "text": "x & y", "color": 255}, 1_700_000_101.5)
            writer.add({"type": "superchat", "author": "s", "author_id": "8", "text": "sc", "value": 30}, 1_700_000_102)
            writer.add({"type": "gift", "author": "g", "author_id": "9", "text": "🎁 x", "gift_count": 3}, 1_700_000_103)
            writer.add({"type": "enter", "author": "e"}, 1_700_000_104)
            writer.close()
            root = ET.parse(path).getroot()
            d = root.find("d")
            self.assertEqual(d.text, "x & y")
            self.assertEqual(d.get("user"), "a<b")
            self.assertTrue(d.get("p").startswith("1.500,1,25,255,1700000101500,"))
            self.assertEqual(root.find("sc").get("price"), "30")
            self.assertEqual(root.find("gift").get("giftcount"), "3")
            self.assertEqual(root.find("BililiveRecorderRecordInfo").get("name"), "n&<")
            self.assertEqual(len(root.findall("d")) + len(root.findall("sc")) + len(root.findall("gift")), 3)


class RecorderLoopTests(unittest.TestCase):
    def _wait(self, recorder):
        deadline = time.time() + 5
        while recorder.is_running and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(recorder.is_running)

    def test_reconnects_into_new_file_then_ends_when_offline(self):
        infos = [_play_info(), _play_info(), _play_info(live=0)]
        session = _Session([[b"FLV1", b"data"], [b"FLV2"]])
        with tempfile.TemporaryDirectory() as folder:
            recorder = bili_recorder.BilibiliRecorder(
                "5", folder, cookies={"SESSDATA": "s"}, name="n", title="t",
                fetch=lambda *_: infos.pop(0), session=session, retry_delay=0.01,
            )
            recorder.start()
            self._wait(recorder)
            state = recorder.snapshot()
            self.assertEqual(state["status"], "Stream ended")
            self.assertEqual(len(state["files"]), 2)
            self.assertEqual(Path(state["files"][0]).read_bytes(), b"FLV1data")
            self.assertTrue(Path(state["files"][0]).with_suffix(".xml").exists())
            self.assertEqual(state["total_bytes"], 12)
            self.assertIn("SESSDATA=s", session.calls[0][1]["headers"]["Cookie"])

    def test_non_flv_response_is_not_saved(self):
        infos = [_play_info(), _play_info(live=0)]
        with tempfile.TemporaryDirectory() as folder:
            recorder = bili_recorder.BilibiliRecorder(
                "5", folder, fetch=lambda *_: infos.pop(0),
                session=_Session([[b"<html>"]]), retry_delay=0.01,
            )
            recorder.start()
            self._wait(recorder)
            self.assertEqual(recorder.snapshot()["files"], [])
            self.assertEqual(list(Path(folder).rglob("*")), [])

    def test_stop_ends_recording(self):
        def endless():
            yield b"FLV"
            while True:
                time.sleep(0.01)
                yield b"x"

        session = _Session([endless()])
        with tempfile.TemporaryDirectory() as folder:
            recorder = bili_recorder.BilibiliRecorder(
                "5", folder, save_danmaku=False,
                fetch=lambda *_: _play_info(), session=session, retry_delay=0.01,
            )
            recorder.start()
            deadline = time.time() + 5
            while recorder.snapshot()["status"] != "Recording" and time.time() < deadline:
                time.sleep(0.01)
            recorder.stop(wait=5)
            self.assertFalse(recorder.is_running)
            self.assertEqual(recorder.snapshot()["status"], "Stopped")


class FormatTests(unittest.TestCase):
    def test_size_and_duration(self):
        self.assertEqual(desktop_app._format_record_size(512), "512 B")
        self.assertEqual(desktop_app._format_record_size(1536), "1.5 KB")
        self.assertEqual(desktop_app._format_record_size(3 * 1024 ** 3), "3.0 GB")
        self.assertEqual(desktop_app._format_record_duration(3725.9), "1:02:05")


if __name__ == "__main__":
    unittest.main()
