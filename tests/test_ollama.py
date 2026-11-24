import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import openai
from openai.types import Model
from openai.types.chat import ChatCompletion

import test_ollama


class OllamaSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.models.list.return_value.data = [
            Model(id="example:latest", object="model", created=0, owned_by="ollama"),
        ]
        self.completion = {
            "id": "test", "object": "chat.completion", "created": 0, "model": "example:latest",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Hello!"}}],
        }
        self.client.chat.completions.create.return_value = ChatCompletion.model_validate(self.completion)
        self.client_patch = patch.object(test_ollama.openai, "OpenAI")
        self.client_mock = self.client_patch.start()
        self.client_mock.return_value.__enter__.return_value = self.client
        self.addCleanup(self.client_patch.stop)
        self.output = io.StringIO()
        self.stdout_patch = contextlib.redirect_stdout(self.output)
        self.stdout_patch.__enter__()
        self.addCleanup(self.stdout_patch.__exit__, None, None, None)

    def test_discovers_model_and_verifies_openai_chat_generation(self):
        self.assertEqual(test_ollama.check_ollama("http://127.0.0.1:11434/", None, "Hello", 30), "Hello!")
        self.client_mock.assert_called_once_with(
            base_url="http://127.0.0.1:11434/v1", api_key="ollama", timeout=30, max_retries=0,
        )
        self.client.models.list.assert_called_once_with()
        self.client.chat.completions.create.assert_called_once_with(
            model="example:latest", messages=[{"role": "user", "content": "Hello"}], stream=False,
        )
        self.assertIn("PASS:", self.output.getvalue())

    def test_accepts_v1_url_and_latest_alias_but_rejects_missing_model(self):
        test_ollama.check_ollama("http://localhost:11434/v1", "example", "Hello", 30)
        self.assertEqual(self.client_mock.call_args.kwargs["base_url"], "http://localhost:11434/v1")
        self.assertEqual(self.client.chat.completions.create.call_args.kwargs["model"], "example:latest")
        self.client.chat.completions.create.reset_mock()
        with self.assertRaisesRegex(ValueError, "not installed"):
            test_ollama.check_ollama("http://localhost:11434/v1", "missing", "Hello", 30)
        self.client.chat.completions.create.assert_not_called()

    def test_rejects_empty_or_malformed_model_list(self):
        for payload in ([], "invalid"):
            with self.subTest(payload=payload):
                self.client.models.list.return_value.data = payload
                with self.assertRaises(ValueError):
                    test_ollama.check_ollama("http://localhost:11434", None, "Hello", 30)
        self.client.chat.completions.create.assert_not_called()

    def test_rejects_incomplete_empty_or_invalid_response(self):
        for choices in (
            [],
            [{"index": 0, "finish_reason": "length", "message": {"role": "assistant", "content": "Hello"}}],
            [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": " "}}],
            [{"index": 0, "finish_reason": "stop", "message": None}],
        ):
            with self.subTest(choices=choices):
                self.completion["choices"] = choices
                self.client.chat.completions.create.return_value = ChatCompletion.model_construct(
                    **self.completion,
                ) if choices and choices[0]["message"] is None else ChatCompletion.model_validate(self.completion)
                with self.assertRaises(ValueError):
                    test_ollama.check_ollama("http://localhost:11434", None, "Hello", 30)
        self.assertNotIn("PASS:", self.output.getvalue())

    def test_cli_reports_connection_timeout_and_http_failures_without_retries(self):
        request = Mock()
        response = Mock(status_code=500, request=request)
        for error, message in (
            (openai.APIConnectionError(request=request), "Cannot connect"),
            (openai.APITimeoutError(request=request), "timed out"),
            (openai.APIStatusError("HTTP 500", response=response, body=None), "500"),
        ):
            with self.subTest(error=error), contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.client.models.list.side_effect = error
                self.client.models.list.reset_mock()
                self.assertEqual(test_ollama.main([]), 1)
                self.assertIn(message, stderr.getvalue())
                self.client.models.list.assert_called_once_with()
                self.assertEqual(self.client_mock.call_args.kwargs["max_retries"], 0)

    def test_rejects_invalid_options_before_connecting(self):
        for url, timeout in (
            ("http://localhost:11434/api", 30),
            ("http://localhost:11434", 0),
            ("http://localhost:11434", float("nan")),
        ):
            with self.subTest(url=url, timeout=timeout), self.assertRaises(ValueError):
                test_ollama.check_ollama(url, None, "Hello", timeout)
        self.client_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
