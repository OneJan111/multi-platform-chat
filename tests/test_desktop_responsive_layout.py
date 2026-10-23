import unittest

from desktop_app import (
    _CHAT_LAYOUT_BREAKPOINT,
    _chat_splitter_layout,
    _saved_splitter_sizes,
    _youtube_channel_video_id,
)


class _Settings:
    def __init__(self, values=None):
        self.values = values or {}

    def value(self, key, default, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None else value


class DesktopResponsiveLayoutTests(unittest.TestCase):
    def test_narrow_window_puts_paid_feed_above_chat(self):
        self.assertEqual(
            _chat_splitter_layout(_CHAT_LAYOUT_BREAKPOINT - 1),
            ("vertical", ("paid", "chat")),
        )

    def test_wide_window_keeps_chat_left_and_paid_feed_right(self):
        self.assertEqual(
            _chat_splitter_layout(_CHAT_LAYOUT_BREAKPOINT),
            ("horizontal", ("chat", "paid")),
        )

    def test_splitter_preferences_are_restored_when_valid(self):
        settings = _Settings({"join_sizes": [5, 2]})
        self.assertEqual(
            _saved_splitter_sizes(settings, "join_sizes", [7, 1]),
            [5, 2],
        )

    def test_invalid_splitter_preferences_use_defaults(self):
        for saved in ([5], [0, 3], ["wide", "short"]):
            with self.subTest(saved=saved):
                settings = _Settings({"join_sizes": saved})
                self.assertEqual(
                    _saved_splitter_sizes(settings, "join_sizes", [7, 1]),
                    [7, 1],
                )

    def test_channel_monitor_keeps_the_nearest_scheduled_video_id(self):
        self.assertEqual(
            _youtube_channel_video_id({
                "video_id": "scheduled01",
                "live": False,
                "upcoming": True,
            }),
            "scheduled01",
        )

    def test_channel_monitor_ignores_video_when_channel_is_offline(self):
        self.assertEqual(
            _youtube_channel_video_id({
                "video_id": "oldvideo001",
                "live": False,
                "upcoming": False,
            }),
            "",
        )


if __name__ == "__main__":
    unittest.main()
