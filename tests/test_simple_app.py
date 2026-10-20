import ast
import html
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.tts import resolve_language


ROOT = Path(__file__).resolve().parents[1]


class SimpleAppConfigTests(unittest.TestCase):
    def configured_platforms(self, youtube="", bilibili="", missevan=""):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        function = next(
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "_configured_platforms"
        )
        namespace = {
            "app_config": SimpleNamespace(
                YOUTUBE_CHANNEL=youtube,
                BILIBILI_ROOM_ID=bilibili,
                MISSEVAN_ROOM_ID=missevan,
            ),
            "bili": SimpleNamespace(parse_room_id=lambda value: value if value.isdigit() else ""),
            "me": SimpleNamespace(parse_room_id=lambda value: value if value.isdigit() else ""),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        return namespace["_configured_platforms"]()

    def test_unconfigured_platforms_are_hidden(self):
        self.assertEqual(self.configured_platforms(), {})

    def test_only_configured_platforms_are_included(self):
        self.assertEqual(
            self.configured_platforms(youtube="https://youtube.com/@streamer", bilibili="12345"),
            {"youtube": "https://youtube.com/@streamer", "bilibili": "12345"},
        )

    def test_configured_but_invalid_room_ids_remain_visible_as_configuration_errors(self):
        self.assertEqual(
            self.configured_platforms(bilibili="not-a-room", missevan="67890"),
            {"bilibili": "", "missevan": "67890"},
        )

    def test_waiting_username_uses_platform_name_then_configured_value(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_source_username"
        )
        namespace = {
            "_SOURCES": {"youtube": "https://youtube.com/@streamer", "bilibili": "12345"},
            "_PLATFORM_NAMES": {"youtube": "YouTube", "bilibili": "Bilibili"},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        self.assertEqual(namespace["_source_username"]("youtube", {"channel": "Channel name"}), "Channel name")
        self.assertEqual(namespace["_source_username"]("youtube", {}), "streamer")
        self.assertEqual(namespace["_source_username"]("bilibili", {}), "12345")

    def test_page_language_maps_to_translation_language(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        functions = [
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name in {"_page_language", "_translation_target"}
        ]
        for page_language, expected in (("en", "en"), ("zh", "zh-CN"), ("ja", "ja")):
            with self.subTest(page_language=page_language):
                namespace = {
                    "st": SimpleNamespace(session_state={"simple_page_language": page_language}),
                    "app_config": SimpleNamespace(SIMPLE_PAGE_LANGUAGE="ja"),
                }
                exec(compile(ast.Module(body=functions, type_ignores=[]), "simple_app.py", "exec"), namespace)
                self.assertEqual(namespace["_translation_target"](), expected)

    def test_message_time_uses_browser_timezone(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_format_message_time"
        )
        namespace = {
            "datetime": datetime,
            "timezone": timezone,
            "ZoneInfo": ZoneInfo,
            "ZoneInfoNotFoundError": ZoneInfoNotFoundError,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        self.assertEqual(namespace["_format_message_time"]("0", "Asia/Tokyo"), "09:00:00")
        self.assertEqual(namespace["_format_message_time"]("invalid", "Asia/Tokyo"), "")

    def test_regular_chat_tts_does_not_include_author(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_queue_speech"
        )
        state = {
            "simple_tts_enabled": True,
            "simple_tts_read_gifts": True,
            "simple_tts_read_chat": True,
            "simple_tts_language": "en",
            "simple_tts_translate": False,
            "simple_translation_enabled": False,
            "simple_tts_queue": [],
            "simple_tts_pending": [],
            "simple_tts_rate": 150,
            "simple_tts_volume": 1.0,
        }
        namespace = {
            "st": SimpleNamespace(session_state=state),
            "is_paid": lambda msg: False,
            "is_gift": lambda msg: False,
            "is_emoji_only": lambda msg: False,
            "strip_emoji": lambda text, platform: text,
            "matches_language": lambda text, language: True,
            "resolve_language": resolve_language,
            "format_announcement": lambda *args: "paid announcement",
            "TTS_LANGUAGES": {"en": ("English", "English", "en-US"), "auto": ("Auto", "Auto", "en-US")},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)

        namespace["_queue_speech"]({
            "id": "chat-1",
            "type": "danmaku",
            "author": "Chat author",
            "text": "Hello everyone",
            "platform": "bilibili",
        })

        self.assertEqual(state["simple_tts_queue"][0]["text"], "Hello everyone")

    def test_gift_tts_uses_selected_language_and_announcement_format(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_queue_speech"
        )
        cases = (
            ("ja", "ja-JP", "English flower"),
            ("zh", "zh-CN", "English flower"),
            ("auto", "ja-JP", "花です"),
            ("auto", "zh-CN", "鲜花"),
            ("auto", "en-US", "Flower"),
        )
        for language, voice, text in cases:
            with self.subTest(language=language, text=text):
                state = {
                    "simple_tts_enabled": True,
                    "simple_tts_read_gifts": True,
                    "simple_tts_read_chat": True,
                    "simple_tts_language": language,
                    "simple_tts_translate": False,
                    "simple_translation_enabled": False,
                    "simple_tts_queue": [],
                    "simple_tts_pending": [],
                    "simple_tts_rate": 150,
                    "simple_tts_volume": 1.0,
                }
                announcements = []
                namespace = {
                    "st": SimpleNamespace(session_state=state),
                    "is_paid": lambda msg: True,
                    "is_gift": lambda msg: True,
                    "is_emoji_only": lambda msg: False,
                    "strip_emoji": lambda text, platform: text,
                    "matches_language": lambda text, language: True,
                    "resolve_language": resolve_language,
                    "format_announcement": lambda kind, author, text, lang: (
                        announcements.append((kind, author, text, lang)) or f"{lang} announcement"
                    ),
                    "TTS_LANGUAGES": {
                        "auto": ("Auto", "", "", ""),
                        "ja": ("Japanese", "ja", "ja-JP", ""),
                        "zh": ("Chinese", "zh-CN", "zh-CN", ""),
                        "en": ("English", "en", "en-US", ""),
                    },
                }
                exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)

                namespace["_queue_speech"]({
                    "id": "gift-1",
                    "type": "gift",
                    "author": "Gifter",
                    "text": text,
                    "platform": "missevan",
                })

                self.assertEqual(announcements, [("gift", "Gifter", text, language)])
                self.assertEqual(state["simple_tts_queue"][0]["text"], f"{language} announcement")
                self.assertEqual(state["simple_tts_queue"][0]["lang"], voice)
                self.assertTrue(state["simple_tts_queue"][0]["priority"])

    def test_profit_totals_accumulate_by_currency(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_record_profit"
        )
        state = {"simple_profit_totals": {}}
        namespace = {"st": SimpleNamespace(session_state=state)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        record = namespace["_record_profit"]

        record({"currency": "$", "value": 5})
        record({"currency": "$", "value": 2.5})
        record({"currency": "¥", "value": 500})
        record({"currency": "¥", "value": "invalid"})
        record({"currency": "€", "value": 0})

        self.assertEqual(state["simple_profit_totals"], {"$": 7.5, "¥": 500.0})

    def test_bilibili_cookie_import_verifies_saves_and_displays_username(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_import_bilibili_cookie"
        )
        state = {
            "simple_bili_cookie": "SESSDATA=secret; bili_jct=csrf",
            "simple_bili_cookie_error": "",
            "simple_bili_login_name": "",
        }
        saved = []
        namespace = {
            "st": SimpleNamespace(session_state=state),
            "bc": SimpleNamespace(
                SITES={"Bilibili": "bilibili.com"},
                CookieReadError=ValueError,
                parse_cookie_text=lambda raw, domain: {"SESSDATA": "secret", "bili_jct": "csrf"},
                verify_bilibili_login=lambda cookies: {"is_login": True, "uname": "Streamer"},
                save_bilibili_credentials=lambda cookies: saved.append(cookies),
            ),
            "_t": lambda text, **kwargs: text.format(**kwargs),
            "_SOURCES": {},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)

        namespace["_import_bilibili_cookie"]()

        self.assertEqual(state["simple_bili_login_name"], "Streamer")
        self.assertEqual(state["simple_bili_cookie"], "")
        self.assertEqual(state["simple_bili_cookie_error"], "")
        self.assertEqual(len(saved), 1)

    def test_bilibili_cookie_import_requires_sessdata(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_import_bilibili_cookie"
        )
        state = {
            "simple_bili_cookie": "bili_jct=csrf",
            "simple_bili_cookie_error": "",
            "simple_bili_login_name": "",
        }
        verified = []
        namespace = {
            "st": SimpleNamespace(session_state=state),
            "bc": SimpleNamespace(
                SITES={"Bilibili": "bilibili.com"},
                CookieReadError=ValueError,
                parse_cookie_text=lambda raw, domain: {"bili_jct": "csrf"},
                verify_bilibili_login=lambda cookies: verified.append(cookies),
            ),
            "_t": lambda text, **kwargs: text.format(**kwargs),
            "_SOURCES": {},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)

        namespace["_import_bilibili_cookie"]()

        self.assertEqual(state["simple_bili_cookie_error"], "Cookie must include SESSDATA.")
        self.assertEqual(verified, [])

    def test_responsive_feed_layout_scrolls_messages_inside_panels(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        functions = [
            node for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_feed_messages_html", "_render_feeds"}
        ]
        output = []
        state = {
            "simple_translation_enabled": False,
            "simple_profit_totals": {"$": 7.5},
            "simple_gifts": [{
                "platform": "youtube",
                "author": "Supporter",
                "text": "<script>alert(1)</script>",
            }],
            "simple_chat": [{
                "platform": "missevan",
                "author": "Viewer",
                "text": "Hello\n\n    [拼音] [bái māo]\n\n```html\n<div>chat text</div>\n```",
            }],
        }
        namespace = {
            "st": SimpleNamespace(
                session_state=state,
                context=SimpleNamespace(timezone=""),
                html=lambda content, **kwargs: output.append(content),
            ),
            "html": html,
            "_PLATFORM_NAMES": {"youtube": "YouTube", "missevan": "MissEvan"},
            "_format_message_time": lambda timestamp, browser_timezone: "",
            "tr": SimpleNamespace(),
            "_translation_target": lambda: "en",
            "_t": lambda text, **kwargs: text.format(**kwargs),
            "gift_utils": SimpleNamespace(format_amount=lambda currency, amount: f"{currency}{amount}"),
            "app_config": SimpleNamespace(RENDER_CHAT_IMAGES=True),
            "MAX_CHAT_DISPLAY": 50,
            "emotes": SimpleNamespace(text_to_html=lambda text, emote_map, sticker, caption:
                                      f'<img src="https://i.test/{emote_map[text]}">' if emote_map else html.escape(text)),
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), "simple_app.py", "exec"), namespace)
        namespace["_render_feeds"]()

        markup = output[0]
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)", markup)
        self.assertIn("@media (max-width: 768px)", markup)
        self.assertIn("grid-template-rows: minmax(0, 2fr) minmax(0, 3fr)", markup)
        self.assertIn('data-testid="stMainBlockContainer"', markup)
        self.assertIn("padding-top: 3.75rem", markup)
        self.assertIn("padding-bottom: 0", markup)
        self.assertIn("height: calc(100dvh - 3.75rem)", markup)
        self.assertIn(".simple-feeds h2.simple-feed-title", markup)
        self.assertIn("overflow-y: auto", markup)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", markup)
        self.assertIn("Hello", markup)
        self.assertIn("Hello\n\n    [拼音] [bái māo]", markup)
        self.assertIn("```html\n&lt;div&gt;chat text&lt;/div&gt;\n```", markup)
        self.assertIn("Total profit (session): $7.5", markup)

    def test_feed_uses_render_chat_images_setting_for_emotes(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_feed_messages_html"
        )
        msg = {
            "platform": "bilibili",
            "author": "Viewer",
            "text": "[smile]",
            "emotes": {"[smile]": "https://i.test/smile.png"},
        }
        namespace = {
            "st": SimpleNamespace(session_state={"simple_translation_enabled": False}),
            "html": html,
            "_PLATFORM_NAMES": {"bilibili": "Bilibili"},
            "_format_message_time": lambda timestamp, browser_timezone: "",
            "tr": SimpleNamespace(),
            "_translation_target": lambda: "en",
            "_t": lambda text, **kwargs: text.format(**kwargs),
            "app_config": SimpleNamespace(RENDER_CHAT_IMAGES=True),
            "MAX_CHAT_DISPLAY": 50,
            "emotes": SimpleNamespace(text_to_html=lambda text, emote_map, sticker, caption:
                                      f'<img src="{emote_map[text]}">' if emote_map else html.escape(text)),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)

        with self.subTest(rendering_enabled=True):
            rendered = namespace["_feed_messages_html"]([msg], "")
            self.assertIn('<img src="https://i.test/smile.png">', rendered)

        namespace["app_config"].RENDER_CHAT_IMAGES = False
        with self.subTest(rendering_enabled=False):
            rendered = namespace["_feed_messages_html"]([msg], "")
            self.assertNotIn("<img", rendered)
            self.assertIn("[smile]", rendered)

    def test_translated_feed_text_uses_blue_class(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_feed_messages_html"
        )
        namespace = {
            "st": SimpleNamespace(session_state={"simple_translation_enabled": True}),
            "html": html,
            "_PLATFORM_NAMES": {"youtube": "YouTube"},
            "_format_message_time": lambda timestamp, browser_timezone: "",
            "tr": SimpleNamespace(get_translation=lambda text, target: "Translated text"),
            "_translation_target": lambda: "en",
            "_t": lambda text, **kwargs: text.format(**kwargs),
            "app_config": SimpleNamespace(RENDER_CHAT_IMAGES=False),
            "MAX_CHAT_DISPLAY": 50,
            "emotes": SimpleNamespace(),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)

        rendered = namespace["_feed_messages_html"]([{
            "platform": "youtube",
            "author": "Viewer",
            "text": "Original text",
        }], "")

        self.assertIn('class="simple-feed-translated"', rendered)
        self.assertIn("Translated text", rendered)

    def test_chat_and_gift_render_limits_use_max_chat_display(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_feed_messages_html"
        )
        namespace = {
            "st": SimpleNamespace(session_state={"simple_translation_enabled": False}),
            "html": html,
            "_PLATFORM_NAMES": {"youtube": "YouTube"},
            "_format_message_time": lambda timestamp, browser_timezone: "",
            "tr": SimpleNamespace(),
            "_translation_target": lambda: "en",
            "_t": lambda text, **kwargs: text.format(**kwargs),
            "app_config": SimpleNamespace(RENDER_CHAT_IMAGES=False),
            "MAX_CHAT_DISPLAY": 2,
            "emotes": SimpleNamespace(),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        messages = [
            {"platform": "youtube", "author": "Viewer", "text": f"message-{n}"}
            for n in range(5)
        ]

        chat_html = namespace["_feed_messages_html"](messages, "")
        gift_html = namespace["_feed_messages_html"](messages, "")

        for rendered in (chat_html, gift_html):
            self.assertNotIn("message-0", rendered)
            self.assertNotIn("message-2", rendered)
            self.assertIn("message-3", rendered)
            self.assertIn("message-4", rendered)

    def test_waiting_status_includes_platform_icon(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_status_line"
        )
        output = []
        state = {
            "simple_yt_error": "",
            "simple_yt_channel": "channel",
            "simple_bili_listener": None,
            "simple_bili_error": "",
            "simple_me_listener": None,
            "simple_me_error": "",
            "simple_room_status": {
                "bilibili": {"live_status": 0},
                "missevan": {"live": False},
            },
        }
        platforms = {"youtube": "YouTube", "bilibili": "Bilibili", "missevan": "MissEvan"}
        namespace = {
            "st": SimpleNamespace(
                session_state=state,
                markdown=lambda content, **kwargs: output.append(content),
            ),
            "html": html,
            "_PLATFORM_NAMES": platforms,
            "_site_icon_uris": lambda: {site: f"data:image/png;base64,{site}" for site in platforms},
            "_source_username": lambda site, info: "Streamer",
            "_t": lambda text, **kwargs: text.format(**kwargs),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        for site, label in platforms.items():
            with self.subTest(site=site):
                namespace["_status_line"](site, {"live": False})
                self.assertIn(f'alt="{label}"', output[-1])
                self.assertIn("Waiting for Streamer", output[-1])
                self.assertIn("white-space:nowrap", output[-1])

    def test_live_notification_only_triggers_on_offline_to_live_transition(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_track_live_status"
        )
        state = {"simple_live_states": {}, "simple_notify_live": True}
        namespace = {
            "st": SimpleNamespace(session_state=state),
            "_PLATFORM_NAMES": {"youtube": "YouTube"},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        track = namespace["_track_live_status"]
        track("youtube", False)
        track("youtube", True, "Stream title")
        track("youtube", True, "Stream title")
        self.assertEqual(
            state["simple_live_states"]["_notifications"],
            [{"site": "YouTube", "title": "Stream title"}],
        )

    def test_live_notification_toggle_suppresses_events_when_disabled(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_track_live_status"
        )
        state = {"simple_live_states": {}, "simple_notify_live": False}
        namespace = {
            "st": SimpleNamespace(session_state=state),
            "_PLATFORM_NAMES": {"bilibili": "Bilibili"},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        namespace["_track_live_status"]("bilibili", False)
        namespace["_track_live_status"]("bilibili", True, "Room title")
        self.assertNotIn("_notifications", state["simple_live_states"])


if __name__ == "__main__":
    unittest.main()
