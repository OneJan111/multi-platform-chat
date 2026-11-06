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

    def test_explicit_session_configuration_does_not_change_dashboard_provider(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": '["translated"]'}}]}
        original_model = openai_compatible_translate.OPENAI_COMPATIBLE_TRANSLATE_MODEL
        with patch.object(openai_compatible_translate._session, "post", return_value=response) as post:
            result = openai_compatible_translate.translate_batch(
                ["hello"], "ja", api_base="http://localhost:1234/v1/",
                api_key="", model="session-model", background="Game stream",
                glossary="HP: health", context=("previous sentence",),
            )
        self.assertEqual(result, [("translated", "")])
        self.assertEqual(post.call_args.args[0], "http://localhost:1234/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "session-model")
        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])
        system = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("Game stream", system)
        self.assertIn("HP: health", system)
        self.assertIn("previous sentence", system)
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertEqual(openai_compatible_translate.OPENAI_COMPATIBLE_TRANSLATE_MODEL, original_model)

    def test_model_discovery_openai_and_ollama_formats(self):
        for payload in ({"data": [{"id": "Model-B"}, {"id": "model-a"}]},
                        {"models": [{"name": "Model-B"}, {"name": "model-a"}]}):
            with self.subTest(payload=payload):
                response = Mock(status_code=200)
                response.json.return_value = payload
                with patch.object(openai_compatible_translate._session, "get", return_value=response) as get:
                    self.assertEqual(openai_compatible_translate.list_models("http://localhost:1234/v1", "fixture-key"),
                                     ["model-a", "Model-B"])
                self.assertEqual(get.call_args.args[0], "http://localhost:1234/v1/models")
                self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer fixture-key")
                self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_model_discovery_ollama_fallback_and_errors(self):
        missing, found = Mock(status_code=404), Mock(status_code=200)
        found.json.return_value = {"models": [{"name": "local-model"}]}
        with patch.object(openai_compatible_translate._session, "get", side_effect=[missing, missing, found]) as get:
            self.assertEqual(openai_compatible_translate.list_models("http://localhost:11434"), ["local-model"])
        self.assertEqual(get.call_args.args[0], "http://localhost:11434/api/tags")
        for response, message in ((Mock(status_code=401), "HTTP 401"),
                                  (Mock(status_code=302), "HTTP 302"),
                                  (missing, "not supported")):
            with self.subTest(message=message), \
                 patch.object(openai_compatible_translate._session, "get", return_value=response), \
                 self.assertRaisesRegex(ValueError, message):
                openai_compatible_translate.list_models("http://localhost:1234/v1")
        response = Mock(status_code=200)
        response.json.return_value = {"data": []}
        with patch.object(openai_compatible_translate._session, "get", return_value=response), \
             self.assertRaisesRegex(ValueError, "no models"):
            openai_compatible_translate.list_models("http://localhost:1234/v1")

    def test_api_base_rejects_embedded_secrets_and_invalid_urls(self):
        for base in ("ftp://example.test", "https://key@example.test/v1",
                     "https://example.test/v1?key=fixture", "https://example.test/#secret",
                     "https://example.test:invalid", "https://exa mple.test"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                openai_compatible_translate.validate_api_base(base)


if __name__ == "__main__":
    unittest.main()
