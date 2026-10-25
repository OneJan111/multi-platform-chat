"""Resolve and render trusted chat user avatars across the dashboard apps."""
from __future__ import annotations

import html
import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

_LOGGER = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CACHE: dict[str, str] = {}
_PENDING: dict[str, Future[str]] = {}
_FAILURES: dict[str, float] = {}
_EXECUTOR: ThreadPoolExecutor | None = None


def message_avatar_url(
    message: dict,
    get_bilibili_avatar: Callable[[str], str],
    safe_image_url: Callable[[str], str],
    safe_badge_url: Callable[[str], str],
) -> str:
    platform = str(message.get("platform", "")).lower()
    safe_url = safe_image_url if platform == "bilibili" else safe_badge_url
    url = safe_url(message.get("avatar", ""))
    if url or platform != "bilibili":
        return url

    uid = str(message.get("author_id", "")).strip()
    if not uid.isdigit() or int(uid) <= 0:
        return ""

    now = time.monotonic()
    with _LOCK:
        for pending_uid, future in list(_PENDING.items()):
            if not future.done():
                continue
            del _PENDING[pending_uid]
            try:
                avatar = safe_image_url(future.result())
            except Exception:
                _LOGGER.exception("Could not fetch Bilibili avatar for uid %s", pending_uid)
                avatar = ""
            if avatar:
                if len(_CACHE) >= 500:
                    _CACHE.pop(next(iter(_CACHE)))
                _CACHE[pending_uid] = avatar
                _FAILURES.pop(pending_uid, None)
            else:
                _FAILURES[pending_uid] = now

        avatar = _CACHE.get(uid)
        if avatar:
            return avatar
        if (
            uid not in _PENDING
            and now - _FAILURES.get(uid, 0) >= 300
            and len(_PENDING) < 8
        ):
            global _EXECUTOR
            if _EXECUTOR is None:
                _EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bilibili-avatar")
            _PENDING[uid] = _EXECUTOR.submit(get_bilibili_avatar, uid)
    return ""


def avatar_html(message: dict, avatar_url: str, css_class: str) -> str:
    name = str(message.get("author") or "?")
    escaped_name = html.escape(name, quote=True)
    if avatar_url:
        return (
            f'<img class="{html.escape(css_class, quote=True)}" '
            f'src="{html.escape(avatar_url, quote=True)}" alt="{escaped_name}" '
            f'title="{escaped_name}" referrerpolicy="no-referrer">'
        )
    initial = html.escape(name[:1].upper())
    return (
        f'<span class="{html.escape(css_class, quote=True)}" title="{escaped_name}">'
        f'{initial}</span>'
    )
