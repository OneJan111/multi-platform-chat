import unittest
from datetime import datetime

from desktop_app import _format_chat_timestamp


class DesktopTimestampTests(unittest.TestCase):
    def test_epoch_seconds_are_formatted_as_readable_local_time(self):
        timestamp = "1792321020"

        self.assertEqual(
            _format_chat_timestamp(timestamp),
            datetime.fromtimestamp(int(timestamp)).strftime("%H:%M:%S"),
        )

    def test_unparseable_timestamp_is_preserved(self):
        self.assertEqual(_format_chat_timestamp("unknown"), "unknown")

    def test_iso_timestamp_is_formatted_as_local_time(self):
        timestamp = "2026-10-18T12:34:56+00:00"

        self.assertEqual(
            _format_chat_timestamp(timestamp),
            datetime.fromisoformat(timestamp).astimezone().strftime("%H:%M:%S"),
        )


if __name__ == "__main__":
    unittest.main()
