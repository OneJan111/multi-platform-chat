"""Public gift artwork catalogs for desktop gift rendering."""
from __future__ import annotations

import requests

from src import emotes
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
