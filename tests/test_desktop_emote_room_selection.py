import unittest

from desktop_app import _selected_monitor_target


class DesktopEmoteRoomSelectionTests(unittest.TestCase):
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
                "target": "https://live.bilibili.com/202",
                "enabled": True,
            },
            {
                "id": "missevan:303",
                "platform": "missevan",
                "target": "303",
                "enabled": True,
            },
        ]

    def test_selected_room_is_used_instead_of_first_enabled_room(self):
        self.assertEqual(
            _selected_monitor_target(
                "bilibili", "bilibili:202", self.targets
            ),
            "https://live.bilibili.com/202",
        )

    def test_falls_back_to_first_enabled_room_if_selection_is_missing(self):
        self.assertEqual(
            _selected_monitor_target("bilibili", "", self.targets),
            "101",
        )

    def test_does_not_fall_back_to_another_platform(self):
        self.assertEqual(
            _selected_monitor_target("youtube", "", self.targets),
            "",
        )


if __name__ == "__main__":
    unittest.main()
