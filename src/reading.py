"""Reading aids (pinyin / furigana ruby) so the streamer can read Super Chats aloud."""
from __future__ import annotations

import html
import re
from functools import lru_cache
from typing import Callable

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
    "auto": "Auto (pinyin for Chinese, furigana for Japanese)",
    "pinyin": "Pinyin",
    "hiragana": "Furigana",
    "both": "Pinyin + Furigana",
    "off": "Off",
}

_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_UNBREAKABLE_RE = re.compile(r"[0-9A-Za-z\u00c0-\u024f'\u2019]+|.", re.S)


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _ruby(base: str, reading: str) -> str:
    return f"<ruby>{_esc(base)}<rt>{_esc(reading)}</rt></ruby>"


def _pinyin_segments(text: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    for m in _HAN_RE.finditer(text):
        out.append((text[pos:m.start()], ""))
        run = m.group()
        # Convert the whole run so polyphonic characters use context (重庆 -> chóng qìng).
        readings = pinyin(run, style=Style.TONE)
        if len(readings) == len(run):
            out.extend((ch, r[0]) for ch, r in zip(run, readings))
        else:
            out.append((run, ""))
        pos = m.end()
    out.append((text[pos:], ""))
    return [s for s in out if s[0]]


def _hiragana_segments(text: str) -> list[tuple[str, str]]:
    out = []
    for seg in _kakasi.convert(text):
        orig, hira = seg["orig"], seg["hira"]
        if not _HAN_RE.search(orig) or not hira or orig == hira:
            out.append((orig, ""))
            continue
        # Keep shared kana (okurigana) outside the ruby: 見ます/みます -> <ruby>見<rt>み</rt></ruby>ます
        head = 0
        while head < min(len(orig), len(hira)) - 1 and orig[head] == hira[head]:
            head += 1
        tail = 0
        while (tail < min(len(orig), len(hira)) - head - 1
               and orig[-1 - tail] == hira[-1 - tail]):
            tail += 1
        out += [(orig[:head], ""), (orig[head:len(orig) - tail], hira[head:len(hira) - tail]),
                (orig[len(orig) - tail:], "")]
    return [s for s in out if s[0]]


def _segments_html(segs: list[tuple[str, str]]) -> str:
    return "".join(_ruby(base, rd) if rd else _esc(base) for base, rd in segs)


def _pinyin_html(text: str) -> str:
    return _segments_html(_pinyin_segments(text))


def _hiragana_html(text: str) -> str:
    return _segments_html(_hiragana_segments(text))


def has_han(text: str) -> bool:
    return bool(_HAN_RE.search(text or ""))


def with_readings(text: str, mode: str = "auto") -> str:
    """Return plain text with annotated readings in parentheses for tooltips."""
    annotated = segments(text, mode)
    if not annotated:
        return text
    return "".join(
        f"{base}（{reading}）" if reading else base
        for base, reading in annotated
    )


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


# Modes the OBS overlay offers: one reading per character ("both" would need two ruby rows).
OVERLAY_MODES = ("off", "auto", "pinyin", "hiragana")


@lru_cache(maxsize=1024)
def segments(text: str, mode: str = "auto") -> tuple[tuple[str, str], ...]:
    """`text` split into (characters, reading) pairs — reading "" where there's none — for renderers that
    build ruby themselves. Empty when there's nothing to annotate. "both" is treated as "auto"."""
    if mode == "off" or not has_han(text):
        return ()
    if mode not in ("pinyin", "hiragana"):
        mode = "hiragana" if _KANA_RE.search(text) else "pinyin"
    if mode == "pinyin" and PINYIN_OK:
        segs = _pinyin_segments(text)
    elif mode == "hiragana" and KAKASI_OK:
        segs = _hiragana_segments(text)
    else:
        return ()
    return tuple(segs) if any(rd for _, rd in segs) else ()


def ruby_html(
    text: str,
    mode: str = "auto",
    *,
    max_width: int | None = None,
    font_size: float = 13,
    measure: Callable[[str, bool], float] | None = None,
) -> str:
    """Return escaped rich text with each reading centered above its matching base text.

    `measure(text, is_reading)` returns real pixel widths; without it widths are estimated
    from `font_size`.
    """
    annotated = segments(text, mode)
    if not annotated:
        return _esc(text).replace("\n", "<br>")

    rows: list[list[tuple[str, str]]] = [[]]
    row_width = 0.0
    width_limit = max_width if max_width and max_width > 0 else None
    font_size = max(float(font_size), 1.0)

    def append_cell(base: str, reading: str) -> None:
        nonlocal row_width
        if measure is not None:
            cell_width = max(
                measure(base, False),
                measure(reading, True) if reading else 0.0,
            ) + 1
        else:
            cell_width = max(
                len(base) * font_size,
                len(reading) * font_size * 0.62,
            ) + 4
        if (
            width_limit
            and rows[-1]
            and row_width + cell_width > width_limit
        ):
            rows.append([])
            row_width = 0.0
        rows[-1].append((base, reading))
        row_width += cell_width

    for base, reading in annotated:
        if reading:
            append_cell(base, reading)
            continue
        # Latin words/numbers stay in one cell so lines don't break mid-word.
        for token in _UNBREAKABLE_RE.findall(base):
            if token == "\n":
                if rows[-1]:
                    rows.append([])
                    row_width = 0.0
            else:
                append_cell(token, "")

    rendered_rows = []
    for row in rows:
        if not row:
            continue
        reading_cells = "".join(
            f'<td align="center" valign="bottom"><small>{_esc(reading)}</small></td>'
            for _, reading in row
        )
        text_cells = "".join(
            '<td align="center">'
            f'{_esc(base).replace(" ", "&nbsp;")}'
            "</td>"
            for base, _ in row
        )
        rendered_rows.append(
            '<table cellspacing="0" cellpadding="0" border="0">'
            f"<tr>{reading_cells}</tr><tr>{text_cells}</tr>"
            "</table>"
        )

    # One table per wrapped line, so a line's columns aren't stretched to match another's.
    return "".join(rendered_rows)
