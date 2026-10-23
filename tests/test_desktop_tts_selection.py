import unittest

from desktop_app import (
    _chat_speech_is_current,
    _message_matches_selected_chat_room,
)


class DesktopTtsSelectionTests(unittest.TestCase):
    def test_selected_room_is_eligible_for_tts_regardless_of_save_setting(self):
        selected_ids = {
            "youtube": "youtube:channel-a",
            "bilibili": "bilibili:room-a",
            "missevan": "missevan:room-a",
        }
        room_ids = set(selected_ids.values()) | {"bilibili:room-b"}

        self.assertTrue(
            _message_matches_selected_chat_room(
                {
                    "platform": "bilibili",
                    "_monitor_id": "bilibili:room-a",
                },
                selected_ids,
                room_ids,
                {"bilibili"},
            )
        )
        self.assertFalse(
            _message_matches_selected_chat_room(
                {
                    "platform": "bilibili",
                    "_monitor_id": "bilibili:room-b",
                },
                selected_ids,
                room_ids,
                {"bilibili"},
            )
        )
        self.assertFalse(
            _message_matches_selected_chat_room(
                {"platform": "youtube", "_monitor_id": "youtube:unknown"},
                selected_ids,
                room_ids,
                {"youtube", "bilibili", "missevan"},
            )
        )

    def test_save_setting_does_not_prevent_live_chat_tts(self):
        self.assertTrue(
            _message_matches_selected_chat_room(
                {"platform": "youtube", "_monitor_id": "youtube:channel-a"},
                {"youtube": "youtube:channel-a"},
                {"youtube:channel-a"},
                {"youtube"},
            )
        )
        self.assertFalse(
            _message_matches_selected_chat_room(
                {"platform": "youtube", "_monitor_id": "youtube:channel-a"},
                {},
                {"youtube:channel-a"},
                {"youtube"},
            )
        )
        self.assertTrue(
            _message_matches_selected_chat_room(
                {"platform": "youtube", "_monitor_id": "youtube:channel-a"},
                {"youtube": "youtube:channel-a"},
                {"youtube:channel-a"},
                {"youtube"},
            )
        )

    def test_unchecked_site_is_not_eligible_for_chat_tts(self):
        self.assertFalse(
            _message_matches_selected_chat_room(
                {
                    "platform": "youtube",
                    "_monitor_id": "youtube:channel-a",
                },
                {"youtube": "youtube:channel-a"},
                {"youtube:channel-a"},
                {"bilibili"},
            )
        )

    def test_queued_speech_is_discarded_after_room_selection_changes(self):
        self.assertFalse(
            _chat_speech_is_current(
                {
                    "platform": "youtube",
                    "_monitor_id": "youtube:channel-a",
                },
                {"youtube": "youtube:channel-a"},
                {"youtube:channel-a"},
                {"youtube"},
                queued_generation=2,
                current_generation=3,
            )
        )

    def test_current_speech_must_still_match_selected_room(self):
        self.assertFalse(
            _chat_speech_is_current(
                {
                    "platform": "youtube",
                    "_monitor_id": "youtube:channel-a",
                },
                {"youtube": "youtube:channel-b"},
                {"youtube:channel-a", "youtube:channel-b"},
                {"youtube"},
                queued_generation=3,
                current_generation=3,
            )
        )

    def test_delayed_speech_is_discarded_when_site_is_unchecked(self):
        self.assertFalse(
            _chat_speech_is_current(
                {
                    "platform": "youtube",
                    "_monitor_id": "youtube:channel-a",
                },
                {"youtube": "youtube:channel-a"},
                {"youtube:channel-a"},
                {"bilibili"},
                queued_generation=3,
                current_generation=3,
            )
        )


if __name__ == "__main__":
    unittest.main()
