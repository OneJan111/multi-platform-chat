import unittest
from unittest.mock import MagicMock, patch

from src import obs_ctrl


class ObsChatTests(unittest.TestCase):
    def test_format_last_ten_chat_text_only(self):
        messages = [{"type": "danmaku", "text": f"chat {i}"} for i in range(12)]
        messages += [{"type": "gift", "text": "gift"}, {"type": "superchat", "text": "paid"}]
        translate = MagicMock(return_value="translated")

        self.assertEqual(
            obs_ctrl.format_chat_text(messages, False, "en", translate),
            "\n".join(f"chat {i}" for i in range(2, 12)),
        )
        translate.assert_not_called()

    def test_translation_only_when_available_and_enabled(self):
        messages = [
            {"type": "textMessageEvent", "text": "你好"},
            {"type": "danmaku", "text": "hello"},
            {"type": "danmaku", "text": "pending"},
        ]
        translations = {"你好": "Hello", "hello": "", "pending": None}
        self.assertEqual(
            obs_ctrl.format_chat_text(messages, True, "en", lambda text, _: translations[text]),
            "你好\nHello\nhello\npending",
        )
        self.assertEqual(
            obs_ctrl.format_chat_text(messages, False, "en", lambda *_: self.fail("translation requested")),
            "你好\nhello\npending",
        )

    def test_usernames_prefix_messages_when_enabled(self):
        messages = [
            {"type": "danmaku", "text": "你好", "author": "Alice"},
            {"type": "danmaku", "text": "hi", "author": ""},
        ]
        self.assertEqual(
            obs_ctrl.format_chat_text(messages, True, "en", lambda text, _: {"你好": "Hello"}.get(text), show_names=True),
            "Alice: 你好\nHello\nhi",
        )
        self.assertEqual(obs_ctrl.format_chat_text(messages, False, "en", lambda *_: None), "你好\nhi")

    @patch.object(obs_ctrl, "_client")
    def test_text_source_updates_only_text_setting(self, client):
        obs_ctrl.set_text_source("Chat", "line 1\nline 2")
        client.return_value.set_input_settings.assert_called_once_with(
            "Chat", {"text": "line 1\nline 2"}, True,
        )
        client.return_value.disconnect.assert_called_once()

    @patch.object(obs_ctrl, "_client")
    def test_only_text_inputs_are_selectable(self, client):
        client.return_value.get_input_list.return_value.inputs = [
            {"inputName": "Chat", "inputKind": "text_gdiplus_v2"},
            {"inputName": "Camera", "inputKind": "dshow_input"},
            {"inputName": "Captions", "inputKind": "text_ft2_source_v2"},
        ]
        self.assertEqual(obs_ctrl.get_text_sources(), ["Chat", "Captions"])


if __name__ == "__main__":
    unittest.main()
