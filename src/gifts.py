"""Gift / Super Chat amounts and the gift leaderboard (top supporters)."""
from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"\d(?:[\d.,\s\u00a0\u202f]*\d)?")


def parse_amount(display: str) -> tuple[str, float]:
    """Split a displayed price like "$5.00", "CA$1,000.00", "¥500" or "5,00 €" into (currency, value).

    Returns ("", 0.0) when there is no number."""
    display = (display or "").strip()
    m = _NUMBER_RE.search(display)
    if not m:
        return "", 0.0
    raw = re.sub(r"[\s\u00a0\u202f]", "", m.group())
    seps = [i for i, c in enumerate(raw) if c in ".,"]
    if seps:
        last = seps[-1]
        decimals = len(raw) - last - 1
        # Several kinds of separator: the last one is the decimal point. One kind: a group of 3 is thousands.
        if len({raw[i] for i in seps}) > 1 or (decimals != 3 and raw.count(raw[last]) == 1):
            raw = re.sub(r"[.,]", "", raw[:last]) + "." + raw[last + 1:]
        else:
            raw = re.sub(r"[.,]", "", raw)
    currency = (display[:m.start()] + display[m.end():]).strip()
    try:
        return currency, float(raw)
    except ValueError:
        return currency, 0.0


def set_value(msg: dict, currency: str, value) -> dict:
    """Record what a paid event is worth, for the leaderboard (no value = counted but not summed)."""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0 and currency:
        msg["currency"], msg["value"] = currency, value
    else:
        msg.pop("currency", None)
        msg.pop("value", None)
    return msg


def format_amount(currency: str, value: float) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{currency}{text}"


def leaderboard(messages: list[dict], platform: str = "", top: int = 20) -> list[dict]:
    """Top supporters from paid messages, best first.

    Amounts in different currencies aren't added together: each supporter is ranked by their total in the
    currency used most on that site (then by number of gifts), and every currency's total is listed."""
    users: dict[tuple[str, str], dict] = {}
    by_currency: dict[str, int] = {}
    for m in messages:
        site = m.get("platform", "")
        if platform and site != platform:
            continue
        name = m.get("author") or ""
        key = (site, str(m.get("author_id") or "") or name)
        if not key[1]:
            continue
        row = users.setdefault(key, {"author": name, "platform": site, "count": 0, "totals": {}})
        row["author"] = name or row["author"]
        row["count"] += 1
        cur, value = m.get("currency"), m.get("value")
        if cur and value:
            row["totals"][cur] = row["totals"].get(cur, 0.0) + float(value)
            by_currency[cur] = by_currency.get(cur, 0) + 1
    main = max(by_currency, key=by_currency.get) if by_currency else ""
    rows = sorted(users.values(), key=lambda r: (r["totals"].get(main, 0.0), r["count"]), reverse=True)[:top]
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
        # The main currency first, then the others from largest.
        order = sorted(row["totals"].items(), key=lambda kv: (kv[0] != main, -kv[1]))
        row["total"] = " + ".join(format_amount(c, v) for c, v in order)
    return rows
