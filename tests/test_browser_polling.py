import ast
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src import user_login
from src.background_poll import BackgroundPoll


ROOT = Path(__file__).resolve().parents[1]


def load_functions(filename, names, namespace):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=functions, type_ignores=[]), filename, "exec"), namespace)


class BackgroundPollTests(unittest.TestCase):
    def test_single_flight_and_login_context_are_session_local(self):
        started = threading.Event()
        release = threading.Event()
        poller = BackgroundPoll()

        def fetch():
            started.set()
            if not release.wait(2):
                raise TimeoutError("Test did not release request")
            return user_login.current()

        logins = {"youtube_page_id": "test-page"}
        try:
            with user_login.using(logins):
                self.assertEqual(poller.poll("source", 1, fetch), (False, None))
            self.assertTrue(started.wait(1))
            future = poller._future
            logins["youtube_page_id"] = "changed"
            for _ in range(10):
                self.assertEqual(poller.poll("source", 1, fetch), (False, None))
            self.assertIs(poller._future, future)
        finally:
            release.set()
            future.result(timeout=2)
        self.assertEqual(
            poller.poll("source", 1, fetch),
            (True, {"youtube_page_id": "test-page"}),
        )

    def test_stale_results_are_discarded_and_errors_are_visible(self):
        poller = BackgroundPoll()
        poller.poll("old-source", 0, lambda: "old")
        poller._future.result(timeout=2)
        self.assertEqual(
            poller.poll("new-source", 0, lambda: "new"), (False, None)
        )
        poller._future.result(timeout=2)
        self.assertEqual(
            poller.poll("new-source", 0, lambda: "unused"), (True, "new")
        )
        poller.poll("error", 0, Mock(side_effect=ValueError("request failed")))
        with self.assertRaisesRegex(ValueError, "request failed"):
            poller._future.result(timeout=2)
        with self.assertRaisesRegex(ValueError, "request failed"):
            poller.poll("error", 0, lambda: "unused")

    def test_interval_is_start_to_start_not_request_duration_plus_interval(self):
        poller = BackgroundPoll()
        with patch("src.background_poll.time.monotonic", return_value=100):
            poller.poll("source", 2, lambda: "first")
            poller._future.result(timeout=2)
            self.assertEqual(poller.poll("source", 2, lambda: None), (True, "first"))
            self.assertEqual(poller.poll("source", 2, lambda: None), (False, None))
            self.assertIsNone(poller._future)
        with patch("src.background_poll.time.monotonic", return_value=103):
            poller.poll("source", 2, lambda: "next")
            self.assertEqual(poller._future.result(timeout=2), "next")

    def test_disconnect_discards_pending_results_even_for_the_same_source(self):
        poller = BackgroundPoll()
        poller.poll("source", 0, lambda: "old")
        poller._future.result(timeout=2)
        poller.invalidate()
        self.assertEqual(
            poller.poll("source", 0, lambda: "fresh"), (False, None)
        )
        poller._future.result(timeout=2)
        self.assertEqual(
            poller.poll("source", 0, lambda: "unused"), (True, "fresh")
        )


