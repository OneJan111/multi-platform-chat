import ast
import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class DisplayConfigTests(unittest.TestCase):
    def load_config(self, value=None):
        env = {} if value is None else {"MAX_CHAT_DISPLAY": value}
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            return runpy.run_path(str(Path(__file__).resolve().parents[1] / "src" / "config.py"))

    def test_default_is_fifty(self):
        self.assertEqual(self.load_config()["MAX_CHAT_DISPLAY"], 50)

    def test_configured_value(self):
        for value in ("10", "50", "100", "200"):
            with self.subTest(value=value):
                self.assertEqual(self.load_config(value)["MAX_CHAT_DISPLAY"], int(value))

    def test_invalid_values_raise(self):
        for value in ("0", "9", "201", "1000", "invalid", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load_config(value)

    def test_transcription_uses_shared_display_limit(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_render_transcription_results"
        )
        for limit in (10, 50, 100, 200):
            with self.subTest(limit=limit):
                streamlit = Mock()
                streamlit.session_state = {"max_chat_display": limit}
                session = Mock(target_language="ja")
                session.snapshot.return_value = {
                    "status": "running",
                    "segments": [
                        {
                            "time": str(index), "original": str(index),
                            "translated": "", "translation_error": "",
                        }
                        for index in range(250)
                    ],
                }
                namespace = {
                    "st": streamlit, "t": lambda text, **kwargs: text,
                    "tr": Mock(LANGUAGES={"ja": "Japanese"}),
                    "_display_order": lambda items: items,
                }
                exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
                namespace["_render_transcription_results"](session)
                self.assertEqual(streamlit.write.call_count, limit)
                self.assertEqual(streamlit.write.call_args_list[0].args, (str(250 - limit),))


if __name__ == "__main__":
    unittest.main()
