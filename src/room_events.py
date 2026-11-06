"""Durable, room-scoped event history for the HTML dashboard."""
from __future__ import annotations

from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
import uuid

from src import highlights, tts


def _number(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


class RoomEvents:
    def __init__(self, path: Path):
        self.path = path
        self.session = uuid.uuid4().hex
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session TEXT NOT NULL, received_at REAL NOT NULL,
                    room TEXT NOT NULL, platform TEXT NOT NULL, kind TEXT NOT NULL,
                    history INTEGER NOT NULL, author TEXT NOT NULL,
                    paid INTEGER NOT NULL, currency TEXT NOT NULL, value REAL,
                    viewers REAL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_room_id ON events(room, id);
                CREATE INDEX IF NOT EXISTS events_room_kind ON events(room, kind, id);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def append(self, events):
        rows = []
        for event in events:
            payload = event["payload"]
            rows.append((
                self.session, event["received_at"], event["room"], event["platform"], event["kind"],
                bool(payload.get("history")), str(payload.get("author") or ""),
                event.get("paid", False), str(payload.get("currency") or ""),
                _number(payload.get("value")), _number(event.get("viewers")),
                json.dumps(payload, ensure_ascii=False, allow_nan=False),
            ))
        with closing(self.connect()) as db, db:
            db.executemany("INSERT INTO events "
                           "(session, received_at, room, platform, kind, history, author, paid, "
                           "currency, value, viewers, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    @staticmethod
    def message(message, received_at):
        paid = tts.is_paid(message) or tts.is_gift(message)
        kind = ("gift" if tts.is_gift(message) else "paid" if paid else
                "join" if message.get("type") == "enter" else
                "chat" if message.get("type") in (None, "", "danmaku", "text") else
                str(message["type"]))
        return {"room": message["_monitor_id"], "platform": message["platform"],
                "received_at": received_at, "kind": kind, "paid": paid, "payload": message}

    @staticmethod
    def statuses(statuses, previous, received_at):
        events = []
        for room, info in statuses.items():
            old = previous.get(room, {})
            base = {"room": room, "platform": room.partition(":")[0],
                    "received_at": received_at}
            if room not in previous or info != old:
                events.append({**base, "kind": "room_status", "payload": info})
            if "live" in info and ("live" not in old or info["live"] != old["live"]):
                events.append({**base, "kind": "live_status",
                               "payload": {"live": info["live"], "previous": old.get("live")}})
            now, before = _number(info.get("viewers")), _number(old.get("viewers"))
            if now is not None and (room not in previous or now != before):
                events.append({**base, "kind": "viewer_count", "viewers": now,
                               "payload": {"viewers": now, "previous": before,
                                           "delta": now - before if before is not None else None}})
        return events

    def rooms(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute(
                "SELECT room, platform, COUNT(*) AS events FROM events GROUP BY room, platform "
                "ORDER BY platform, room")]

    def page(self, room, before=0, limit=100):
        if type(before) is not int or before < 0:
            raise ValueError("Invalid event cursor.")
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Event limit must be 1–200.")
        with closing(self.connect()) as db:
            records = db.execute(
                "SELECT * FROM events WHERE room=? AND (?=0 OR id<?) "
                "ORDER BY id DESC LIMIT ?", (room, before, before, limit + 1)).fetchall()
        return {"events": [self.decode(row) for row in records[:limit]],
                "next": records[limit - 1]["id"] if len(records) > limit else None}

    @staticmethod
    def decode(row):
        return {key: row[key] for key in ("id", "session", "received_at", "room", "platform", "kind")} | {
            "payload": json.loads(row["payload"])}

    def export(self, room):
        # A read transaction gives a consistent export while new events keep arriving in WAL mode.
        with closing(self.connect()) as db, db:
            db.execute("BEGIN")
            cursor = db.execute("SELECT * FROM events WHERE room=? ORDER BY id", (room,))
            while rows := cursor.fetchmany(200):
                for row in rows:
                    yield (json.dumps(self.decode(row), ensure_ascii=False) + "\n").encode("utf-8")

    def delete(self, room):
        with closing(self.connect()) as db, db:
            count = db.execute("DELETE FROM events WHERE room=?", (room,)).rowcount
        return {"deleted": count}

    def analytics(self, room):
        message_filter = "kind NOT IN ('room_status','live_status','viewer_count','join')"
        with closing(self.connect()) as db:
            counts = {row["kind"]: row["n"] for row in db.execute(
                "SELECT kind, COUNT(*) AS n FROM events WHERE room=? GROUP BY kind", (room,))}
            messages = db.execute(
                f"SELECT COUNT(*) FROM events WHERE room=? AND {message_filter}", (room,)).fetchone()[0]
            rows = [["Messages", "", messages, "All recorded messages"]]
            rows += [["Recorded events", "", sum(counts.values()), ""]]
            rows += [[kind, "", count, ""] for kind, count in counts.items()]
            rows += [["Paid value", "", f"{row['total']:g} {row['currency']}", "Original platform currency"]
                     for row in db.execute(
                         "SELECT currency, SUM(value) AS total FROM events "
                         "WHERE room=? AND paid=1 AND currency<>'' AND value IS NOT NULL GROUP BY currency",
                         (room,))]
            rows += [["Top chatter", "", row["n"], row["author"]] for row in db.execute(
                f"SELECT author, COUNT(*) AS n FROM events WHERE room=? AND {message_filter} "
                "GROUP BY author ORDER BY n DESC LIMIT 20", (room,))]
            rows += [["Messages/minute", "", row["n"], row["minute"]] for row in db.execute(
                "SELECT strftime('%Y-%m-%d %H:%M', received_at, 'unixepoch', 'localtime') AS minute, COUNT(*) AS n "
                f"FROM events WHERE room=? AND {message_filter} GROUP BY minute ORDER BY n DESC LIMIT 20",
                (room,))]
            latest = db.execute(
                "SELECT viewers FROM events WHERE room=? AND kind='viewer_count' ORDER BY id DESC LIMIT 1",
                (room,)).fetchone()
            peak = db.execute(
                "SELECT MAX(viewers) FROM events WHERE room=? AND kind='viewer_count'", (room,)).fetchone()[0]
        return {"room": room, "messages": messages, "counts": counts, "rows": rows,
                "events": sum(counts.values()), "viewers": [] if latest is None else [
                    {"site": room.partition(":")[0], "now": latest["viewers"], "peak": peak}]}

    def hotspots(self, room, window):
        # Sessions stay separate: a quiet gap between app runs must not create huge empty buckets.
        with closing(self.connect()) as db:
            latest = db.execute(
                "SELECT session FROM events WHERE room=? AND kind IN ('chat','gift','paid') "
                "AND history=0 ORDER BY id DESC LIMIT 1", (room,)).fetchone()
            if latest is None:
                return [], None
            events = [highlights.log_entry(json.loads(row["payload"]), bool(row["paid"]), row["received_at"])
                      for row in db.execute(
                          "SELECT payload, paid, received_at FROM events "
                          "WHERE room=? AND session=? AND kind IN ('chat','gift','paid') AND history=0 "
                          "ORDER BY id", (room, latest["session"]))]
        return highlights.find_highlights(events, window=window), min(e["ts"] for e in events)
