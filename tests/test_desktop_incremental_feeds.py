import unittest
import base64
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

    def test_non_square_emojis_and_stickers_preserve_aspect_ratio(self):
        for width, height, maximum, expected in (
            (200, 100, 26, (26, 13)),
            (100, 200, 96, (48, 96)),
            (100, 100, 20, (20, 20)),
        ):
            with self.subTest(width=width, height=height):
                image = desktop_app.QtGui.QImage(
                    width, height, desktop_app.QtGui.QImage.Format.Format_ARGB32
                )
                image.fill(desktop_app.QtCore.Qt.GlobalColor.red)
                buffer = desktop_app.QtCore.QBuffer()
                buffer.open(desktop_app.QtCore.QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "PNG")
                data = bytes(buffer.data())
                size = desktop_app._chat_image_size(data, maximum)
                self.assertEqual((size.width(), size.height()), expected)
                self.assertEqual(
                    desktop_app._chat_image_dimensions(data, maximum),
                    f'width="{expected[0]}" height="{expected[1]}"',
                )
                url = f"https://i0.hdslb.com/emoji-{width}-{height}.png"
                self.window._chat_image_cache[url] = ("image/png", data)
                message = self.message(1) | {
                    "text": "[emoji]", "emotes": {"[emoji]": url},
                    "sticker_url": url,
                }
                self.render([message])
                text = self.chat.itemWidget(self.chat.item(0))._chat_label.text()
                self.assertIn(desktop_app._chat_image_dimensions(data, 26), text)
                self.assertIn(desktop_app._chat_image_dimensions(data, 96), text)

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

    def test_gift_effect_toggle_starts_movie_and_disables_it_immediately(self):
        self.window.gift_effects = desktop_app.QtWidgets.QCheckBox()
        self.window._show_error = Mock()
        url = "https://i0.hdslb.com/gift.gif"
        data = base64.b64decode(
            "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
        )
        self.window._chat_image_cache[url] = ("image/gif", data)
        message = self.message(1) | {
            "platform": "youtube", "type": "gift",
            "sticker_url": url, "gift_animation_url": url,
        }
        self.render([message])
        row = self.chat.itemWidget(self.chat.item(0))
        self.assertIn('<img src=', row._chat_label.text())
        self.assertFalse(row.findChildren(desktop_app.QtGui.QMovie))

        self.window.gift_effects.setChecked(True)
        self.render([message])
        row = self.chat.itemWidget(self.chat.item(0))
        movies = row.findChildren(desktop_app.QtGui.QMovie)
        self.assertEqual(len(movies), 1)
        self.assertTrue(movies[0].isValid())
        self.assertNotIn('<img src=', row._chat_label.text())

        self.window.gift_effects.setChecked(False)
        self.render([message])
        row = self.chat.itemWidget(self.chat.item(0))
        self.assertFalse(row.findChildren(desktop_app.QtGui.QMovie))
        self.assertIn('<img src=', row._chat_label.text())
        self.window._show_error.assert_not_called()

    def test_discounted_bilibili_gift_keeps_actual_and_original_prices(self):
        from src import i18n
        from src.bilibili import DanmakuListener

        self.window.i18n = desktop_app._DesktopI18n(i18n)
        message = DanmakuListener._gift_message({
            "uname": "viewer", "giftName": "Flower", "num": 2,
            "coin_type": "gold", "total_coin": 1600,
            "discount_price": 800, "price": 1000,
        })
        for language, original_label in (("en", "list"), ("zh", "原价"), ("ja", "定価")):
            with self.subTest(language=language):
                self.window._ui_language = language
                self.render([message])
                text = self.chat.itemWidget(self.chat.item(0))._chat_label.text()
                self.assertIn("¥1.6", text)
                self.assertIn(f"{original_label} ¥2", text)
                self.assertEqual(message["value"], 1.6)

    def test_missevan_price_matches_simple_app_amount_label(self):
        from src import gifts
        from src.missevan import MissEvanListener

        listener = MissEvanListener.__new__(MissEvanListener)
        listener.room_id = "123"
        listener.messages = []
        listener._admins = set()
        listener._creator_id = 0
        listener._handle({
            "room_id": 123, "type": "gift", "event": "send",
            "gift": {"name": "Flower", "num": 3, "price": 2},
            "user": {"user_id": 5, "username": "viewer"}, "oid": "gift-1",
        })
        message = listener.messages[0]
        self.render([message])
        text = self.chat.itemWidget(self.chat.item(0))._chat_label.text()
        self.assertIn(gifts.amount_label(message), text)
        self.assertIn("💎6", text)

    def test_paid_membership_price_matches_simple_app_amount_label(self):
        message = self.message(1) | {
            "type": "newSponsorEvent", "text": "Membership",
            "currency": "¥", "value": 138,
        }
        self.render([message])
        text = self.chat.itemWidget(self.chat.item(0))._chat_label.text()
        self.assertIn("¥138", text)
