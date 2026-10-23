import unittest

from desktop_app import _monitored_target_for_message


class DesktopArchiveMonitorScopeTests(unittest.TestCase):
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
                "enabled": False,
            },
        ]

    def test_only_the_matching_room_with_saving_enabled_can_be_saved(self):
        target = _monitored_target_for_message(
            {
                "platform": "bilibili",
                "_monitor_id": "bilibili:101",
            },
            self.targets,
        )

        self.assertEqual(target["target"], "101")

    def test_room_without_saving_enabled_or_removed_room_is_not_saved(self):
        for monitor_id in ("bilibili:202", "bilibili:removed"):
            with self.subTest(monitor_id=monitor_id):
                self.assertIsNone(
                    _monitored_target_for_message(
                        {
                            "platform": "bilibili",
                            "_monitor_id": monitor_id,
                        },
                        self.targets,
                    )
                )

    def test_missing_monitor_id_only_maps_to_a_single_enabled_room(self):
        message = {"platform": "bilibili"}

        self.assertEqual(
            _monitored_target_for_message(message, self.targets)["target"],
            "101",
        )
        self.assertIsNone(
            _monitored_target_for_message(
                message,
                self.targets + [{
                    "id": "bilibili:303",
                    "platform": "bilibili",
                    "target": "303",
                    "enabled": True,
                }],
            )
        )


if __name__ == "__main__":
    unittest.main()
