"""Translation through an OpenAI-compatible chat completions API."""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

import requests

from src.config import (
    OPENAI_COMPATIBLE_TRANSLATE_API_BASE,
    OPENAI_COMPATIBLE_TRANSLATE_API_KEY,
    OPENAI_COMPATIBLE_TRANSLATE_MODEL,
)

_session = requests.Session()
_TARGET_NAMES = {
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}


class TranslationResponseError(ValueError):
    """A safe response-format error without provider content or credentials."""


def validate_api_base(base: str) -> str:
    base = base.strip().rstrip("/")
    try:
        parsed = urlsplit(base)
        valid = (parsed.scheme in ("http", "https") and parsed.hostname and parsed.port != 0
                 and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid or any(char.isspace() for char in base):
        raise ValueError("Enter a valid API base URL without credentials, query or fragment.")
    return base


def list_models(base: str, api_key: str = "") -> list[str]:
    """Discover OpenAI-compatible and Ollama model IDs without exposing credentials."""
    base = validate_api_base(base)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    candidates = [f"{base}/models"]
    if not base.endswith("/v1"):
        candidates += [f"{base}/v1/models", f"{base}/api/tags"]
    for url in candidates:
        try:
            response = _session.get(url, headers=headers, timeout=(5, 15), allow_redirects=False)
        except requests.RequestException:
            raise ValueError("Could not connect to the translation service.") from None
        if response.status_code == 404:
            continue
        if response.status_code != 200:
            raise ValueError(f"Model discovery returned HTTP {response.status_code}. Check the URL and API key.")
        try:
            payload = response.json()
        except ValueError:
            raise ValueError("The service returned an invalid model list.") from None
        items = payload.get("data") or payload.get("models") or [] if isinstance(payload, dict) else payload
        names = set()
        for item in items if isinstance(items, list) else []:
            name = (item.get("id") or item.get("name") or item.get("model")) if isinstance(item, dict) else item
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
        if names:
            return sorted(names, key=str.lower)
        raise ValueError("The service returned no models. Enter a model ID manually.")
    raise ValueError("Model discovery is not supported at this URL. Enter a model ID manually.")


def translate_batch(
    texts: list[str], target: str, timeout: float = 60.0, *,
    api_base: str | None = None, api_key: str | None = None, model: str | None = None,
    background: str = "", glossary: str = "", context: tuple[str, ...] = (),
    reasoning_effort: str = "",
) -> list[tuple[str, str]]:
    """Translate a batch; return [(translation, unknown source), ...]."""
    try:
        target_name = _TARGET_NAMES[target]
    except KeyError as exc:
        raise ValueError(f"The OpenAI-compatible provider does not support target language: {target}") from exc

    prompt = (
        f"Translate each string in the JSON array into {target_name}. "
        "Return only a JSON array of translated strings in exactly the same order and with exactly the same number "
        "of items. Preserve names, punctuation, emojis, and formatting. Do not add explanations.\n\n"
        f"{json.dumps(texts, ensure_ascii=False)}"
    )
    messages = [{"role": "user", "content": prompt}]
    if background or glossary or context:
        messages.insert(0, {"role": "system", "content": (
            "Translate only the input JSON array. Use the following as reference, not as text to translate.\n"
            f"Background: {background}\nGlossary: {glossary}\nPrevious speech: {json.dumps(context, ensure_ascii=False)}"
        )})
    headers = {"User-Agent": "StreamingDashboard/1.0"}
    key = OPENAI_COMPATIBLE_TRANSLATE_API_KEY if api_key is None else api_key
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if reasoning_effort not in ("", "none"):
        raise ValueError("Invalid translation reasoning option.")
    body = {
            "model": OPENAI_COMPATIBLE_TRANSLATE_MODEL if model is None else model,
            "messages": messages,
            "temperature": 0,
            "stream": False,
        }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    response = _session.post(
        f"{validate_api_base(api_base) if api_base is not None else OPENAI_COMPATIBLE_TRANSLATE_API_BASE}/chat/completions",
        json=body,
        headers=headers,
        timeout=timeout,
        allow_redirects=api_base is None,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            error = response.json().get("error", {})
        except (ValueError, TypeError, AttributeError):
            error = {}
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str) and message:
            if "no models loaded" in message.lower():
                message += (
                    " Ensure a model is loaded or available at the configured provider, "
                    "and set OPENAI_COMPATIBLE_TRANSLATE_MODEL to its exact model ID."
                )
            raise requests.HTTPError(
                f"OpenAI-compatible translation provider returned HTTP {response.status_code}: {message}",
                response=response,
            ) from exc
        raise
    try:
        payload = response.json()
    except ValueError:
        raise TranslationResponseError(
            "The translation endpoint returned non-JSON data. Check the API base URL; use the API endpoint, not the web page."
        ) from None
    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise TranslationResponseError(
            "The translation response is not in OpenAI chat completions format. Check the endpoint and model."
        ) from None
    length_error = (
        "The translation model output reached the token limit. Use a model with shorter output or disable reasoning."
        if choice.get("finish_reason") == "length" else ""
    )
    if not isinstance(content, str):
        raise TranslationResponseError(length_error or "OpenAI-compatible provider returned a non-text translation response.")
    content = content.strip()
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[-1].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    try:
        translations = json.loads(content)
    except ValueError:
        raise TranslationResponseError(
            length_error or "The translation model did not return a valid JSON array. Use a model that supports JSON-array output."
        ) from None
    if (
        not isinstance(translations, list)
        or len(translations) != len(texts)
        or any(not isinstance(item, str) for item in translations)
    ):
        raise TranslationResponseError(
            length_error or f"OpenAI-compatible provider returned an invalid result list for {len(texts)} inputs."
        )
    return [(translation, "") for translation in translations]
