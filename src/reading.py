"""Reading aids (pinyin / hiragana ruby) so the streamer can read Super Chats aloud."""
from __future__ import annotations

import html
import re
from functools import lru_cache

try:
    from pypinyin import Style, pinyin
    PINYIN_OK = True
except ImportError:  # pragma: no cover
    PINYIN_OK = False

try:
    import pykakasi
    _kakasi = pykakasi.kakasi()
    KAKASI_OK = True
except ImportError:  # pragma: no cover
    KAKASI_OK = False

MODES: dict[str, str] = {
    "auto": "Auto (pinyin for Chinese, hiragana for Japanese)",
    "pinyin": "Pinyin",
    "hiragana": "Hiragana",
    "both": "Pinyin + Hiragana",
    "off": "Off",
}

_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _ruby(base: str, reading: str) -> str:
    return f"<ruby>{_esc(base)}<rt>{_esc(reading)}</rt></ruby>"


def _pinyin_html(text: str) -> str:
    out, pos = [], 0
    for m in _HAN_RE.finditer(text):
        out.append(_esc(text[pos:m.start()]))
        run = m.group()
        # Convert the whole run so polyphonic characters use context (重庆 -> chóng qìng).
        readings = pinyin(run, style=Style.TONE)
        if len(readings) == len(run):
            out.extend(_ruby(ch, r[0]) for ch, r in zip(run, readings))
        else:
            out.append(_esc(run))
        pos = m.end()
    out.append(_esc(text[pos:]))
    return "".join(out)


def _hiragana_html(text: str) -> str:
    out = []
    for seg in _kakasi.convert(text):
        orig, hira = seg["orig"], seg["hira"]
        if not _HAN_RE.search(orig) or not hira or orig == hira:
            out.append(_esc(orig))
            continue
        # Keep shared kana (okurigana) outside the ruby: 見ます/みます -> <ruby>見<rt>み</rt></ruby>ます
        head = 0
        while head < min(len(orig), len(hira)) - 1 and orig[head] == hira[head]:
            head += 1
        tail = 0
        while (tail < min(len(orig), len(hira)) - head - 1
               and orig[-1 - tail] == hira[-1 - tail]):
            tail += 1
        core_o = orig[head:len(orig) - tail]
        core_h = hira[head:len(hira) - tail]
        out.append(_esc(orig[:head]) + _ruby(core_o, core_h) + _esc(orig[len(orig) - tail:]))
    return "".join(out)


def has_han(text: str) -> bool:
    return bool(_HAN_RE.search(text or ""))


@lru_cache(maxsize=512)
def annotate_html(text: str, mode: str = "auto") -> str:
    """
    Return HTML-escaped text with ruby readings. Returns "" when there's nothing to annotate
    (no Chinese characters, mode off, or the needed library is missing).
    For "both", the pinyin and hiragana versions are joined with a <br>.
    """
    if mode == "off" or not has_han(text):
        return ""
    if mode == "auto":
        mode = "hiragana" if _KANA_RE.search(text) else "pinyin"
    parts = []
    if mode in ("pinyin", "both") and PINYIN_OK:
        parts.append(_pinyin_html(text))
    if mode in ("hiragana", "both") and KAKASI_OK:
        parts.append(_hiragana_html(text))
    return "<br>".join(parts)
