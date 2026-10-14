import unittest
from unittest.mock import Mock, patch

from src import translate


class TranslationProviderTests(unittest.TestCase):
    def setUp(self):
        with translate._lock:
            translate._index_retry_until = 0.0

    def tearDown(self):
        with translate._lock:
            translate._index_retry_until = 0.0

    def test_google_provider_remains_default_compatible(self):
        response = Mock()
        response.json.return_value = [["你好", "en"]]
        with (
            patch.object(translate, "INDEX_TRANSLATE_API_BASE", ""),
            patch.object(translate._session, "get", return_value=response) as get,
        ):
            result = translate.translate_batch(["hello"], "zh-CN")

        self.assertEqual(result, [("你好", "en")])
        get.assert_called_once()
        response.raise_for_status.assert_called_once_with()

    def test_index_translate_is_tried_before_fallback(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '["翻译结果", "第二条"]'}}],
        }
        with (
            patch.object(translate, "INDEX_TRANSLATE_API_BASE", "https://index.example/v1"),
            patch.object(translate, "INDEX_TRANSLATE_MODEL", "TestModel"),
            patch.object(translate._session, "post", return_value=response) as post,
            patch.object(translate._session, "get") as get,
        ):
            result = translate.translate_batch(["first", "second"], "zh-CN")

        self.assertEqual(result, [("翻译结果", ""), ("第二条", "")])
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://index.example/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "TestModel")
        self.assertEqual(post.call_args.kwargs["timeout"], translate._INDEX_TIMEOUT)
        get.assert_not_called()

    def test_index_failure_falls_back_to_google(self):
        import requests

        response = Mock()
        response.json.return_value = [["翻译结果", "en"]]
        with (
            patch.object(translate, "INDEX_TRANSLATE_API_BASE", "https://index.example/v1"),
            patch.object(translate._session, "post", side_effect=requests.Timeout("slow")) as post,
            patch.object(translate._session, "get", return_value=response) as get,
        ):
            result = translate.translate_batch(["hello"], "zh-CN")
            again = translate.translate_batch(["another"], "zh-CN")

        self.assertEqual(result, [("翻译结果", "en")])
        self.assertEqual(again, [("翻译结果", "en")])
        post.assert_called_once()
        self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
