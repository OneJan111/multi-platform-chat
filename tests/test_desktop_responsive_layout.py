import unittest
from collections import OrderedDict

import desktop_app
from desktop_app import (
    _CHAT_LAYOUT_BREAKPOINT,
    _bilibili_zone,
    _chat_splitter_layout,
    _dedupe_combined_monitor_messages,
    _monitor_card_columns,
    _missevan_viewer_count,
    _saved_record_enabled_ids,
    _saved_splitter_sizes,
    _two_row_group_height,
    _youtube_channel_for_video,
    _youtube_channel_stream_map,
    _youtube_monitor_groups,
    _youtube_channel_video_id,
    _youtube_direct_stream_finished,
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

    def test_bilibili_zone_combines_parent_and_area(self):
        self.assertEqual(_bilibili_zone("手游", "原神"), "手游 / 原神")
        self.assertEqual(_bilibili_zone("手游", ""), "手游")
        self.assertEqual(_bilibili_zone("手游", "手游"), "手游")
        self.assertEqual(_bilibili_zone("", ""), "")

    def test_default_feed_panels_fit_two_rows(self):
        self.assertEqual(_two_row_group_height(220, 180, 30), 100)
        self.assertEqual(_two_row_group_height(30, 180, 30), 60)

    def test_missevan_websocket_viewer_count_overrides_api_count(self):
        self.assertEqual(_missevan_viewer_count(0, 18), 18)
        self.assertEqual(_missevan_viewer_count(21, 0), 0)
        self.assertEqual(_missevan_viewer_count(0, None), 0)

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

    def test_recording_preferences_restore_only_configured_rooms(self):
        settings = _Settings({
            "record_enabled_ids": ["youtube:one", "bilibili:two", "removed:room"],
        })
        self.assertEqual(
            _saved_record_enabled_ids(settings, {"youtube:one", "bilibili:two"}),
            {"youtube:one", "bilibili:two"},
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

    def test_scheduled_video_can_revert_to_owning_channel(self):
        self.assertEqual(
            _youtube_channel_for_video({
                "channel_id": "UCabcdefghijklmnopqrstuv",
            }),
            "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv",
        )
        self.assertEqual(_youtube_channel_for_video({"channel_id": ""}), "")
        self.assertTrue(
            _youtube_direct_stream_finished(
                {"ended": True}, "https://www.youtube.com/channel/UCabc"
            )
        )
        self.assertFalse(
            _youtube_direct_stream_finished(
                {"ended": False}, "https://www.youtube.com/channel/UCabc"
            )
        )
        self.assertFalse(_youtube_direct_stream_finished({"ended": True}, ""))

    def test_stream_and_channel_targets_group_when_watching_same_video(self):
        video_id = "AbCdEf12345"
        targets = [
            {"id": "youtube:channel", "platform": "youtube",
             "target": "https://www.youtube.com/@channel"},
            {"id": f"youtube:{video_id}", "platform": "youtube",
             "target": f"https://www.youtube.com/watch?v={video_id}"},
        ]
        statuses = {
            "youtube:channel": {"video_id": video_id},
            f"youtube:{video_id}": {"video_id": video_id},
        }

        self.assertEqual(
            _youtube_monitor_groups(targets, statuses),
            {f"youtube:{video_id}": ("youtube:channel",)},
        )
        self.assertEqual(
            _youtube_channel_stream_map(
                {f"youtube:{video_id}": ("youtube:channel",)}
            ),
            {"youtube:channel": f"youtube:{video_id}"},
        )
        statuses["youtube:channel"]["video_id"] = "Different123"
        self.assertEqual(_youtube_monitor_groups(targets, statuses), {})

    def test_grouped_stream_messages_are_not_added_twice(self):
        seen = OrderedDict()
        groups = {"youtube:video": ("youtube:channel",)}
        first = {
            "id": "chat-1", "platform": "youtube",
            "_monitor_id": "youtube:video",
        }
        duplicate = {
            "id": "chat-1", "platform": "youtube",
            "_monitor_id": "youtube:channel",
        }

        expected = {**first, "_monitor_id": "youtube:channel"}
        self.assertEqual(
            _dedupe_combined_monitor_messages([first, duplicate], groups, seen),
            [expected],
        )
        self.assertEqual(
            _dedupe_combined_monitor_messages([duplicate], groups, seen), []
        )


if __name__ == "__main__":
    unittest.main()