class BrowserChatDeliveryTests(unittest.TestCase):
    def test_main_dashboard_drains_chat_while_youtube_chat_is_blocked(self):
        state = {
            "last_poll": 0, "selected_chat_id": "chat", "yt_page_token": "",
            "tts_enabled": False, "translate_target": "en", "translate_enabled": False,
            "activity_log": [], "blocked_msgs": [],
            "filter": SimpleNamespace(filter_messages=lambda msgs: (msgs, [])),
            "bili_listener": SimpleNamespace(
                pop_messages=Mock(side_effect=[[{"id": "bili"}], []])
            ),
            "me_listener": SimpleNamespace(
                pop_messages=Mock(side_effect=[[{"id": "me"}], []])
            ),
        }
        stored = []
        namespace = {
            "st": SimpleNamespace(session_state=state),
            "time": time, "BackgroundPoll": BackgroundPoll, "CHAT_POLL_INTERVAL": 1,
            "_flush_translated_speech": Mock(), "_flush_chat_translation_pending": Mock(),
            "_check_watched_channel": Mock(),
            "_append_chat_message": stored.append, "_cap_chat_history": Mock(),
            "app_config": SimpleNamespace(ANALYTICS_ENABLED=False),
            "CHAT_TRANSLATION_DISPLAY_MODE": "immediate",
        }
        started, release = threading.Event(), threading.Event()

        def fetch(*args):
            started.set()
            if not release.wait(2):
                raise TimeoutError("Test did not release YouTube")
            return [{"id": "youtube"}], "next", 1000

        namespace["yt"] = SimpleNamespace(get_chat_messages=fetch)
        load_functions("app.py", {"_poll_chat"}, namespace)
        before = time.monotonic()
        try:
            namespace["_poll_chat"]()
            self.assertLess(time.monotonic() - before, 0.5)
            self.assertTrue(started.wait(1))
            self.assertEqual([msg["id"] for msg in stored], ["bili", "me"])
        finally:
            release.set()
            state["_yt_chat_poll"]._future.result(timeout=2)
        namespace["_poll_chat"]()
        self.assertEqual(state["yt_page_token"], "next")
        self.assertEqual(stored[-1]["id"], "youtube")

    def test_simple_app_drains_chat_while_youtube_chat_is_blocked(self):
        state = {
            "simple_last_poll": 0, "simple_yt_video_id": "video",
            "simple_yt_chat_id": "chat", "simple_yt_page_token": "",
            "simple_yt_backlog_loaded": False, "simple_translation_enabled": False,
            "simple_bili_listener": SimpleNamespace(pop_messages=lambda: [{"id": "bili"}]),
            "simple_me_listener": SimpleNamespace(pop_messages=lambda: [{"id": "me"}]),
        }
        accepted = Mock()
        namespace = {
            "st": SimpleNamespace(session_state=state), "time": time,
            "BackgroundPoll": BackgroundPoll, "SIMPLE_CHAT_POLL_INTERVAL": 1,
            "_SERVER_HISTORY_ENABLED": False, "_accept_messages": accepted,
            "_flush_tts_pending": Mock(),
        }
        release = threading.Event()

        def fetch(*args):
            if not release.wait(2):
                raise TimeoutError("Test did not release YouTube")
            return [{"id": "youtube"}], "next", 1000

        namespace["yt"] = SimpleNamespace(get_chat_messages=fetch)
        load_functions("simple_app.py", {"_poll_messages"}, namespace)
        before = time.monotonic()
        try:
            namespace["_poll_messages"]()
            self.assertLess(time.monotonic() - before, 0.5)
            self.assertEqual(accepted.call_count, 2)
            self.assertEqual(accepted.call_args_list[0].args[0], [{"id": "bili"}])
        finally:
            release.set()
            state["_simple_yt_chat_poll"]._future.result(timeout=2)
        namespace["_poll_messages"]()
        accepted.assert_any_call([{"id": "youtube"}], is_backlog=True)
        self.assertTrue(state["simple_yt_backlog_loaded"])
        self.assertEqual(state["simple_yt_page_token"], "next")

    def test_simple_status_requests_do_not_block_script_thread(self):
        state = {
            "simple_yt_channel": "", "simple_yt_video_id": "video",
            "simple_yt_chat_id": "", "simple_room_status": {},
        }
        release = threading.Event()

        def fetch(*args):
            if not release.wait(2):
                raise TimeoutError("Test did not release status")
            return {}

        namespace = {
            "st": SimpleNamespace(session_state=state), "time": time,
            "BackgroundPoll": BackgroundPoll, "_STATUS_INTERVAL": 60,
            "_SOURCES": {"bilibili": "123", "missevan": "456"},
            "yt": SimpleNamespace(get_video_live_status=fetch),
            "bili": SimpleNamespace(get_room_info=fetch),
            "me": SimpleNamespace(get_room_info=fetch),
        }
        load_functions("simple_app.py", {
            "_refresh_youtube", "_fetch_youtube_status", "_refresh_room_status",
        }, namespace)
        before = time.monotonic()
        try:
            namespace["_refresh_youtube"]()
            namespace["_refresh_room_status"]()
            self.assertLess(time.monotonic() - before, 0.5)
            self.assertEqual(state["simple_room_status"], {})
        finally:
            release.set()
            for key, poller in list(state.items()):
                if key.endswith("_poll"):
                    poller._future.result(timeout=2)

    def test_main_channel_watch_does_not_block_chat_or_attach_stale_stream(self):
        state = {
            "yt_watch_channel": "old-channel", "yt_live_video": "",
            "selected_chat_id": "", "yt_watch_last": 0,
        }
        release = threading.Event()

        def find(channel):
            if not release.wait(2):
                raise TimeoutError("Test did not release channel lookup")
            return {"live": True, "video_id": "old-video"}

        namespace = {
            "st": SimpleNamespace(session_state=state),
            "BackgroundPoll": BackgroundPoll, "time": time, "YT_WATCH_INTERVAL": 0,
            "ytw": SimpleNamespace(find_live_video=find),
            "yt": SimpleNamespace(resolve_live_chat_id=lambda _: ("old-chat", "")),
        }
        load_functions("app.py", {
            "_check_watched_channel", "_fetch_watched_channel",
        }, namespace)
        before = time.monotonic()
        try:
            namespace["_check_watched_channel"]()
            self.assertLess(time.monotonic() - before, 0.5)
        finally:
            release.set()
            state["_yt_watch_poll"]._future.result(timeout=2)
        state["yt_watch_channel"] = "new-channel"
        namespace["_check_watched_channel"]()
        state["_yt_watch_poll"]._future.result(timeout=2)
        self.assertEqual(state["selected_chat_id"], "")

    def test_forced_channel_watch_applies_result_without_live_alert(self):
        state = {
            "yt_watch_channel": "channel", "yt_live_video": "",
            "selected_chat_id": "", "yt_watch_last": 0, "live_notify": True,
        }
        toast, alert = Mock(), Mock()
        namespace = {
            "st": SimpleNamespace(session_state=state, toast=toast),
            "BackgroundPoll": BackgroundPoll, "time": time, "YT_WATCH_INTERVAL": 60,
            "ytw": SimpleNamespace(find_live_video=lambda _: {
                "live": True, "video_id": "video", "channel": "Channel",
            }),
            "yt": SimpleNamespace(resolve_live_chat_id=lambda _: ("chat", "")),
            "t": lambda text, **kwargs: text.format(**kwargs),
            "_alert_live": alert,
        }
        load_functions("app.py", {
            "_check_watched_channel", "_fetch_watched_channel",
        }, namespace)
        namespace["_check_watched_channel"](force=True)
        state["_yt_watch_poll"]._future.result(timeout=2)
        namespace["_check_watched_channel"]()
        self.assertEqual(state["selected_chat_id"], "chat")
        self.assertEqual(state["yt_live_video"], "video")
        self.assertEqual(state["yt_page_token"], "")
        toast.assert_called_once()
        alert.assert_not_called()
