import unittest

from desktop_app import _format_message_for_copy


class DesktopChatCopyTests(unittest.TestCase):
    def test_copy_format_includes_timestamp_room_author_and_message(self):
        message = {
            "timestamp": "1792321020",
            "platform": "bilibili",
            "author": "viewer",
            "text": "hello",
        }

        copied = _format_message_for_copy(message)

        self.assertIn("[BILIBILI] viewer: hello", copied)
        self.assertNotIn("1792321020", copied)

    def test_copy_format_includes_available_translation(self):
        copied = _format_message_for_copy({
            "timestamp": "",
            "platform": "youtube",
            "author": "viewer",
            "text": "hello",
            "translation": "你好",
        })

        self.assertIn("viewer: hello", copied)
        self.assertIn("Translation: 你好", copied)


if __name__ == "__main__":
    unittest.main()
