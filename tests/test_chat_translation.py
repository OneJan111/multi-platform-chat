import ast
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


class ChatTranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8"))

    def setUp(self):
        self.state = {
            "translate_target": "zh-CN", "tts_enabled": True,
            "tts_announce_paid": True, "tts_read_chat": True,
        }
        self.lookup = Mock(return_value=None)
        self.deliver = Mock()
        self.namespace = {
            "st": SimpleNamespace(session_state=self.state),
            "tr": SimpleNamespace(get_translation=self.lookup),
            "_reads_translated": lambda msg: msg.get("type") != "gift",
            "_deliver_message_speech": self.deliver,
        }
        names = {
            "_append_chat_message", "_cap_chat_history", "_flush_chat_translation_pending",
            "_queue_message_speech", "_flush_translated_speech",
        }
        module = ast.Module(
            body=[node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name in names],
            type_ignores=[],
        )
        exec(compile(module, "app.py", "exec"), self.namespace)
        self.message = {"id": "test", "type": "danmaku", "text": "Hello", "author": "Viewer"}

    def queue(self, **kwargs):
        self.namespace["_queue_message_speech"](self.message, "Hello", "auto", False, **kwargs)

    def flush(self):
        self.namespace["_flush_translated_speech"]()

    def test_pending_translation_does_not_speak_original_and_delivers_once_when_ready(self):
        self.queue()
        self.flush()
        self.deliver.assert_not_called()
        self.assertEqual(len(self.state["_tts_translation_pending"]), 1)
        self.lookup.return_value = "你好"
        self.flush()
        self.flush()
        self.deliver.assert_called_once_with(self.message, "你好", "zh", False, False)

    def test_failed_or_same_language_translation_uses_original_after_completion(self):
        self.queue()
        self.lookup.return_value = ""
        self.flush()
        self.deliver.assert_called_once_with(self.message, "Hello", "auto", False, False)

    def test_muted_feed_discards_pending_speech(self):
        self.queue()
        self.state["tts_read_chat"] = False
        self.lookup.return_value = "你好"
        self.flush()
        self.deliver.assert_not_called()
        self.assertEqual(self.state["_tts_translation_pending"], [])

    def test_manual_replay_waits_without_requiring_automatic_tts(self):
        self.state["tts_enabled"] = False
        self.queue(manual=True)
        self.deliver.assert_not_called()
        self.lookup.return_value = "你好"
        self.flush()
        self.deliver.assert_called_once_with(self.message, "你好", "zh", False, True)

    def test_target_change_discards_old_translation(self):
        self.queue()
        self.state["translate_target"] = "ja"
        self.lookup.return_value = "你好"
        self.flush()
        self.deliver.assert_not_called()
        self.assertEqual(self.state["_tts_translation_pending"], [])

    def test_gifts_are_spoken_immediately_without_translation(self):
        self.message["type"] = "gift"
        self.namespace["_queue_message_speech"](self.message, "Gift", "en", True)
        self.lookup.assert_not_called()
        self.deliver.assert_called_once_with(self.message, "Gift", "auto", True, False)

    def test_app_never_waits_for_translation_network_results(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if ast.unparse(node.func) == "tr.prefetch":
                    self.assertFalse(any(keyword.arg == "wait" for keyword in node.keywords))

    def test_new_chat_is_stored_while_translation_is_still_pending(self):
        self.message["platform"] = "bilibili"
        listener = SimpleNamespace(pop_messages=Mock(return_value=[self.message]))
        self.state.update({
            "last_poll": 0, "selected_chat_id": "", "bili_listener": listener,
            "tts_skip_emoji": False, "tts_lang": "auto",
            "filter": SimpleNamespace(filter_messages=lambda messages: (messages, [])),
            "activity_log": [], "chat_messages": [], "paid_messages": [],
            "join_messages": [], "blocked_msgs": [], "max_chat_display": 200,
        })
        self.namespace.update({
            "time": time, "CHAT_POLL_INTERVAL": 5, "_check_watched_channel": Mock(),
            "CHAT_TRANSLATION_DISPLAY_MODE": "immediate",
            "_tts_translating": lambda: True, "is_paid": lambda message: False,
            "is_gift": lambda message: False, "_TTS_MAX_JOINS": 3,
            "hl": SimpleNamespace(MAX_LOG=1000, log_entry=lambda *args: {}),
            "_append_chat_message": lambda message: (
                self.state["paid_messages"].append(message) if message.get("type") in ("paid", "gift")
                else self.state["join_messages"].append(message) if message.get("type") == "enter"
                else self.state["chat_messages"].append(message)
            ),
            "_cap_chat_history": lambda: None,
            "_flush_chat_translation_pending": lambda: None,
        })
        self.namespace["tr"].prefetch = Mock()
        node = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == "_poll_chat")
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), self.namespace)
        self.namespace["_poll_chat"]()
        self.assertEqual(self.state["chat_messages"], [self.message])
        self.deliver.assert_not_called()
        self.assertEqual(len(self.state["_tts_translation_pending"]), 1)
        self.lookup.return_value = "你好"
        # Ready speech is processed even when no new chat poll is due.
        self.namespace["_poll_chat"]()
        self.deliver.assert_called_once_with(self.message, "你好", "zh", False, False)
        self.assertEqual(listener.pop_messages.call_count, 1)

    def test_wait_mode_hides_chat_until_translation_is_ready(self):
        self.message["platform"] = "bilibili"
        listener = SimpleNamespace(pop_messages=Mock(return_value=[self.message]))
        self.state.update({
            "last_poll": 0, "selected_chat_id": "", "bili_listener": listener,
            "tts_skip_emoji": False, "tts_lang": "auto", "translate_enabled": True,
            "filter": SimpleNamespace(filter_messages=lambda messages: (messages, [])),
            "activity_log": [], "chat_messages": [], "paid_messages": [],
            "join_messages": [], "blocked_msgs": [], "max_chat_display": 200,
            "_chat_translation_pending": [],
        })
        self.namespace.update({
            "time": time, "CHAT_POLL_INTERVAL": 5, "CHAT_TRANSLATION_DISPLAY_MODE": "wait",
            "_check_watched_channel": Mock(), "_tts_translating": lambda: True,
            "is_paid": lambda message: False, "is_gift": lambda message: False,
            "_TTS_MAX_JOINS": 3, "hl": SimpleNamespace(MAX_LOG=1000, log_entry=lambda *args: {}),
        })
        self.namespace["tr"].prefetch = Mock()
        node = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == "_poll_chat")
        helpers = [
            n for n in self.tree.body if isinstance(n, ast.FunctionDef)
            and n.name in {"_append_chat_message", "_cap_chat_history", "_flush_chat_translation_pending"}
        ]
        exec(compile(ast.Module(body=[*helpers, node], type_ignores=[]), "app.py", "exec"), self.namespace)

        self.namespace["_poll_chat"]()

        self.assertEqual(self.state["chat_messages"], [])
        self.assertEqual(len(self.state["_chat_translation_pending"]), 1)
        self.namespace["tr"].get_translation.return_value = "你好"
        self.namespace["_poll_chat"]()
        self.assertEqual(self.state["chat_messages"], [self.message])
        self.assertEqual(self.state["_chat_translation_pending"], [])
        self.assertEqual(listener.pop_messages.call_count, 1)

    def test_stop_clears_pending_translated_speech(self):
        self.queue()
        self.namespace.update({"_browser_tts": lambda: True, "t": lambda text: text})
        self.namespace["st"].toast = Mock()
        node = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == "_stop_tts")
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), self.namespace)
        self.namespace["_stop_tts"](True)
        self.lookup.return_value = "你好"
        self.flush()
        self.deliver.assert_not_called()


class ListeningHintTests(unittest.TestCase):
    def test_hint_requires_an_active_listener(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_has_active_chat_listener")
        for state, expected in (
            ({}, False),
            ({"selected_chat_id": "live-chat"}, True),
            ({"yt_watch_channel": "channel"}, False),
            ({"bili_listener": SimpleNamespace(running=True)}, True),
            ({"me_listener": SimpleNamespace(running=True)}, True),
            ({"bili_listener": SimpleNamespace(running=False)}, False),
            ({"me_listener": SimpleNamespace(running=False)}, False),
        ):
            with self.subTest(state=state):
                namespace = {"st": SimpleNamespace(session_state=state)}
                exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
                self.assertEqual(namespace["_has_active_chat_listener"](), expected)


if __name__ == "__main__":
    unittest.main()
