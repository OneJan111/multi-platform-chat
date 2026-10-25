import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import desktop_app


@unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
class IncrementalFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (
            desktop_app.QtWidgets.QApplication.instance()
            or desktop_app.QtWidgets.QApplication([])
        )

    def setUp(self):
        self.chat = desktop_app.QtWidgets.QListWidget()
        self.paid = desktop_app.QtWidgets.QListWidget()
        self.window = SimpleNamespace(
            paid_list=self.paid,
            _feed_scroll_paused={"chat": False, "paid": False},
            _feed_paused_messages={"chat": None, "paid": None},
            _bilibili_avatar_cache={},
            _chat_image_cache={},
            _ui_language="en",
            _thanked_ids=set(),
            show_reading=Mock(),
            _resize_feed_items=lambda view: (
                desktop_app._DesktopWindow._resize_feed_items(self.window, view)
            ),
        )
        self.window.show_reading.isChecked.return_value = False

    def tearDown(self):
        self.chat.deleteLater()
        self.paid.deleteLater()
        self.app.processEvents()

    def render(self, messages):
        desktop_app._DesktopWindow._render_feed(
            self.window, self.chat, messages
        )

    def message(self, number):
        return {
            "_desktop_feed_id": number,
            "id": str(number),
            "platform": "bilibili",
            "author": "viewer",
            "text": f"message {number}",
        }

    def test_unchanged_and_appended_messages_preserve_widget_and_selection(self):
        first = self.message(1)
        self.render([first])
        row = self.chat.itemWidget(self.chat.item(0))
        label = row._chat_label
        label.setSelection(0, 5)
        selection = label.selectedText()
        self.render([first])
        self.render([first, self.message(2)])
        self.assertIs(self.chat.itemWidget(self.chat.item(0)), row)
        self.assertEqual(label.selectedText(), selection)
        self.assertEqual(self.chat.count(), 2)

    def test_mutation_updates_only_affected_row_and_removal_keeps_remaining(self):
        first, second = self.message(1), self.message(2)
        self.render([first, second])
        first_row = self.chat.itemWidget(self.chat.item(0))
        second_row = self.chat.itemWidget(self.chat.item(1))
        second["translation"] = "translated"
        self.render([first, second])
        self.assertIs(self.chat.itemWidget(self.chat.item(0)), first_row)
        updated = self.chat.itemWidget(self.chat.item(1))
        self.assertIsNot(updated, second_row)
        self.assertIn("translated", updated._chat_label.text())
        self.render([second])
        self.assertEqual(self.chat.count(), 1)
        self.assertIs(self.chat.itemWidget(self.chat.item(0)), updated)
        self.render([])
        self.assertEqual(self.chat.count(), 0)

    def test_reordering_and_reading_setting_invalidation(self):
        first, second = self.message(1), self.message(2)
        self.render([first, second])
        self.render([second, first])
        self.assertEqual(
            [self.chat.item(i).data(
                desktop_app.QtCore.Qt.ItemDataRole.UserRole
            )["id"] for i in range(2)],
            ["2", "1"],
        )
        row = self.chat.itemWidget(self.chat.item(0))
        self.window._thanked_ids.add("2")
        self.render([second, first])
        self.assertIsNot(self.chat.itemWidget(self.chat.item(0)), row)
        self.assertIn(
            "THANKED", self.chat.itemWidget(self.chat.item(0))._chat_label.text()
        )

    def test_loaded_image_invalidates_only_rows_using_that_image(self):
        first, second = self.message(1), self.message(2)
        url = "https://i0.hdslb.com/bfs/test.png"
        second["membership_icon"] = url
        self.render([first, second])
        first_row = self.chat.itemWidget(self.chat.item(0))
        second_row = self.chat.itemWidget(self.chat.item(1))
        self.window._chat_image_cache[url] = ("image/png", b"test")
        self.render([first, second])
        self.assertIs(self.chat.itemWidget(self.chat.item(0)), first_row)
        self.assertIsNot(self.chat.itemWidget(self.chat.item(1)), second_row)
