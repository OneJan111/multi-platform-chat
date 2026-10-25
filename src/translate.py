"""Chat translation via Index-Translate, OpenAI-compatible APIs, or Google.

Translations run in a background thread pool and are cached, so Streamlit reruns never
block on the network: `get_translation` returns None until the result is ready.
Index-Translate falls back to Google; OpenAI-compatible API mode never falls back.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from src import slang
from src.config import (
    GOOGLE_TRANSLATE_URL,
    INDEX_TRANSLATE_API_BASE,
    INDEX_TRANSLATE_MODEL,
    TRANSLATION_PROVIDER,
)
from src import openai_compatible_translate

log = logging.getLogger(__name__)
_RETRY_AFTER = 60.0  # seconds before retrying a failed translation
_MAX_CACHE = 3000
_INDEX_TIMEOUT = 30.0
_INDEX_RETRY_AFTER = 60.0
_TARGET_NAMES = {
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}

LANGUAGES: dict[str, str] = {
    "zh-CN": "Chinese (简体中文)",
    "zh-TW": "Chinese (繁體中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
}

# (text, target) -> (translated_text, detected_source_lang)
_cache: dict[tuple[str, str], tuple[str, str]] = {}
_failed: dict[tuple[str, str], float] = {}
_pending: set[tuple[str, str]] = set()
_lock = threading.Lock()
_index_retry_until = 0.0
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="translate")
_session = requests.Session()  # keep-alive: a cold TLS connection costs ~2s
_BATCH_ITEMS = 25
_BATCH_CHARS = 600  # CJK expands ~9x when URL-encoded; keep request URLs well under limits
def _index_translate_batch(texts: list[str], target: str, timeout: float) -> list[tuple[str, str]]:
    try:
        target_name = _TARGET_NAMES[target]
    except KeyError as exc:
        raise ValueError(f"Index-Translate does not support the configured target language: {target}") from exc
    prompt = (
        f"Translate each string in the JSON array into {target_name}. "
        "Return only a JSON array of translated strings in exactly the same order and with exactly the same number "
        "of items. Preserve names, punctuation, emojis, and formatting. Do not add explanations.\n\n"
        f"{json.dumps(texts, ensure_ascii=False)}"
    )
    response = _session.post(
        f"{INDEX_TRANSLATE_API_BASE}/chat/completions",
        json={
            "model": INDEX_TRANSLATE_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 2048,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        headers={"User-Agent": "StreamingDashboard/1.0"},
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("Index-Translate returned a non-text translation response.")
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[-1].strip()
    translations = json.loads(content)
    if (not isinstance(translations, list) or len(translations) != len(texts)
            or any(not isinstance(item, str) for item in translations)):
        raise ValueError(f"Index-Translate returned an invalid result list for {len(texts)} inputs.")
    return [(translation, "") for translation in translations]


def _fallback_translate_batch(
    texts: list[str], target: str, timeout: float
) -> list[tuple[str, str]]:
    params = [("client", "dict-chrome-ex"), ("sl", "auto"), ("tl", target)]
    params += [("q", text) for text in texts]
    resp = _session.get(GOOGLE_TRANSLATE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if len(data) != len(texts):
        raise ValueError(f"expected {len(texts)} results, got {len(data)}")
    return [
        (item[0], item[1] if len(item) > 1 else "") if isinstance(item, list) else (str(item), "")
        for item in data
    ]


def translate_batch(texts: list[str], target: str, timeout: float = 10.0) -> list[tuple[str, str]]:
    """Blocking translation of several texts in one request. Returns [(translated, source_lang)]."""
    global _index_retry_until
    protected = [slang.protect(text, target) for text in texts]
    request_texts = [text for text, _ in protected]
    results = None
    if TRANSLATION_PROVIDER == "openai_compatible":
        results = openai_compatible_translate.translate_batch(request_texts, target)
    elif TRANSLATION_PROVIDER == "google":
        results = _fallback_translate_batch(request_texts, target, timeout)
    with _lock:
        try_index = (
            TRANSLATION_PROVIDER == "index"
            and INDEX_TRANSLATE_API_BASE
            and time.monotonic() >= _index_retry_until
        )
    if try_index:
        try:
            results = _index_translate_batch(request_texts, target, _INDEX_TIMEOUT)
            with _lock:
                _index_retry_until = 0.0
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
            with _lock:
                _index_retry_until = time.monotonic() + _INDEX_RETRY_AFTER
            log.warning("Index-Translate failed; falling back to Google Translate: %s", exc)
    if results is None:
        results = _fallback_translate_batch(request_texts, target, timeout)

    return [
        (slang.restore(translated, replacements), source)
        for (translated, source), (_, replacements) in zip(results, protected)
    ]


def translate(text: str, target: str, timeout: float = 10.0) -> tuple[str, str]:
    """Blocking translation. Returns (translated_text, detected_source_lang)."""
    return translate_batch([text], target, timeout)[0]


def _same_language(source: str, target: str) -> bool:
    s, t = source.lower(), target.lower()
    if s == t:
        return True
    # Google reports Chinese as "zh-CN" / "zh-TW"; treat other zh variants as different scripts.
    return s.split("-")[0] == t.split("-")[0] and not s.startswith("zh")


def _worker(keys: list[tuple[str, str]]) -> None:
    target = keys[0][1]
    try:
        results = translate_batch([k[0] for k in keys], target)
        with _lock:
            if len(_cache) + len(keys) > _MAX_CACHE:
                for k in list(_cache)[: _MAX_CACHE // 4]:
                    del _cache[k]
            for key, res in zip(keys, results):
                _cache[key] = res
                _failed.pop(key, None)
    except Exception:
        with _lock:
            now = time.time()
            for key in keys:
                _failed[key] = now
        log.exception("Translation failed using the configured translation provider.")
    finally:
        with _lock:
            _pending.difference_update(keys)


def _lookup(key: tuple[str, str]) -> str | None:
    """Cached result under _lock: translated text, "" (hide), or None (not available)."""
    hit = _cache.get(key)
    if hit is not None:
        text, target = key
        translated, source = hit
        if _same_language(source, target) or translated.strip().lower() == text.lower():
            return ""
        return translated
    if key in _pending:
        return None
    failed_at = _failed.get(key)
    if failed_at and time.time() - failed_at < _RETRY_AFTER:
        return ""
    return None


def _needs_fetch(key: tuple[str, str]) -> bool:
    if key in _cache or key in _pending:
        return False
    failed_at = _failed.get(key)
    return not (failed_at and time.time() - failed_at < _RETRY_AFTER)


def prefetch(texts: list[str], target: str, wait: float = 0.0) -> None:
    """Queue batched translations; optionally wait up to `wait` seconds for them to finish."""
    keys = list(dict.fromkeys(((t or "").strip(), target) for t in texts if (t or "").strip()))
    with _lock:
        todo = [k for k in keys if _needs_fetch(k)]
        _pending.update(todo)
    batch: list[tuple[str, str]] = []
    chars = 0
    for key in todo:
        if batch and (len(batch) >= _BATCH_ITEMS or chars + len(key[0]) > _BATCH_CHARS):
            _pool.submit(_worker, batch)
            batch, chars = [], 0
        batch.append(key)
        chars += len(key[0])
    if batch:
        _pool.submit(_worker, batch)

    deadline = time.time() + wait
    while time.time() < deadline:
        with _lock:
            if not any(k in _pending for k in keys):
                return
        time.sleep(0.05)


def get_translation(text: str, target: str) -> str | None:
    """
    Non-blocking lookup. Returns:
    - the translated text when ready,
    - "" when no translation should be shown (empty text, already in target language),
    - None while the translation is pending.
    Failed lookups return "" and are retried after _RETRY_AFTER seconds.
    """
    text = (text or "").strip()
    if not text or not target:
        return ""
    key = (text, target)
    with _lock:
        fetch = _needs_fetch(key)
        result = _lookup(key)
    if fetch:
        prefetch([text], target)
    return result
