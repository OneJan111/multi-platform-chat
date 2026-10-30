import ast
import os
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit


ROOT = Path(__file__).resolve().parents[1]


class SimpleObsOverlayTests(unittest.TestCase):
    def test_count_default_overrides_and_invalid_values(self):
        for value in (None, "1", "25", "50", "0", "51", "-1", "invalid"):
            env = {} if value is None else {"SIMPLE_OVERLAY_COUNT": value}
            with self.subTest(value=value), patch.dict(os.environ, env, clear=True), patch(
                "dotenv.load_dotenv"
            ):
                if value in ("0", "51", "-1", "invalid"):
                    with self.assertRaises(ValueError):
                        runpy.run_path(str(ROOT / "src" / "config.py"))
                else:
                    config = runpy.run_path(str(ROOT / "src" / "config.py"))
                    self.assertEqual(config["SIMPLE_OVERLAY_COUNT"], 10 if value is None else int(value))

    def render_sidebar(self, selected, count=10, public_url=""):
        tree = ast.parse((ROOT / "simple_app.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_render_obs_overlay"
        )
        st = Mock()
        st.multiselect.return_value = selected
        st.context.headers = {"Host": "localhost:8501"}
        overlay = Mock(PORT=8502)
        namespace = {
            "st": st,
            "overlay_server": overlay,
            "_t": lambda text, **kwargs: text.format(**kwargs),
            "_SOURCES": {"youtube": "@example", "bilibili": "123", "missevan": "456"},
            "_PLATFORM_NAMES": {"youtube": "YouTube", "bilibili": "Bilibili", "missevan": "MissEvan"},
            "app_config": SimpleNamespace(
                SIMPLE_OVERLAY_COUNT=count, OVERLAY_PUBLIC_URL=public_url, OVERLAY_HOST="127.0.0.1",
            ),
            "urlencode": urlencode,
            "urlsplit": urlsplit,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        namespace["_render_obs_overlay"]()
        overlay.ensure_started.assert_called_once()
        st.link_button.assert_called_once()
        return st, st.code.call_args.args[0]

    def test_only_all_link_with_selected_sites_and_default_limit(self):
        st, url = self.render_sidebar(["bilibili", "missevan"])
        self.assertEqual(
            parse_qs(urlsplit(url).query),
            {"bilibili": ["123"], "missevan": ["456"], "n": ["10"]},
        )
        self.assertEqual(urlsplit(url).netloc, "localhost:8502")
        self.assertEqual(urlsplit(url).path, "/overlay")
        st.caption.assert_any_call("All (Super Chats, gifts and chat together)")

    def test_configured_count_and_public_url(self):
        _, url = self.render_sidebar([], count=25, public_url="https://overlay.example")
        self.assertEqual(urlsplit(url).netloc, "overlay.example")
        self.assertEqual(
            parse_qs(urlsplit(url).query),
            {"youtube": ["@example"], "bilibili": ["123"], "missevan": ["456"], "n": ["25"]},
        )


if __name__ == "__main__":
    unittest.main()
