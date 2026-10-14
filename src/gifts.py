"""Gift / Super Chat amounts and the gift leaderboard (top supporters)."""
from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"\d(?:[\d.,\s\u00a0\u202f]*\d)?")
_SUPER_CHAT_TYPES = {"superChatEvent", "superStickerEvent", "superchat"}


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


def amount_totals(messages: list[dict]) -> dict[str, float]:
    """Sum known gift and Super Chat amounts separately by currency."""
    totals: dict[str, float] = {}
    for msg in messages:
        if msg.get("type") != "gift" and msg.get("type") not in _SUPER_CHAT_TYPES:
            continue
        currency, value = msg.get("currency"), msg.get("value")
        if not currency or not value:
            continue
        try:
            amount = float(value)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            totals[currency] = totals.get(currency, 0.0) + amount
    return totals


def gift_price_label(message: dict) -> str:
    """Return the known gift amount unless the message text already displays it."""
    if message.get("type") != "gift":
        return ""
    currency, value = message.get("currency"), message.get("value")
    if not currency or not value:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return ""
    label = format_amount(currency, amount)
    return "" if label in str(message.get("text") or "") else label


def platform_totals(messages: list[dict], platforms: tuple[str, ...]) -> dict[str, dict]:
    """Summarize gift quantities, Super Chat events, and known revenue per platform."""
    totals = {
        platform: {
            "gift_count": 0,
            "gift_revenue": {},
            "superchat_count": 0,
            "superchat_revenue": {},
        }
        for platform in platforms
    }
    for msg in messages:
        summary = totals.get(msg.get("platform", ""))
        if summary is None:
            continue
        if msg.get("type") == "gift":
            count_key, revenue_key = "gift_count", "gift_revenue"
            try:
                count = int(msg.get("gift_count", 1) or 1)
            except (TypeError, ValueError):
                count = 1
            summary[count_key] += max(count, 1)
        elif msg.get("type") in _SUPER_CHAT_TYPES:
            count_key, revenue_key = "superchat_count", "superchat_revenue"
            summary[count_key] += 1
        else:
            continue
        currency, value = msg.get("currency"), msg.get("value")
        if currency and value:
            try:
                amount = float(value)
            except (TypeError, ValueError):
                continue
            if amount > 0:
                revenue = summary[revenue_key]
                revenue[currency] = revenue.get(currency, 0.0) + amount
    return totals


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
