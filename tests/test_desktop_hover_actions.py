import unittest
from unittest.mock import Mock

from desktop_app import (
    _feed_scroll_click_state,
    _message_action_names,
    _reading_tooltip_allowed,
    _selected_feed_indices,
)


class DesktopHoverActionTests(unittest.TestCase):
    def test_hidden_chat_cannot_show_tooltip_even_when_window_is_active(self):
        widget = Mock()
        widget.isVisible.return_value = False
        widget.window.return_value.isActiveWindow.return_value = True
        self.assertFalse(_reading_tooltip_allowed(widget))

    def test_visible_chat_cannot_show_tooltip_when_window_is_inactive(self):
        widget = Mock()
        widget.isVisible.return_value = True
        widget.window.return_value.isActiveWindow.return_value = False
        self.assertFalse(_reading_tooltip_allowed(widget))

    def test_visible_chat_in_active_window_can_show_tooltip(self):
        widget = Mock()
        widget.isVisible.return_value = True
        widget.window.return_value.isActiveWindow.return_value = True
        self.assertTrue(_reading_tooltip_allowed(widget))

    def test_first_click_pauses_feed_on_clicked_message(self):
        self.assertEqual(
            _feed_scroll_click_state(False, None, "chat-1"),
            (True, "chat-1"),
        )

    def test_clicking_paused_message_again_resumes_feed(self):
        self.assertEqual(
            _feed_scroll_click_state(True, "chat-1", "chat-1"),
            (False, None),
        )

    def test_clicking_another_message_while_paused_keeps_feed_paused(self):
        self.assertEqual(
            _feed_scroll_click_state(True, "chat-1", "chat-2"),
            (True, "chat-2"),
        )

    def test_feed_refresh_can_restore_selection_for_chat_or_gift(self):
        chat_message = {"_desktop_feed_id": "chat-1", "text": "chat"}
        gift_message = {"_desktop_feed_id": "paid-1", "text": "gift"}

        self.assertEqual(
            _selected_feed_indices(
                [chat_message, gift_message],
                [dict(gift_message)],
            ),
            [1],
        )

    def test_feed_refresh_does_not_restore_a_filtered_out_selection(self):
        selected_message = {"_desktop_feed_id": "removed"}

        self.assertEqual(
            _selected_feed_indices(
                [{"_desktop_feed_id": "remaining"}],
                [selected_message],
            ),
            [],
        )

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
