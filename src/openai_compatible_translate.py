"""Translation through an OpenAI-compatible chat completions API."""
from __future__ import annotations

import json
import re

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


def translate_batch(
    texts: list[str], target: str, timeout: float = 60.0
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
    headers = {"User-Agent": "StreamingDashboard/1.0"}
    if OPENAI_COMPATIBLE_TRANSLATE_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_COMPATIBLE_TRANSLATE_API_KEY}"
    response = _session.post(
        f"{OPENAI_COMPATIBLE_TRANSLATE_API_BASE}/chat/completions",
        json={
            "model": OPENAI_COMPATIBLE_TRANSLATE_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 2048,
            "stream": False,
        },
        headers=headers,
        timeout=timeout,
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
    content = response.json()["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("OpenAI-compatible provider returned a non-text translation response.")
    content = content.strip()
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[-1].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    translations = json.loads(content)
    if (
        not isinstance(translations, list)
        or len(translations) != len(texts)
        or any(not isinstance(item, str) for item in translations)
    ):
        raise ValueError(
            f"OpenAI-compatible provider returned an invalid result list for {len(texts)} inputs."
        )
    return [(translation, "") for translation in translations]
