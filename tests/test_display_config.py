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

    def test_translation_display_mode_defaults_and_overrides(self):
        config_path = str(Path(__file__).resolve().parents[1] / "src" / "config.py")
        for value, expected in ((None, "immediate"), ("immediate", "immediate"), ("wait", "wait")):
            env = {} if value is None else {"CHAT_TRANSLATION_DISPLAY_MODE": value}
            with self.subTest(value=value), patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
                self.assertEqual(runpy.run_path(config_path)["CHAT_TRANSLATION_DISPLAY_MODE"], expected)

    def test_invalid_translation_display_mode_raises(self):
        config_path = str(Path(__file__).resolve().parents[1] / "src" / "config.py")
        for value in ("", "yes", "parallel"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"CHAT_TRANSLATION_DISPLAY_MODE": value}, clear=True
            ), patch("dotenv.load_dotenv"), self.assertRaises(ValueError):
                runpy.run_path(config_path)

    def test_analytics_enabled_defaults_to_false_and_can_be_enabled(self):
        config_path = str(Path(__file__).resolve().parents[1] / "src" / "config.py")
        for value, expected in ((None, False), ("true", True), (" FALSE ", False)):
            env = {} if value is None else {"ANALYTICS_ENABLED": value}
            with self.subTest(value=value), patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
                self.assertEqual(runpy.run_path(config_path)["ANALYTICS_ENABLED"], expected)

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

    def test_simple_monitor_defaults_and_overrides(self):
        config_path = str(Path(__file__).resolve().parents[1] / "src" / "config.py")
        defaults = {
            "SIMPLE_PAGE_LANGUAGE": "ja",
            "SIMPLE_TRANSLATION_ENABLED": True,
            "SIMPLE_TTS_TRANSLATE": True,
            "SIMPLE_NOTIFY_LIVE": True,
        }
        overrides = {
            "SIMPLE_PAGE_LANGUAGE": " en ",
            "SIMPLE_TRANSLATION_ENABLED": "false",
            "SIMPLE_TTS_TRANSLATE": " FALSE ",
            "SIMPLE_NOTIFY_LIVE": "false",
        }
        for env, expected in (
            ({}, defaults),
            (overrides, {**dict.fromkeys(defaults, False), "SIMPLE_PAGE_LANGUAGE": "en"}),
        ):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
                config = runpy.run_path(config_path)
                self.assertEqual({key: config[key] for key in defaults}, expected)

    def test_invalid_simple_monitor_language_raises(self):
        config_path = str(Path(__file__).resolve().parents[1] / "src" / "config.py")
        with patch.dict(os.environ, {"SIMPLE_PAGE_LANGUAGE": "invalid"}, clear=True), patch(
            "dotenv.load_dotenv"
        ), self.assertRaisesRegex(ValueError, "SIMPLE_PAGE_LANGUAGE"):
            runpy.run_path(config_path)


if __name__ == "__main__":
    unittest.main()
