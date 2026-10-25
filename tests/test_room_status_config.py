import ast
import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class RoomStatusConfigTests(unittest.TestCase):
    def load_interval(self, value=None):
        env = {} if value is None else {"ROOM_STATUS_POLL_INTERVAL": value}
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            return runpy.run_path(str(ROOT / "src" / "config.py"))["ROOM_STATUS_POLL_INTERVAL"]

    def test_default_and_custom_intervals(self):
        self.assertEqual(self.load_interval(), 60)
        self.assertEqual(self.load_interval("120"), 120)
        self.assertEqual(self.load_interval("1"), 1)

    def test_invalid_intervals(self):
        for value in ("0", "-1", "", "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load_interval(value)

    def test_status_and_transcription_have_no_auto_refresh_and_caches_use_interval(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        functions = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        for name in ("_stream_status", "_panel"):
            with self.subTest(function=name):
                decorators = functions[name].decorator_list
                self.assertTrue(decorators)
                self.assertTrue(
                    all(
                        not any(
                            keyword.arg == "run_every"
                            for keyword in decorator.keywords
                        )
                        for decorator in decorators
                        if isinstance(decorator, ast.Call)
                    )
                )
        for name, keyword in (
            ("_cached_video_status", "ttl"),
            ("_cached_room_info", "ttl"),
            ("_cached_me_room_info", "ttl"),
        ):
            with self.subTest(function=name):
                decorator = functions[name].decorator_list[0]
                interval = next(item.value for item in decorator.keywords if item.arg == keyword)
                self.assertEqual(interval.id, "ROOM_STATUS_POLL_INTERVAL")
        calls = {
            node.func.id for node in ast.walk(functions["_stream_status"])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("_emit_live_alerts", calls)


if __name__ == "__main__":
    unittest.main()
