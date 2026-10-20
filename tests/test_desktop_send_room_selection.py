import unittest

from desktop_app import _selected_send_destinations


class DesktopSendRoomSelectionTests(unittest.TestCase):
    def setUp(self):
        self.targets = [
            {
                "id": "bilibili:101",
                "platform": "bilibili",
                "target": "101",
                "enabled": True,
            },
            {
                "id": "bilibili:202",
                "platform": "bilibili",
                "target": "202",
                "enabled": True,
            },
            {
                "id": "youtube:channel-a",
                "platform": "youtube",
                "target": "channel-a",
                "enabled": True,
            },
            {
                "id": "missevan:303",
                "platform": "missevan",
                "target": "303",
                "enabled": False,
            },
        ]

    def test_only_one_explicitly_selected_room_per_site_is_sent_to(self):
        destinations = _selected_send_destinations(
            ["bilibili", "youtube"],
            {
                "bilibili": "bilibili:202",
                "youtube": "youtube:channel-a",
            },
            self.targets,
        )

        self.assertEqual(
            [(entry["platform"], entry["target"]) for entry in destinations],
            [("bilibili", "202"), ("youtube", "channel-a")],
        )

    def test_unselected_or_disabled_rooms_are_never_fallback_destinations(self):
        destinations = _selected_send_destinations(
            ["bilibili", "missevan"],
            {"bilibili": "", "missevan": "missevan:303"},
            self.targets,
        )

        self.assertEqual(destinations, [])


if __name__ == "__main__":
    unittest.main()
