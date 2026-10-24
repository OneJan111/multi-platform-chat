"""Bilibili emote extraction and safe inline-image rendering."""
from __future__ import annotations

import html
import json
import re
from urllib.parse import urlsplit

_MAX_EMOTE_PX = 120


def safe_image_url(url) -> str:
    """Only allow https images from Bilibili's CDN, normalising protocol-relative URLs."""
    if not isinstance(url, str):
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not (host == "hdslb.com" or host.endswith(".hdslb.com")):
        return ""
    return url


_BADGE_HOSTS = (
    "hdslb.com", "ggpht.com", "googleusercontent.com", "maoercdn.com", "ytimg.com"
)


def safe_badge_url(url) -> str:
    """https badge and avatar images from trusted platform CDNs only."""
    if not isinstance(url, str):
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not any(host == h or host.endswith("." + h) for h in _BADGE_HOSTS):
        return ""
    return url


def safe_chat_image_url(url) -> str:
    """Emote/sticker images from Bilibili, YouTube or MissEvan CDNs."""
    return safe_image_url(url) or safe_badge_url(url)


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def parse_danmu_emotes(meta: list) -> tuple[dict[str, str], str]:
    """Return ({"[code]": url}, sticker_url) from DANMU_MSG info[0]."""
    sticker = ""
    if len(meta) > 13 and meta[12] == 1:
        sticker = safe_image_url(_as_dict(meta[13]).get("url"))
    emotes: dict[str, str] = {}
    if len(meta) > 15:
        extra = _as_dict(_as_dict(meta[15]).get("extra"))
        for code, info in (extra.get("emots") or {}).items():
            url = safe_image_url(_as_dict(info).get("url"))
            if isinstance(code, str) and code and url:
                emotes[code] = url
    return emotes, sticker


def _img(url: str, alt: str, size: str) -> str:
    return (
        f'<img src="{html.escape(url, quote=True)}" alt="{html.escape(alt, quote=True)}" '
        f'title="{html.escape(alt, quote=True)}" referrerpolicy="no-referrer" '
        f'style="height:{size};vertical-align:middle;">'
    )


def text_to_html(text: str, emotes: dict[str, str] | None = None, sticker: str = "", caption: bool = False) -> str:
    """Escape text and swap known emote codes / sticker danmaku for images.

    `caption` keeps the text next to the sticker (e.g. a Super Sticker's amount)."""
    if sticker:
        image = _img(sticker, text, f"{_MAX_EMOTE_PX}px")
        return f"{html.escape(text)}<br>{image}" if caption else image
    if not emotes:
        return html.escape(text)
    codes = sorted((c for c in emotes if c in text), key=len, reverse=True)
    if not codes:
        return html.escape(text)
    out = []
    for part in re.split("(" + "|".join(map(re.escape, codes)) + ")", text):
        out.append(_img(emotes[part], part, "1.6em") if part in emotes else html.escape(part))
    return "".join(out)
