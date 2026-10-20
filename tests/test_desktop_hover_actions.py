import unittest

from desktop_app import _message_action_names


class DesktopHoverActionTests(unittest.TestCase):
    def test_regular_chat_actions_are_message_specific(self):
        self.assertEqual(
            _message_action_names("youtube"),
            ("Block", "Read", "Copy"),
        )

    def test_bilibili_paid_actions_include_thank_and_mute(self):
        self.assertEqual(
            _message_action_names("bilibili", paid=True),
            ("Block", "Read", "Thank", "Mute", "Copy"),
        )

    def test_non_bilibili_paid_actions_do_not_offer_mute(self):
        self.assertEqual(
            _message_action_names("missevan", paid=True),
            ("Block", "Read", "Thank", "Copy"),
        )


if __name__ == "__main__":
    unittest.main()
