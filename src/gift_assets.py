"""Public gift artwork catalogs and non-blocking browser gift rendering."""
from __future__ import annotations

import time
import requests

from src import emotes
from src.background_poll import BackgroundTask
from src.config import BILIBILI_LIVE_API_ORIGIN, MISSEVAN_CHATROOM_META_URL


def fetch_catalog(platform: str, room_id: str) -> dict[str, dict[str, str]]:
    if platform == "bilibili":
        from src.bili_recorder import HEADERS

        response = requests.get(
            f"{BILIBILI_LIVE_API_ORIGIN}/xlive/web-room/v1/giftPanel/giftConfig",
            params={"platform": "pc", "room_id": room_id},
            headers=HEADERS,
            timeout=(5, 10),
        )
    elif platform == "missevan":
        from src.missevan import _UA

        response = requests.get(
            MISSEVAN_CHATROOM_META_URL, params={"room_id": room_id},
            headers={"User-Agent": _UA}, timeout=(5, 10)
        )
    else:
        raise ValueError(f"Unsupported gift catalog platform: {platform}")
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"{platform} gift catalog error: {payload.get('code')}")
    if platform == "bilibili":
        entries = payload.get("data", {}).get("list", [])
    else:
        groups = payload.get("info", {}).get("gifts", [])
        if isinstance(groups, dict):
            groups = [groups]
        entries = [entry for group in groups for entry in group.get("data", [])]
    catalog = {}
    for entry in entries:
        gift_id = str(entry.get("id") if platform == "bilibili" else entry.get("gift_id"))
        icon = entry.get("img_basic") if platform == "bilibili" else entry.get("icon_url")
        animation = (
            entry.get("gif") or entry.get("webp")
            if platform == "bilibili" else entry.get("icon_active_url")
        )
        catalog[gift_id] = {
            "sticker_url": emotes.safe_chat_image_url(icon),
            "gift_animation_url": emotes.safe_chat_image_url(animation),
        }
    return catalog


class GiftArtwork:
    """Session-local, single-flight catalog lookups; never mutate shared messages."""

    def __init__(self) -> None:
        self._catalogs: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
        self._pending: dict[tuple[str, str], BackgroundTask] = {}
        self._failures: dict[tuple[str, str], float] = {}

    def resolve(self, message: dict) -> dict:
        if message.get("type") != "gift":
            return message
        result = dict(message)
        result["sticker_caption"] = True
        platform = str(message.get("platform", "")).lower()
        room_id = str(message.get("room_id") or "")
        gift_id = str(message.get("gift_id") or "")
        if platform not in ("bilibili", "missevan") or not room_id or not gift_id:
            return result
        key = platform, room_id
        task = self._pending.get(key)
        if task is not None:
            try:
                ready, catalog = task.take()
            except Exception as exc:
                self._pending.pop(key)
                self._failures[key] = time.monotonic()
                raise RuntimeError(f"{platform} gift images could not be loaded: {exc}") from exc
            if ready:
                self._pending.pop(key)
                if len(self._catalogs) >= 32:
                    self._catalogs.pop(next(iter(self._catalogs)))
                self._catalogs[key] = catalog
        if key in self._catalogs:
            for field, url in self._catalogs[key].get(gift_id, {}).items():
                if url and not result.get(field):
                    result[field] = url
        elif key not in self._pending and (
            time.monotonic() - self._failures.get(key, float("-inf")) >= 300
        ):
            if len(self._pending) >= 32:
                return result
            task = BackgroundTask()
            task.submit(lambda: fetch_catalog(*key), name="browser-gift-artwork")
            self._pending[key] = task
        return result
