import ast
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from src.background_poll import BackgroundPoll, BackgroundTask


ROOT = Path(__file__).resolve().parents[1]


def load_functions(names, namespace):
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=functions, type_ignores=[]), "app.py", "exec"), namespace)


class BrowserFeatureIsolationTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "tts_rate": 150, "tts_volume": 0.8, "_tts_translation_pending": [],
            "obs_enabled": True, "obs_chat_enabled": True,
            "obs_chat_source": "Chat", "obs_chat_last": None,
            "obs_chat_last_at": 0, "chat_messages": [],
            "translate_enabled": False, "translate_target": "en",
        }
        self.warnings = Mock()
        self.namespace = {
            "st": SimpleNamespace(
                session_state=self.state, warning=self.warnings, toast=Mock(),
            ),
            "BackgroundPoll": BackgroundPoll, "BackgroundTask": BackgroundTask,
            "time": time, "CHAT_POLL_INTERVAL": 1,
            "t": lambda text, **kwargs: text.format(**kwargs),
            "_browser_tts": lambda: False,
            "app_config": SimpleNamespace(TTS_USE_GTTS=True),
            "stop_speaking": Mock(return_value=0),
        }
        self.release = threading.Event()
        self.tasks = []

    def tearDown(self):
        self.release.set()
        for task in self.tasks:
            if task._future is not None:
                try:
                    task._future.result(timeout=2)
                except ValueError:
                    pass

    def blocked(self, value):
        if not self.release.wait(2):
            raise TimeoutError("Test did not release network operation")
        return value

    def load(self, *names):
        load_functions(set(names), self.namespace)

    def test_tts_and_obs_complete_independently_of_each_other(self):
        self.namespace["speak"] = Mock(side_effect=lambda *a, **k: self.blocked(b"audio"))
        self.namespace["obs"] = SimpleNamespace(
            set_text_source=Mock(),
            format_chat_text=lambda *a: "latest chat",
        )
        self.namespace["tr"] = SimpleNamespace(get_translation=Mock())
        self.load("_play_tts", "_take_tts_audio", "_sync_obs_chat")
        before = time.monotonic()
        self.namespace["_play_tts"]("hello", "en")
        tts_task = self.state["_tts_audio_task"]
        self.tasks.append(tts_task)
        self.namespace["_sync_obs_chat"]()
        obs_task = self.state["_obs_text_task"]
        self.tasks.append(obs_task)
        self.assertLess(time.monotonic() - before, 0.5)
        obs_task._future.result(timeout=1)
        self.namespace["_sync_obs_chat"]()
        self.assertEqual(self.state["obs_chat_last"], ("Chat", "latest chat"))
        self.assertNotIn("_tts_audio", self.state)
        self.assertFalse(self.release.is_set())
        self.release.set()
        tts_task._future.result(timeout=1)
        self.namespace["_take_tts_audio"]()
        self.assertEqual(self.state["_tts_audio"], b"audio")

    def test_stopped_tts_does_not_play_late_audio(self):
        self.namespace["speak"] = lambda *a, **k: self.blocked(b"late")
        self.load("_play_tts", "_take_tts_audio", "_stop_tts")
        self.namespace["_play_tts"]("hello", "en")
        task = self.state["_tts_audio_task"]
        self.tasks.append(task)
        self.namespace["_stop_tts"](True)
        self.release.set()
        task._future.result(timeout=1)
        self.namespace["_take_tts_audio"]()
        self.assertNotIn("_tts_audio", self.state)

    def test_tts_pending_work_is_bounded_and_failures_are_reported(self):
        self.namespace["speak"] = Mock(side_effect=lambda *a, **k: self.blocked(None))
        self.load("_play_tts", "_take_tts_audio")
        self.namespace["_play_tts"]("first", "en")
        task = self.state["_tts_audio_task"]
        self.tasks.append(task)
        self.namespace["_play_tts"]("second", "en")
        self.warnings.assert_called_with(
            "TTS audio generation is busy; try again shortly."
        )
        self.release.set()
        with self.assertRaises(RuntimeError):
            task._future.result(timeout=1)
        self.namespace["_take_tts_audio"]()
        self.assertIn("TTS audio generation failed:", self.warnings.call_args.args[0])

    def test_offline_tts_keeps_its_existing_worker(self):
        self.namespace["app_config"].TTS_USE_GTTS = False
        self.namespace["speak_async"] = Mock()
        self.load("_play_tts")
        self.namespace["_play_tts"]("hello", "en")
        self.namespace["speak_async"].assert_called_once_with(
            "hello", rate=150, volume=0.8, lang="en", priority=True,
        )
        self.assertNotIn("_tts_audio_task", self.state)

    def test_obs_text_single_flight_sends_latest_after_blocked_update(self):
        text = ["first"]
        calls = Mock(side_effect=lambda *a: self.blocked(None))
        self.namespace["obs"] = SimpleNamespace(
            set_text_source=calls,
            format_chat_text=lambda *a: text[0],
        )
        self.namespace["tr"] = SimpleNamespace(get_translation=Mock())
        self.load("_sync_obs_chat")
        self.namespace["_sync_obs_chat"]()
        task = self.state["_obs_text_task"]
        self.tasks.append(task)
        first = task._future
        text[0] = "latest"
        for _ in range(5):
            self.namespace["_sync_obs_chat"]()
        self.assertIs(task._future, first)
        self.release.set()
        first.result(timeout=1)
        self.namespace["_sync_obs_chat"]()
        task._future.result(timeout=1)
        self.namespace["_sync_obs_chat"]()
        self.assertEqual(calls.call_count, 2)
        calls.assert_called_with("Chat", "latest")
        self.assertEqual(self.state["obs_chat_last"], ("Chat", "latest"))

    def test_obs_actions_are_not_repeated_and_false_results_are_errors(self):
        self.load("_queue_obs_action", "_take_obs_action")
        operation = Mock(side_effect=lambda: self.blocked(False))
        self.namespace["_queue_obs_action"](operation)
        task = self.state["_obs_action_task"]
        self.tasks.append(task)
        self.namespace["_queue_obs_action"](operation)
        self.warnings.assert_called_with("An OBS operation is already in progress.")
        self.release.set()
        task._future.result(timeout=1)
        self.namespace["_take_obs_action"]()
        operation.assert_called_once()
        self.assertIn("OBS operation failed:", self.warnings.call_args.args[0])

    def test_obs_status_lookup_does_not_block_chat_or_other_jobs(self):
        self.namespace["obs"] = SimpleNamespace(
            get_status=lambda: self.blocked({"connected": False}),
            last_error=("unreachable", ""),
        )
        self.load("_fetch_obs_snapshot", "_obs_snapshot")
        before = time.monotonic()
        result = self.namespace["_obs_snapshot"]()
        task = self.state["_obs_status_poll"]
        self.tasks.append(task)
        self.assertLess(time.monotonic() - before, 0.5)
        self.assertFalse(result["status"]["connected"])
        independent = BackgroundTask()
        self.tasks.append(independent)
        independent.submit(lambda: "chat", name="test-chat")
        self.assertEqual(independent._future.result(timeout=1), "chat")
        self.assertFalse(self.release.is_set())
        self.release.set()
        task._future.result(timeout=1)
        self.assertEqual(
            self.namespace["_obs_snapshot"]()["error"], ("unreachable", "")
        )

    def test_simple_variants_do_not_add_unsupported_features(self):
        source = (ROOT / "simple_app.py").read_text(encoding="utf-8")
        self.assertIn("speechSynthesis", source)
        self.assertNotIn("obs_ctrl", source)
        self.assertNotIn("LiveTranscriber", source)
        wrapper = (ROOT / "simple_server_app.py").read_text(encoding="utf-8")
        self.assertIn('with_name("simple_app.py")', wrapper)

    def test_obs_and_audio_fragments_render_and_control_actions_in_streamlit(self):
        from streamlit.testing.v1 import AppTest

        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        names = {
            "_obs_controls", "_obs_snapshot", "_fetch_obs_snapshot",
            "_take_obs_action", "_queue_obs_action", "_change_obs_scene",
            "_change_obs_visibility", "_take_tts_audio", "_tts_audio_player",
        }
        functions = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name in names
        ]
        harness = """
import streamlit as st
import time
from types import SimpleNamespace
from src.background_poll import BackgroundTask, BackgroundPoll
CHAT_POLL_INTERVAL = 1
OBS_HOST, OBS_PORT = "localhost", 4455
_obs_local = True
def t(text, **kwargs):
    return text.format(**kwargs)
status = {
    "connected": True, "cpu_usage": 1, "memory_usage": 2, "fps": 60,
    "current_scene": "Scene", "streaming": False, "recording": False,
}
obs = SimpleNamespace(
    get_status=lambda: status,
    get_scenes=lambda: ["Scene"],
    get_sources=lambda scene: [{"id": 1, "name": "Camera", "visible": True}],
    get_text_sources=lambda: ["Chat"],
    last_error=("", ""),
    start_stream=lambda: True, stop_stream=lambda: True,
    start_recording=lambda: True, stop_recording=lambda: True,
    switch_scene=lambda scene: True,
    set_source_visibility=lambda *args: True,
)
for key, value in {
    "obs_enabled": True, "obs_chat_enabled": True, "obs_chat_source": "Chat",
    "obs_chat_last": None, "obs_chat_last_at": 0, "ui_lang": "en",
    "_obs_snapshot": {
        "status": status, "error": ("", ""), "scenes": ["Scene"],
        "scene": "Scene", "sources": [{"id": 1, "name": "Camera", "visible": True}],
        "text_sources": ["Chat"], "text_error": "",
    },
}.items():
    st.session_state.setdefault(key, value)
"""
        harness += "\n\n".join(ast.unparse(function) for function in functions)
        harness += "\n_obs_controls()\nwith st.sidebar:\n    _tts_audio_player()\n"
        app = AppTest.from_string(harness).run()
        self.assertFalse(app.exception, app.exception)
        button = next(button for button in app.button if button.label == "▶️ Start Stream")
        button.click().run()
        self.assertFalse(app.exception, app.exception)
        task = app.session_state["_obs_action_task"]
        self.tasks.append(task)
        if task._future is not None:
            task._future.result(timeout=1)
        app.run()
        self.assertFalse(app.exception, app.exception)
        self.assertFalse(task.busy)


if __name__ == "__main__":
    unittest.main()
