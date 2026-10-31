import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from src import gift_assets
import desktop_app


class GiftCatalogTests(unittest.TestCase):
    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_desktop_catalog_lookup_enriches_gifts_and_deduplicates_requests(self):
        app = desktop_app.QtWidgets.QApplication.instance()
        if app is None:
            app = desktop_app.QtWidgets.QApplication([])
        message = {
            "type": "gift", "platform": "missevan", "room_id": "456", "gift_id": "2",
        }
        icon = "https://static.maoercdn.com/icon.png"
        animation = "https://static.maoercdn.com/active.webp"
        window = SimpleNamespace(
            _paid=[message], _chat_image_cache={icon: ("image/png", b"image")},
            _chat_images_pending=set(), _bilibili_avatar_cache={},
            gift_effects=desktop_app.QtWidgets.QCheckBox(),
            _refresh_feeds=Mock(),
        )
        window._queue_chat_images = lambda messages: (
            desktop_app._DesktopWindow._queue_chat_images(window, messages)
        )

        def run_task(function, callback, *, on_finished):
            result = function()
            on_finished()
            callback(result)

        window._run_task = Mock(side_effect=run_task)
        with patch.object(gift_assets, "fetch_catalog", return_value={
            "2": {"sticker_url": icon, "gift_animation_url": animation},
        }) as fetch:
            window._queue_chat_images([message])
            window._queue_chat_images([message])
        fetch.assert_called_once_with("missevan", "456")
        self.assertEqual(message["sticker_url"], icon)
        self.assertEqual(message["gift_animation_url"], animation)
        self.assertFalse(window._gift_catalog_pending)

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_gift_effect_choice_persists(self):
        app = desktop_app.QtWidgets.QApplication.instance()
        if app is None:
            app = desktop_app.QtWidgets.QApplication([])
        settings = Mock()
        settings.value.side_effect = lambda key, default, **kwargs: (
            True if key == "gift_effects" else default
        )
        window = SimpleNamespace(_settings=settings)
        toggle = desktop_app.QtWidgets.QCheckBox()
        desktop_app._DesktopWindow._persist_widget(window, toggle, "gift_effects")
        self.assertTrue(toggle.isChecked())
        toggle.setChecked(False)
        settings.setValue.assert_called_with("gift_effects", False)

    def test_bilibili_catalog_selects_gif_and_safe_icon(self):
        response = Mock()
        response.json.return_value = {"code": 0, "data": {"list": [{
            "id": 1, "img_basic": "https://i0.hdslb.com/icon.png",
            "gif": "https://i0.hdslb.com/effect.gif",
            "webp": "https://i0.hdslb.com/effect.webp",
        }]}}
        with patch.object(gift_assets.requests, "get", return_value=response):
            catalog = gift_assets.fetch_catalog("bilibili", "123")
        self.assertEqual(catalog["1"]["sticker_url"], "https://i0.hdslb.com/icon.png")
        self.assertEqual(catalog["1"]["gift_animation_url"], "https://i0.hdslb.com/effect.gif")

    def test_missevan_catalog_selects_webp_not_svga(self):
        response = Mock()
        response.json.return_value = {"code": 0, "info": {"gifts": [{"data": [{
            "gift_id": 2, "icon_url": "https://static.maoercdn.com/icon.png",
            "icon_active_url": "https://static.maoercdn.com/active.webp",
            "web_combo_effect_url": "https://static.maoercdn.com/combo.svga",
        }]}]}}
        with patch.object(gift_assets.requests, "get", return_value=response):
            catalog = gift_assets.fetch_catalog("missevan", "456")
        self.assertEqual(
            catalog["2"]["gift_animation_url"], "https://static.maoercdn.com/active.webp"
        )

    def test_catalog_rejects_untrusted_asset_hosts_and_reports_api_errors(self):
        response = Mock()
        response.json.return_value = {"code": 0, "data": {"list": [{
            "id": 1, "img_basic": "https://evil.example/icon.png",
            "gif": "https://evil.example/effect.gif",
        }]}}
        with patch.object(gift_assets.requests, "get", return_value=response):
            self.assertEqual(gift_assets.fetch_catalog("bilibili", "1")["1"], {
                "sticker_url": "", "gift_animation_url": "",
            })
            response.json.return_value = {"code": -1}
            with self.assertRaisesRegex(RuntimeError, "gift catalog error"):
                gift_assets.fetch_catalog("bilibili", "1")
