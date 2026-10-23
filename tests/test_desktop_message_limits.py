import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import desktop_app
from desktop_app import _limit_messages_per_room, _retain_selected_room_messages


class DesktopMessageLimitTests(unittest.TestCase):
    def test_busy_room_does_not_evict_quiet_room_and_order_is_preserved(self):
        messages = [
            {"platform": "bilibili", "_monitor_id": room, "text": str(index)}
            for index, room in enumerate(("a", "b", "a", "a", "a"))
        ]

        retained = _limit_messages_per_room(messages, 2)

        self.assertEqual(retained, [messages[1], messages[3], messages[4]])
        self.assertIs(retained[0], messages[1])

    def test_rooms_and_platforms_have_independent_limits(self):
        messages = [
            {"platform": platform, "room_id": room, "text": str(index)}
            for index in range(3)
            for platform, room in (
                ("bilibili", "123"),
                ("bilibili", "456"),
                ("missevan", "123"),
            )
        ]

        self.assertEqual(_limit_messages_per_room(messages, 1), messages[-3:])

    def test_channel_fallback_and_empty_history(self):
        messages = [
            {"platform": "youtube", "channel_id": "a"},
            {"platform": "youtube", "channel_id": "b"},
            {"platform": "youtube", "channel_id": "a"},
        ]
        self.assertEqual(_limit_messages_per_room(messages, 1), messages[1:])
        self.assertEqual(_limit_messages_per_room([], 10), [])
        self.assertEqual(_limit_messages_per_room(messages, 0), [])

    def test_only_selected_rooms_are_retained_with_limits_applied_per_room(self):
        messages = [
            {"platform": platform, "_monitor_id": monitor_id, "text": str(index)}
            for index, (platform, monitor_id) in enumerate((
                ("youtube", "youtube:a"),
                ("youtube", "youtube:b"),
                ("youtube", "youtube:a"),
                ("bilibili", "bilibili:c"),
                ("bilibili", "bilibili:d"),
                ("bilibili", "bilibili:c"),
            ))
        ]

        retained = _retain_selected_room_messages(
            messages,
            {"youtube": "youtube:a", "bilibili": "bilibili:c"},
            {"youtube:a", "youtube:b", "bilibili:c", "bilibili:d"},
            1,
        )

        self.assertEqual(
            [(message["platform"], message["text"]) for message in retained],
            [("youtube", "2"), ("bilibili", "5")],
        )

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_changing_setting_trims_each_room_and_refreshes_immediately(self):
        messages = [
            {"platform": "youtube", "_monitor_id": room}
            for room in ("a", "b", "a", "b")
        ]
        window = SimpleNamespace(
            _settings=Mock(),
            _messages=messages,
            _paid=[],
            _joins=[],
            _monitor_targets=[
                {"id": "a", "platform": "youtube"},
                {"id": "b", "platform": "youtube"},
            ],
            chat_room_selectors={
                "youtube": SimpleNamespace(currentData=lambda: "a"),
            },
            max_messages=SimpleNamespace(value=lambda: 1),
            _refresh_feeds=Mock(),
        )
        window._selected_chat_room_ids = lambda: {
            "youtube": "a",
        }
        window._retain_selected_feed_messages = (
            lambda: desktop_app._DesktopWindow._retain_selected_feed_messages(window)
        )

        desktop_app._DesktopWindow._set_message_limit(window, 1)

        self.assertEqual(window._messages, [messages[2]])
        window._settings.setValue.assert_called_once_with("max_messages", 1)
        window._refresh_feeds.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
