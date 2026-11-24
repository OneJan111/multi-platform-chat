"""Check a local Ollama server and verify that a model generates text."""
from __future__ import annotations

import argparse
import math
import sys
import time
from urllib.parse import urlsplit

import openai
from openai.types import Model
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice


def check_ollama(base_url: str, model: str | None, prompt: str, timeout: float) -> str:
    base_url = base_url.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in ("http", "https") or not parsed.hostname
        or parsed.port == 0 or parsed.username or parsed.password
        or parsed.path not in ("", "/v1") or parsed.query or parsed.fragment
    ):
        raise ValueError("Use the Ollama API URL, e.g. http://127.0.0.1:11434/v1.")
    if not parsed.path:
        base_url += "/v1"
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be a positive, finite number of seconds.")
    if not prompt.strip():
        raise ValueError("Prompt must not be empty.")

    # Ollama requires no authentication; the SDK requires a non-empty API key.
    with openai.OpenAI(base_url=base_url, api_key="ollama", timeout=timeout, max_retries=0) as client:
        models = client.models.list()
        if not isinstance(models.data, list):
            raise ValueError("Ollama returned an invalid model list.")
        names = [
            item.id for item in models.data
            if isinstance(item, Model) and isinstance(item.id, str) and item.id.strip()
        ]
        if not names:
            raise ValueError("No models installed. Run 'ollama pull <model>' first.")
        print(f"Available models: {', '.join(names)}", flush=True)
        selected = model.strip() if model is not None else names[0]
        if selected not in names and f"{selected}:latest" in names:
            selected = f"{selected}:latest"
        if selected not in names:
            raise ValueError(f"Model '{selected}' is not installed. Use one of the models listed above.")
        print(f"Testing {selected} (first load may take a while)...", flush=True)
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=selected,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        if not isinstance(response, ChatCompletion) or not isinstance(response.choices, list):
            raise ValueError("Ollama returned an invalid generation response.")
        if not response.choices:
            raise ValueError("Ollama returned no completion choices.")
        choice = response.choices[0]
        if not isinstance(choice, Choice) or not isinstance(choice.message, ChatCompletionMessage):
            raise ValueError("Ollama returned an invalid completion choice.")
        text = choice.message.content
        if choice.finish_reason != "stop" or not isinstance(text, str) or not text.strip():
            raise ValueError("The model did not return a completed, non-empty text response.")
        print(f"PASS: {selected} generated text in {time.perf_counter() - started:.2f}s.")
        print(f"Response: {text.strip()}")
        return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--model", help="Installed model name; defaults to the first installed model.")
    parser.add_argument("--prompt", default="Say hello in one short sentence.")
    parser.add_argument("--timeout", type=float, default=120, help="Response timeout in seconds (default: 120).")
    args = parser.parse_args(argv)
    try:
        check_ollama(args.base_url, args.model, args.prompt, args.timeout)
    except openai.APITimeoutError:
        print("FAIL: Ollama timed out. Try increasing --timeout for a cold or large model.", file=sys.stderr)
        return 1
    except openai.APIConnectionError:
        print("FAIL: Cannot connect to Ollama. Start 'ollama serve' and check --base-url.", file=sys.stderr)
        return 1
    except (openai.APIError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
