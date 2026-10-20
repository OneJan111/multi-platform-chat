import unittest

from desktop_app import _message_matches_selected_chat_room


class DesktopTtsSelectionTests(unittest.TestCase):
    def test_only_selected_enabled_room_is_eligible_for_tts(self):
        selected_ids = {
            "youtube": "youtube:channel-a",
            "bilibili": "bilibili:room-a",
            "missevan": "missevan:room-a",
        }
        enabled_ids = set(selected_ids.values()) | {"bilibili:room-b"}

        self.assertTrue(
            _message_matches_selected_chat_room(
                {
                    "platform": "bilibili",
                    "_monitor_id": "bilibili:room-a",
                },
                selected_ids,
                enabled_ids,
            )
        )
        self.assertFalse(
            _message_matches_selected_chat_room(
                {
                    "platform": "bilibili",
                    "_monitor_id": "bilibili:room-b",
                },
                selected_ids,
                enabled_ids,
            )
        )
        self.assertFalse(
            _message_matches_selected_chat_room(
                {"platform": "youtube", "_monitor_id": "youtube:unknown"},
                selected_ids,
                enabled_ids,
            )
        )

    def test_unselected_or_disabled_room_is_not_eligible_for_tts(self):
        self.assertFalse(
            _message_matches_selected_chat_room(
                {"platform": "youtube", "_monitor_id": "youtube:channel-a"},
                {},
                {"youtube:channel-a"},
            )
        )
        self.assertFalse(
            _message_matches_selected_chat_room(
                {"platform": "youtube", "_monitor_id": "youtube:channel-a"},
                {"youtube": "youtube:channel-a"},
                set(),
            )
        )


if __name__ == "__main__":
    unittest.main()
