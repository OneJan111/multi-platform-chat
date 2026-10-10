import csv
import io
import unittest

from src import highlights as hl


def _events(spec):
    """spec: list of (second, count, paid)."""
    out = []
    for sec, count, paid in spec:
        out += [{"ts": 1_000_000 + sec + i * 0.1, "platform": "bilibili", "paid": paid, "text": "哈哈哈哈哈"}
                for i in range(count)]
    return out


class HighlightTests(unittest.TestCase):
    def test_to_epoch_handles_epoch_ms_and_iso(self):
        self.assertEqual(hl.to_epoch("1700000000"), 1700000000)
        self.assertEqual(hl.to_epoch(1700000000000), 1700000000)
        self.assertEqual(hl.to_epoch("2023-11-14T22:13:20Z"), 1700000000)
        self.assertIsNone(hl.to_epoch("nope"))
        self.assertIsNone(hl.to_epoch(""))

    def test_burst_found_against_quiet_baseline(self):
        quiet = [(s, 1, False) for s in range(0, 600, 30)]
        events = _events(quiet + [(300, 30, False), (330, 20, False), (335, 2, True)])
        clips = hl.find_highlights(events, window=30, pre_roll=20, post_roll=10)
        self.assertEqual(len(clips), 1)
        clip = clips[0]
        self.assertEqual(clip["start"] - 1_000_000, 280)
        self.assertEqual(clip["end"] - 1_000_000, 370)
        self.assertEqual(clip["paid"], 2)
        self.assertEqual(clip["phrases"][0], ("哈哈哈", clip["chat"]))

    def test_top_keeps_busiest_in_time_order(self):
        events = _events([(0, 1, False), (100, 1, False), (200, 1, False), (300, 1, False), (400, 1, False),
                          (500, 1, False), (600, 1, False),
                          (60, 10, False), (240, 40, False), (480, 20, False)])
        clips = hl.find_highlights(events, window=30, top=2, pre_roll=0, post_roll=0)
        self.assertEqual([c["start"] - 1_000_000 for c in clips], [240, 480])

    def test_exports(self):
        clip = {"start": 100.0, "end": 145.5, "phrases": [("666", 9)], "paid_texts": [], "sample": []}
        self.assertEqual(hl.offset(3725), "01:02:05")
        self.assertEqual(hl.offset(-5), "00:00:00")
        self.assertEqual(hl.timecode(61.5, 30, hour=1), "01:01:01:15")
        edl = hl.to_edl([clip], origin=40.0, fps=30, hour=1).decode()
        self.assertIn("001  001      V     C        01:01:00:00 01:01:00:01 01:01:00:00 01:01:00:01", edl)
        self.assertIn(" |C:ResolveColorRed |M:#1 666×9 |D:1365", edl)
        data = hl.to_csv([{"开始": "00:01:00", "热词": "哈哈"}])
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(list(csv.reader(io.StringIO(data.decode("utf-8-sig")))), [["开始", "热词"], ["00:01:00", "哈哈"]])


if __name__ == "__main__":
    unittest.main()
