import unittest

import desktop_app
from desktop_app import (
    _CHAT_LAYOUT_BREAKPOINT,
    _chat_splitter_layout,
    _monitor_card_columns,
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

    def test_monitor_cards_use_fewer_columns_at_minimal_width(self):
        self.assertEqual(_monitor_card_columns(639), 1)
        self.assertEqual(_monitor_card_columns(640), 2)
        self.assertEqual(_monitor_card_columns(1019), 2)
        self.assertEqual(_monitor_card_columns(1020), 3)

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_stream_title_elides_to_one_line_and_keeps_full_tooltip(self):
        app = desktop_app.QtWidgets.QApplication.instance()
        if app is None:
            app = desktop_app.QtWidgets.QApplication([])
        label = desktop_app._ElidedLabel()
        title = "A very long stream title that does not fit"
        label.resize(90, 24)
        label.setFullText(title)
        label.show()
        app.processEvents()

        self.assertNotEqual(label.text(), title)
        self.assertEqual(label.toolTip(), title)

        label.resize(800, 24)
        app.processEvents()
        self.assertEqual(label.text(), title)

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
