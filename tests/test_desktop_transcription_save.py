import tempfile
import unittest
from pathlib import Path

from desktop_app import (
    _append_transcription_segment,
    _existing_lrc_offset,
    _format_transcription,
    _format_transcription_lrc,
    _write_transcription,
)


class DesktopTranscriptionSaveTests(unittest.TestCase):
    def test_lrc_uses_elapsed_timestamps_and_includes_translations(self):
        self.assertEqual(
            _format_transcription_lrc([
                {"start_seconds": 1.25, "original": "こんにちは", "translated": "Hello"},
                {"start_seconds": 65.5, "original": "次の文", "translated": ""},
            ]),
            "[00:01.25]こんにちは\n[00:01.25]Hello\n[01:05.50]次の文",
        )

    def test_lrc_rounds_across_minute_boundaries_and_flattens_lines(self):
        self.assertEqual(
            _format_transcription_lrc([
                {"start_seconds": 59.999, "original": "first\nsecond"},
                {"start_seconds": 3601, "original": "later"},
                {"original": "", "transcription_error": "failed"},
            ]),
            "[01:00.00]first second\n[60:01.00]later",
        )

    def test_lrc_rejects_missing_or_invalid_elapsed_timestamps(self):
        for seconds in (None, -1, float("nan"), float("inf"), "12:34:56"):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                _format_transcription_lrc([
                    {"start_seconds": seconds, "original": "text"},
                ])

    def test_format_includes_timestamps_original_and_translation(self):
        self.assertEqual(
            _format_transcription([
                {"time": "12:34:56", "original": "こんにちは", "translated": "Hello"},
                {"time": "12:35:04", "original": "次の文", "translated": ""},
            ]),
            "[12:34:56] こんにちは\n🌐 Hello\n\n[12:35:04] 次の文",
        )

    def test_write_transcription_saves_utf8_and_creates_parent_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "transcript.txt"

            result = _write_transcription(path, "[12:34:56] こんにちは\n🌐 Hello")

            self.assertEqual(result, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "[12:34:56] こんにちは\n🌐 Hello")

    def test_append_transcript_adds_text_segments_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "transcript.txt"
            _append_transcription_segment(path, {
                "time": "12:34:56", "original": "こんにちは", "translated": "Hello",
            })
            _append_transcription_segment(path, {
                "time": "12:35:04", "original": "次の文",
            })

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "[12:34:56] こんにちは\n🌐 Hello\n\n[12:35:04] 次の文",
            )

    def test_append_transcript_adds_lrc_segments_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "transcript.lrc"
            _append_transcription_segment(path, {
                "start_seconds": 1.25, "original": "こんにちは",
                "translated": "Hello",
            })
            _append_transcription_segment(path, {
                "start_seconds": 65.5, "original": "次の文",
            })

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "[00:01.25]こんにちは\n[00:01.25]Hello\n[01:05.50]次の文",
            )

    def test_append_empty_segment_does_not_create_a_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "transcript.txt"

            _append_transcription_segment(path, {"original": ""})

            self.assertFalse(path.exists())

    def test_lrc_appending_offsets_later_transcription_sessions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "transcript.lrc"
            _append_transcription_segment(
                path, {"start_seconds": 0, "original": "first"}
            )
            next_offset = _existing_lrc_offset(path)
            _append_transcription_segment(
                path,
                {"start_seconds": 0, "original": "second"},
                next_offset,
            )

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "[00:00.00]first\n[00:08.00]second",
            )


if __name__ == "__main__":
    unittest.main()
