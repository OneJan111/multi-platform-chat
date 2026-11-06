import unittest
import ast
import html
import threading
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from src import gift_assets
from src import emotes
import desktop_app


class GiftCatalogTests(unittest.TestCase):
    def test_browser_artwork_is_nonblocking_and_does_not_mutate_server_history(self):
        artwork = gift_assets.GiftArtwork()
        message = {
            "type": "gift", "platform": "bilibili", "room_id": "123",
            "gift_id": "1", "text": "Flower (actual ¥1, list ¥2)",
            "value": 1, "currency": "¥",
        }
        release = threading.Event()
        started = threading.Event()

        def fetch(*_):
            started.set()
            if not release.wait(3):
                raise TimeoutError("Catalog test not released")
            return {"1": {"sticker_url": "https://i0.hdslb.com/gift.png"}}

        with patch.object(gift_assets, "fetch_catalog", side_effect=fetch) as fetch_mock:
            try:
                first = artwork.resolve(message)
                self.assertTrue(started.wait(1))
                self.assertNotIn("sticker_url", first)
                artwork.resolve(message)
                self.assertEqual(fetch_mock.call_count, 1)
            finally:
                release.set()
                artwork._pending[("bilibili", "123")]._future.result(timeout=2)
            result = artwork.resolve(message)
        self.assertEqual(result["sticker_url"], "https://i0.hdslb.com/gift.png")
        self.assertTrue(result["sticker_caption"])
        self.assertEqual(result["value"], 1)
        self.assertEqual(result["text"], message["text"])
        self.assertNotIn("sticker_url", message)

    def test_browser_catalog_errors_are_reported_and_backed_off(self):
        artwork = gift_assets.GiftArtwork()
        message = {
            "type": "gift", "platform": "missevan", "room_id": "123", "gift_id": "2",
        }
        with patch.object(gift_assets, "fetch_catalog", side_effect=ValueError("failed")) as fetch:
            artwork.resolve(message)
            with self.assertRaises(ValueError):
                artwork._pending[("missevan", "123")]._future.result(timeout=2)
            with self.assertRaisesRegex(RuntimeError, "gift images could not be loaded"):
                artwork.resolve(message)
            artwork.resolve(message)
            self.assertEqual(fetch.call_count, 1)

    def test_browser_renderers_show_gift_images_and_preserve_price_text(self):
        root = Path(__file__).resolve().parents[1]
        for filename, names, renderer in (
            ("app.py", {"_gift_artwork_message", "_message_text_html"}, "_message_text_html"),
            ("simple_app.py", {"_feed_message_text_html"}, "_feed_message_text_html"),
        ):
            with self.subTest(filename=filename):
                artwork = gift_assets.GiftArtwork()
                artwork._catalogs[("bilibili", "123")] = {
                    "1": {"sticker_url": "https://i0.hdslb.com/gift.png"},
                }
                state = {"_gift_artwork": artwork, "render_chat_images": True}
                namespace = {
                    "st": SimpleNamespace(session_state=state, warning=Mock()),
                    "app_config": SimpleNamespace(RENDER_CHAT_IMAGES=True),
                    "html": html, "html_lib": html, "emotes": emotes,
                    "reading": SimpleNamespace(annotate_html=lambda *_: ""),
                    "_chat_reading_mode": lambda: "off",
                }
                tree = ast.parse((root / filename).read_text(encoding="utf-8"))
                module = ast.Module(body=[
                    node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name in names
                ], type_ignores=[])
                exec(compile(module, filename, "exec"), namespace)
                message = {
                    "type": "gift", "platform": "bilibili", "room_id": "123",
                    "gift_id": "1", "text": "Flower ¥1, list ¥2",
                }
                rendered = namespace[renderer](message, message["text"])
                self.assertIn("https://i0.hdslb.com/gift.png", rendered)
                self.assertIn("Flower ¥1, list ¥2", rendered)
                self.assertNotIn("sticker_url", message)
                state["render_chat_images"] = False
                namespace["app_config"].RENDER_CHAT_IMAGES = False
                self.assertNotIn("<img", namespace[renderer](message, message["text"]))

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
