import unittest
from unittest.mock import Mock, patch

from src import openai_compatible_translate


class OpenAICompatibleTranslationTests(unittest.TestCase):
    def test_translates_batch_using_openai_compatible_endpoint(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '["こんにちは", "ありがとう"]'}}],
        }
        with (
            patch.object(
                openai_compatible_translate,
                "OPENAI_COMPATIBLE_TRANSLATE_API_BASE",
                "http://localhost:1234/v1",
            ),
            patch.object(openai_compatible_translate, "OPENAI_COMPATIBLE_TRANSLATE_MODEL", "loaded-model"),
            patch.object(openai_compatible_translate, "OPENAI_COMPATIBLE_TRANSLATE_API_KEY", ""),
            patch.object(openai_compatible_translate._session, "post", return_value=response) as post,
        ):
            result = openai_compatible_translate.translate_batch(["hello", "thanks"], "ja")

        self.assertEqual(result, [("こんにちは", ""), ("ありがとう", "")])
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "http://localhost:1234/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "loaded-model")
        self.assertEqual(post.call_args.kwargs["timeout"], 60.0)
        response.raise_for_status.assert_called_once_with()

    def test_includes_optional_bearer_token(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": '["翻訳"]'}}]}
        with (
            patch.object(openai_compatible_translate, "OPENAI_COMPATIBLE_TRANSLATE_API_KEY", "secret"),
            patch.object(openai_compatible_translate._session, "post", return_value=response) as post,
        ):
            openai_compatible_translate.translate_batch(["text"], "zh-CN")

        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer secret")

    def test_rejects_invalid_translation_response(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": '["only one"]'}}]}
        with (
            patch.object(openai_compatible_translate._session, "post", return_value=response),
            self.assertRaisesRegex(ValueError, "invalid result list"),
        ):
            openai_compatible_translate.translate_batch(["one", "two"], "en")

    def test_explains_when_no_model_is_loaded(self):
        import requests

        response = Mock()
        response.status_code = 400
        response.json.return_value = {
            "error": {
                "message": "No models loaded. Please load a model in the developer page.",
            },
        }
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        with (
            patch.object(openai_compatible_translate._session, "post", return_value=response),
            self.assertRaisesRegex(
                requests.HTTPError,
                "OPENAI_COMPATIBLE_TRANSLATE_MODEL to its exact model ID",
            ),
        ):
            openai_compatible_translate.translate_batch(["hello"], "ja")

    def test_accepts_fenced_json_after_thinking_output(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '<think>reasoning</think>```json\n["翻訳"]\n```'}}],
        }
        with patch.object(openai_compatible_translate._session, "post", return_value=response):
            self.assertEqual(
                openai_compatible_translate.translate_batch(["text"], "ja"),
                [("翻訳", "")],
            )


if __name__ == "__main__":
    unittest.main()
