import ast
import html
import os
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src import chat_avatars
from src import emotes


ROOT = Path(__file__).resolve().parents[1]


class LightweightRenderingTests(unittest.TestCase):
    def test_environment_default_and_override(self):
        for value, expected in ((None, True), ("false", False), ("true", True)):
            env = {} if value is None else {"RENDER_CHAT_IMAGES": value}
            with self.subTest(value=value), patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
                self.assertEqual(
                    runpy.run_path(str(ROOT / "src" / "config.py"))["RENDER_CHAT_IMAGES"],
                    expected,
                )

    def test_disabled_preserves_escaped_text_without_images(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_message_text_html"
        )
        state = {"render_chat_images": False}
        namespace = {
            "st": SimpleNamespace(session_state=state), "html_lib": html,
            "emotes": emotes, "_chat_reading_mode": lambda: "off",
            "reading": SimpleNamespace(annotate_html=Mock(return_value="")),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
        render = namespace["_message_text_html"]
        text = "Rose x3 ¥30 [smile] <script>"
        message = {
            "emotes": {"[smile]": "https://example.com/emoji.png"},
            "sticker_url": "https://example.com/gift.png", "sticker_caption": True,
        }
        result = render(message, text)
        self.assertEqual(result, html.escape(text))
        self.assertNotIn("<img", result)
        state["render_chat_images"] = True
        self.assertIn("<img", render(message, text))

    def test_chat_avatar_uses_trusted_urls_and_falls_back_to_author_initial(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        functions = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_message_avatar_url", "_message_avatar_html"}
        ]
        pending = SimpleNamespace(done=lambda: False)
        executor = SimpleNamespace(submit=Mock(return_value=pending))
        namespace = {
            "chat_avatars": chat_avatars,
            "emotes": emotes,
            "html_lib": html,
            "bili": SimpleNamespace(get_user_avatar=Mock()),
        }
        with chat_avatars._LOCK:
            chat_avatars._CACHE.clear()
            chat_avatars._PENDING.clear()
            chat_avatars._FAILURES.clear()
        with patch.object(chat_avatars, "_EXECUTOR", executor):
            exec(compile(ast.Module(body=functions, type_ignores=[]), "app.py", "exec"), namespace)

            avatar_url = namespace["_message_avatar_url"]
            self.assertEqual(avatar_url({
                "platform": "youtube", "avatar": "https://yt3.ggpht.com/avatar",
            }), "https://yt3.ggpht.com/avatar")
            self.assertEqual(avatar_url({
                "platform": "youtube", "avatar": "https://example.com/avatar",
            }), "")
            self.assertEqual(avatar_url({
                "platform": "bilibili", "author_id": "42",
            }), "")
            executor.submit.assert_called_once()
            with chat_avatars._LOCK:
                chat_avatars._PENDING.clear()

            image = namespace["_message_avatar_html"](
                {"author": "Alice"}, "https://yt3.ggpht.com/avatar"
            )
            fallback = namespace["_message_avatar_html"]({"author": "<Alice>"}, "")
        self.assertIn('<img class="chat-avatar"', image)
        self.assertIn('title="&lt;Alice&gt;"', fallback)
        self.assertIn("&lt;", fallback)

    def test_simple_monitor_renders_trusted_user_avatar(self):
        tree = ast.parse((ROOT / "simple_app.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_feed_messages_html"
        )
        namespace = {
            "st": SimpleNamespace(session_state={"simple_translation_enabled": False}),
            "_SERVER_HISTORY_ENABLED": False,
            "MAX_CHAT_DISPLAY": 50,
            "_PLATFORM_NAMES": {"youtube": "YouTube"},
            "_format_message_time": lambda *_: "",
            "_t": lambda text, **kwargs: text,
            "_translation_target": lambda: "en",
            "chat_avatars": chat_avatars,
            "bili": SimpleNamespace(get_user_avatar=Mock()),
            "emotes": emotes,
            "gift_utils": SimpleNamespace(amount_label=Mock(return_value="")),
            "is_paid": lambda _: False,
            "is_gift": lambda _: False,
            "_feed_message_text_html": lambda _msg, text: html.escape(text),
            "html": html,
            "app_config": SimpleNamespace(RENDER_CHAT_IMAGES=True),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        rendered = namespace["_feed_messages_html"](
            [{
                "id": "message-1",
                "platform": "youtube",
                "author": "Alice",
                "avatar": "https://yt3.ggpht.com/avatar",
                "text": "hello",
            }],
            "",
        )

        self.assertIn('class="simple-feed-avatar"', rendered)
        self.assertIn('src="https://yt3.ggpht.com/avatar"', rendered)

    def test_simple_monitor_renders_bilibili_emotes_and_missevan_stickers(self):
        tree = ast.parse((ROOT / "simple_app.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_feed_messages_html"
        )
        namespace = {
            "st": SimpleNamespace(session_state={"simple_translation_enabled": False}),
            "_SERVER_HISTORY_ENABLED": False,
            "MAX_CHAT_DISPLAY": 50,
            "_PLATFORM_NAMES": {"bilibili": "Bilibili", "missevan": "MissEvan"},
            "_format_message_time": lambda *_: "",
            "_t": lambda text, **kwargs: text,
            "_translation_target": lambda: "en",
            "chat_avatars": SimpleNamespace(
                message_avatar_url=lambda *_: "",
                avatar_html=lambda *_: "",
            ),
            "bili": SimpleNamespace(get_user_avatar=Mock()),
            "emotes": emotes,
            "gift_utils": SimpleNamespace(amount_label=Mock(return_value="")),
            "is_paid": lambda _: False,
            "is_gift": lambda _: False,
            "_feed_message_text_html": lambda msg, text: emotes.text_to_html(
                text, msg.get("emotes"), msg.get("sticker_url", ""), msg.get("sticker_caption", False)
            ),
            "html": html,
            "app_config": SimpleNamespace(RENDER_CHAT_IMAGES=True),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        rendered = namespace["_feed_messages_html"](
            [
                {
                    "id": "bili-1",
                    "platform": "bilibili",
                    "author": "Alice",
                    "text": "[smile]",
                    "emotes": {"[smile]": "https://i0.hdslb.com/bfs/emote/smile.png"},
                },
                {
                    "id": "me-1",
                    "platform": "missevan",
                    "author": "Bob",
                    "text": "[sticker]",
                    "sticker_url": "https://static.maoercdn.com/sticker.png",
                },
            ],
            "",
        )

        self.assertIn('src="https://i0.hdslb.com/bfs/emote/smile.png"', rendered)
        self.assertIn('src="https://static.maoercdn.com/sticker.png"', rendered)


if __name__ == "__main__":
    unittest.main()
