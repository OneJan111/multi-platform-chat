import ast
import os
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
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

    def render_sidebar(
        self, selected, count=10, public_url="", host="localhost:8501",
        page_url="http://localhost:8501/", overlay_host="127.0.0.1",
    ):
        tree = ast.parse((ROOT / "simple_app.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_render_obs_overlay"
        )
        st = Mock()
        st.multiselect.return_value = selected
        st.context.headers = {"Host": host}
        st.context.url = page_url
        overlay = Mock(PORT=8502)
        namespace = {
            "st": st,
            "overlay_server": overlay,
            "_t": lambda text, **kwargs: text.format(**kwargs),
            "_SOURCES": {"youtube": "@example", "bilibili": "123", "missevan": "456"},
            "_PLATFORM_NAMES": {"youtube": "YouTube", "bilibili": "Bilibili", "missevan": "MissEvan"},
            "app_config": SimpleNamespace(
                SIMPLE_OVERLAY_COUNT=count, OVERLAY_PUBLIC_URL=public_url, OVERLAY_HOST=overlay_host,
            ),
            "urlencode": urlencode,
            "urlsplit": urlsplit,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        namespace["_render_obs_overlay"]()
        if parse_qs(urlsplit(st.code.call_args.args[0]).query).get("view") == ["overlay"]:
            overlay.ensure_started.assert_not_called()
        else:
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

    def test_cloud_link_uses_https_streamlit_address_without_overlay_port(self):
        for overlay_host in ("127.0.0.1", "0.0.0.0"):
            with self.subTest(overlay_host=overlay_host):
                _, url = self.render_sidebar(
                    ["bilibili"], host="monitor.streamlit.app",
                    page_url="https://monitor.streamlit.app/?old=setting",
                    overlay_host=overlay_host,
                )
                self.assertEqual(urlsplit(url).scheme, "https")
                self.assertEqual(urlsplit(url).netloc, "monitor.streamlit.app")
                self.assertEqual(
                    parse_qs(urlsplit(url).query),
                    {"view": ["overlay"], "bilibili": ["123"], "n": ["10"]},
                )

    def test_remote_fallback_preserves_app_path(self):
        _, url = self.render_sidebar(
            ["missevan"], host="example.org",
            page_url="https://example.org/monitor?old=setting",
        )
        self.assertEqual(urlsplit(url).path, "/monitor")
        self.assertEqual(parse_qs(urlsplit(url).query)["view"], ["overlay"])

    def test_public_url_takes_precedence_on_cloud(self):
        _, url = self.render_sidebar(
            ["youtube"], host="monitor.streamlit.app",
            page_url="https://monitor.streamlit.app/",
            public_url="https://overlay.example",
        )
        self.assertEqual(urlsplit(url).netloc, "overlay.example")
        self.assertNotIn("view", parse_qs(urlsplit(url).query))

    def test_overlay_page_renders_standalone_data_without_binding_port(self):
        tree = ast.parse((ROOT / "simple_app.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_render_overlay_page"
        )
        st = Mock()
        query = {"view": ["overlay"], "bilibili": ["123"], "n": ["10"]}
        st.query_params = MagicMock()
        st.query_params.__iter__.return_value = iter(query)
        st.query_params.get_all.side_effect = query.__getitem__
        st.fragment.side_effect = lambda **kwargs: lambda callback: callback
        overlay = Mock(_PAGE_CSS=".avatar {width:32px}")
        overlay.overlay_data.return_value = {"messages": [{"text": "hello"}]}
        overlay.render_html.return_value = "<div>hello</div>"
        namespace = {"st": st, "overlay_server": overlay}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "simple_app.py", "exec"), namespace)
        namespace["_render_overlay_page"]()
        overlay.ensure_started.assert_not_called()
        overlay.overlay_data.assert_called_once_with(query)
        st.fragment.assert_called_once_with(run_every=2)
        st.markdown.assert_any_call("<div>hello</div>", unsafe_allow_html=True)
        self.assertIn("background:transparent", st.markdown.call_args_list[0].args[0])

    def test_both_entrypoints_serve_overlay_without_monitor_controls(self):
        from streamlit.testing.v1 import AppTest
        from src import overlay_server

        for filename in ("simple_app.py", "simple_server_app.py"):
            with self.subTest(filename=filename), patch.dict(os.environ), patch.object(
                overlay_server, "overlay_data",
                return_value={"messages": [{"text": "overlay test", "author": "Alice"}]},
            ) as data, patch.object(overlay_server, "ensure_started") as start, patch(
                "src.server_chat_history.ServerChatPoller"
            ):
                app = AppTest.from_file(str(ROOT / filename))
                app.query_params.update({"view": "overlay", "bilibili": "123", "n": "10"})
                app.run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.sidebar.selectbox), 0)
                self.assertTrue(any("overlay test" in item.value for item in app.markdown))
                data.assert_called_once_with(
                    {"view": ["overlay"], "bilibili": ["123"], "n": ["10"]}
                )
                start.assert_not_called()

    def test_server_history_overlay_includes_retained_chat_and_gifts(self):
        from src import overlay_feeds, overlay_server
        from src.server_chat_history import ServerChatHistory

        history = ServerChatHistory()
        history.append_many([
            {"id": str(i), "type": "danmaku", "platform": "bilibili",
             "text": f"old chat {i}", "_simple_arrived": i, "history": True}
            for i in range(12)
        ])
        history.append_many([
            {"id": "gift", "type": "gift", "platform": "bilibili",
             "text": "old gift", "_simple_arrived": 20, "history": True},
            {"id": "other", "type": "danmaku", "platform": "missevan",
             "text": "other room", "_simple_arrived": 21},
        ])
        key = overlay_feeds.FeedKey(bilibili="123", missevan="456")
        query = {"bilibili": ["123"], "n": ["10"]}
        with patch.dict(overlay_server._STATE, {"history_sources": {}}), patch.object(
            overlay_feeds, "get"
        ) as standalone:
            overlay_server.register_history_source(
                key, lambda: overlay_server.snapshot(
                    history.chat(), False, "", lambda *_: "",
                    count=50, paid_count=50, paid_messages=history.gifts(),
                ),
            )
            server = overlay_server.OverlayServer(0, "127.0.0.1")
            try:
                for transport in (None, server):
                    data = overlay_server.overlay_data(query, transport)
                    self.assertEqual(len(data["messages"]), 10)
                    self.assertEqual(data["messages"][0]["text"], "old chat 3")
                    self.assertEqual(data["messages"][-1]["text"], "old gift")
                    self.assertEqual(data["paid"], [])
                history.append_many([{
                    "id": "new", "type": "danmaku", "platform": "bilibili",
                    "text": "new chat", "_simple_arrived": 30,
                }])
                for transport in (None, server):
                    self.assertEqual(
                        overlay_server.overlay_data(query, transport)["messages"][-1]["text"],
                        "new chat",
                    )
            finally:
                server.server_close()
            standalone.assert_not_called()


if __name__ == "__main__":
    unittest.main()
