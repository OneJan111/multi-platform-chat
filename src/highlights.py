"""Find chat hotspots (bursts of chat, gifts and Super Chats) and export them as clip lists."""
from __future__ import annotations

import csv
import io
import re
import statistics
from collections import Counter
from datetime import datetime

PAID_WEIGHT = 5  # one gift / Super Chat counts like this many chat messages
MAX_LOG = 200_000


def to_epoch(ts) -> float | None:
    """Epoch seconds from a message timestamp: epoch seconds/ms (str or number) or ISO 8601."""
    if ts is None or ts == "":
        return None
    try:
        value = float(ts)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt.timestamp()
    return value / 1000 if value > 1e11 else value


def log_entry(msg: dict, paid: bool, now: float) -> dict:
    ts = to_epoch(msg.get("timestamp"))
    return {
        "ts": ts if ts is not None else now,
        "platform": msg.get("platform", ""),
        "paid": paid,
        "text": str(msg.get("text", ""))[:80],
    }


_REPEAT = re.compile(r"(.)\1{3,}")


def _normalise(text: str) -> str:
    """"哈哈哈哈哈" and "哈哈哈哈" count as the same phrase."""
    return _REPEAT.sub(r"\1\1\1", text.strip().lower())


def find_highlights(events: list[dict], window: int = 30, sensitivity: float = 2.0, min_score: int = 5,
                    top: int = 20, pre_roll: int = 20, post_roll: int = 10) -> list[dict]:
    """Group events into `window`-second buckets, keep runs of buckets well above the stream's usual
    activity, and return the `top` busiest as clips (chronological), padded by pre/post roll."""
    events = [e for e in events if e.get("ts") is not None]
    if not events or window <= 0:
        return []
    first = min(e["ts"] for e in events)
    buckets: dict[int, list[dict]] = {}
    for e in events:
        buckets.setdefault(int((e["ts"] - first) // window), []).append(e)
    last = max(buckets)
    score = [sum(PAID_WEIGHT if e["paid"] else 1 for e in buckets.get(b, [])) for b in range(last + 1)]
    threshold = max(min_score, statistics.median(score) * sensitivity)
    hot = [b for b, s in enumerate(score) if s >= threshold]

    runs: list[list[int]] = []
    for b in hot:
        if runs and b - runs[-1][-1] <= 2:  # one quiet bucket between two bursts doesn't split them
            runs[-1].append(b)
        else:
            runs.append([b])

    clips = []
    for run in runs:
        members = [e for b in range(run[0], run[-1] + 1) for e in buckets.get(b, [])]
        chat = [e for e in members if not e["paid"]]
        paid = [e for e in members if e["paid"]]
        peak = max(run, key=lambda b: score[b])
        phrases = Counter(_normalise(e["text"]) for e in chat if e["text"].strip())
        start = first + run[0] * window
        end = first + (run[-1] + 1) * window
        clips.append({
            "start": start - pre_roll,
            "end": end + post_roll,
            "peak": first + peak * window,
            "score": sum(score[b] for b in range(run[0], run[-1] + 1)),
            "chat": len(chat),
            "paid": len(paid),
            "platforms": sorted({e["platform"] for e in members if e["platform"]}),
            "phrases": [(p, n) for p, n in phrases.most_common(3) if n >= 2],
            "paid_texts": [e["text"] for e in paid[:3]],
            "sample": [e["text"] for e in chat[:3]],
        })
    clips.sort(key=lambda c: c["score"], reverse=True)
    return sorted(clips[:top], key=lambda c: c["start"])


def offset(seconds: float) -> str:
    """Seconds since stream start -> HH:MM:SS (never negative)."""
    s = max(0, int(round(seconds)))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def timecode(seconds: float, fps: int, hour: int = 0) -> str:
    frames = max(0, int(round(seconds * fps)))
    s, f = divmod(frames, fps)
    return f"{s // 3600 + hour:02d}:{s % 3600 // 60:02d}:{s % 60:02d}:{f:02d}"


def summary(clip: dict) -> str:
    """Short description: top phrases, else paid events, else sample chat."""
    if clip["phrases"]:
        return " / ".join(f"{p}×{n}" for p, n in clip["phrases"])
    return " / ".join(clip["paid_texts"] or clip["sample"])[:120]


def to_csv(rows: list[dict]) -> bytes:
    """UTF-8 with BOM so Excel shows Chinese/Japanese correctly."""
    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def to_edl(clips: list[dict], origin: float, fps: int = 30, hour: int = 0, title: str = "Hotspots") -> bytes:
    """CMX 3600 marker EDL — DaVinci Resolve: right-click the timeline > Timelines > Import > Timeline
    Markers from EDL. `hour` = the timeline's start hour (Resolve defaults to 01:00:00:00)."""
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    for n, clip in enumerate(clips, 1):
        start = max(0.0, clip["start"] - origin)
        tc_in, tc_out = timecode(start, fps, hour), timecode(start + 1 / fps, fps, hour)
        name = re.sub(r"[|\r\n]+", " ", f"#{n} {summary(clip)}").strip()[:80]
        duration = max(1, int(round((clip["end"] - max(clip["start"], origin)) * fps)))
        lines.append(f"{n:03d}  001      V     C        {tc_in} {tc_out} {tc_in} {tc_out}  ")
        lines.append(f" |C:ResolveColorRed |M:{name} |D:{duration}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")
