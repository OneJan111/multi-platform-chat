import ast
import html
import os
import runpy
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


if __name__ == "__main__":
    unittest.main()
