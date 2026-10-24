import ast
import html
import os
import runpy
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
            "emotes": emotes,
            "html_lib": html,
            "logging": __import__("logging"),
            "time": __import__("time"),
            "threading": threading,
            "_AVATAR_LOCK": threading.Lock(),
            "_BILIBILI_AVATAR_CACHE": {},
            "_BILIBILI_AVATAR_PENDING": {},
            "_BILIBILI_AVATAR_FAILURES": {},
            "_bilibili_avatar_executor": lambda: executor,
            "bili": SimpleNamespace(get_user_avatar=Mock()),
        }
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

        image = namespace["_message_avatar_html"](
            {"author": "Alice"}, "https://yt3.ggpht.com/avatar"
        )
        fallback = namespace["_message_avatar_html"]({"author": "<Alice>"}, "")
        self.assertIn('<img class="chat-avatar"', image)
        self.assertIn('title="&lt;Alice&gt;"', fallback)
        self.assertIn("&lt;", fallback)


if __name__ == "__main__":
    unittest.main()
