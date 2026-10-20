import unittest

from desktop_app import (
    _selected_transcription_room,
    _transcription_room_entries,
)


class DesktopTranscriptionRoomSelectionTests(unittest.TestCase):
    def setUp(self):
        self.targets = [
            {
                "id": "youtube:channel-one",
                "platform": "youtube",
                "target": "channel-one",
                "enabled": True,
            },
            {
                "id": "youtube:channel-two",
                "platform": "youtube",
                "target": "channel-two",
                "enabled": True,
            },
            {
                "id": "bilibili:123",
                "platform": "bilibili",
                "target": "123",
                "enabled": True,
            },
            {
                "id": "bilibili:456",
                "platform": "bilibili",
                "target": "456",
                "enabled": False,
            },
        ]

    def test_room_choices_are_limited_to_enabled_rooms_on_selected_site(self):
        self.assertEqual(
            [entry["id"] for entry in _transcription_room_entries(
                "bilibili", self.targets
            )],
            ["bilibili:123"],
        )

    def test_start_room_lookup_returns_only_explicitly_selected_room(self):
        self.assertEqual(
            _selected_transcription_room(
                "youtube", "youtube:channel-two", self.targets
            )["target"],
            "channel-two",
        )
        self.assertIsNone(
            _selected_transcription_room(
                "youtube", "", self.targets
            )
        )
        self.assertIsNone(
            _selected_transcription_room(
                "bilibili", "bilibili:456", self.targets
            )
        )


if __name__ == "__main__":
    unittest.main()
