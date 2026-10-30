import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import desktop_app
from desktop_app import (
    _chat_event_card_colors,
    _archive_messages_as_tsv,
    _archive_messages_newest_first,
    _format_message_for_copy,
    _message_avatar_url,
)


class DesktopChatCopyTests(unittest.TestCase):
    def test_saved_chat_messages_display_newest_first(self):
        messages = [{"text": "first"}, {"text": "second"}, {"text": "third"}]

        ordered = _archive_messages_newest_first(messages)

        self.assertEqual([m["text"] for m in ordered], ["third", "second", "first"])
        self.assertEqual(messages[0]["text"], "first")

    def test_saved_chat_display_keeps_only_latest_500_messages(self):
        messages = [{"text": str(index)} for index in range(5000)]

        ordered = _archive_messages_newest_first(messages)

        self.assertEqual(len(ordered), 500)
        self.assertEqual(ordered[0]["text"], "4999")
        self.assertEqual(ordered[-1]["text"], "4500")
        self.assertEqual(len(messages), 5000)

    def test_saved_chat_toolbar_labels_are_short_and_translated(self):
        from src import i18n

        for label in ("Reload", "Save", "Copy table", "Delete"):
            for lang in ("zh", "ja"):
                translated = i18n.translate(label, lang)
                self.assertNotEqual(translated, label)
                self.assertLessEqual(len(translated), 5)
    def test_saved_chat_table_is_tsv_with_headers_and_safe_cells(self):
        copied = _archive_messages_as_tsv(
            [
                {
                    "timestamp": "not-a-time",
                    "platform": "bilibili",
                    "author": "viewer\t1",
                    "text": "first line\nsecond line",
                }
            ],
            ("Time", "Platform", "Author", "Message"),
        )

        self.assertEqual(
            copied,
            "Time\tPlatform\tAuthor\tMessage\n"
            "not-a-time\tbilibili\tviewer 1\tfirst line second line",
        )

    def test_copy_format_includes_timestamp_room_author_and_message(self):
        message = {
            "timestamp": "1792321020",
            "platform": "bilibili",
            "author": "viewer",
            "text": "hello",
        }

        copied = _format_message_for_copy(message)

        self.assertIn("[BILIBILI] viewer: hello", copied)
        self.assertNotIn("1792321020", copied)

    def test_copy_format_includes_available_translation(self):
        copied = _format_message_for_copy({
            "timestamp": "",
            "platform": "youtube",
            "author": "viewer",
            "text": "hello",
            "translation": "你好",
        })

        self.assertIn("viewer: hello", copied)
        self.assertIn("Translation: 你好", copied)

    def test_paid_and_membership_events_get_distinct_card_styles(self):
        self.assertEqual(
            _chat_event_card_colors({
                "platform": "missevan",
                "is_super_admin": True,
                "type": "danmaku",
            }),
            ("#b42318", "#ffffff", "#ef8178"),
        )
        self.assertEqual(
            _chat_event_card_colors({"type": "superchat"}),
            ("#f4dfaa", "#5a3d20", "#dfbd70"),
        )
        self.assertEqual(
            _chat_event_card_colors({"type": "gift"}),
            ("#eadcf2", "#49335a", "#c7a8d8"),
        )
        self.assertEqual(
            _chat_event_card_colors({"type": "newSponsorEvent"}),
            ("#dceaf6", "#29445f", "#a9c8e2"),
        )
        self.assertIsNone(_chat_event_card_colors({"type": "danmaku"}))

    def test_bilibili_avatar_uses_cached_profile_and_https_normalization(self):
        cached = _message_avatar_url(
            {"platform": "bilibili", "author_id": "42"},
            {"42": "https://i0.hdslb.com/bfs/face/avatar.png"},
        )
        incoming = _message_avatar_url(
            {
                "platform": "bilibili",
                "avatar": "http://i0.hdslb.com/bfs/face/avatar.png",
            },
            {},
        )

        self.assertEqual(cached, "https://i0.hdslb.com/bfs/face/avatar.png")
        self.assertEqual(incoming, cached)

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_copy_shortcut_copies_selected_label_text(self):
        app = desktop_app.QtWidgets.QApplication.instance()
        if app is None:
            app = desktop_app.QtWidgets.QApplication([])
        label = desktop_app.QtWidgets.QLabel()
        label.setTextFormat(desktop_app.QtCore.Qt.TextFormat.RichText)
        label.setTextInteractionFlags(
            desktop_app.QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | desktop_app.QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        label.setText("<b>viewer</b><br>hello chat")
        label.setSelection(0, len("viewerhello chat"))
        clipboard = Mock()

        class QApplicationMock:
            @staticmethod
            def focusWidget():
                return label

            @staticmethod
            def clipboard():
                return clipboard

        window = SimpleNamespace(
            _active_feed="chat",
            chat_list=Mock(),
            paid_list=Mock(),
        )
        with patch.object(
            desktop_app.QtWidgets, "QApplication", QApplicationMock
        ):
            desktop_app._DesktopWindow._copy_selected_chat(window)

        clipboard.setText.assert_called_once_with(label.selectedText())
        self.assertTrue(label.hasSelectedText())


if __name__ == "__main__":
    unittest.main()
