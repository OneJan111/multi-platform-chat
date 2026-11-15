import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from src.room_events import RoomEvents


class RoomEventsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "events.sqlite3"
        self.store = RoomEvents(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def messages(self, room, count):
        return [RoomEvents.message({
            "_monitor_id": room, "platform": room.partition(":")[0],
            "type": "danmaku", "id": str(index), "text": f"message {index}",
        }, 1700000000 + index) for index in range(count)]

    def test_persistence_pagination_and_room_scoped_deletion(self):
        self.store.append(self.messages("bilibili:1", 205))
        self.store.append(self.messages("bilibili:2", 7))
        restarted = RoomEvents(self.path)
        first = restarted.page("bilibili:1")
        self.assertEqual(len(first["events"]), 100)
        self.store.append(self.messages("bilibili:1", 1))
        second = restarted.page("bilibili:1", first["next"])
        third = restarted.page("bilibili:1", second["next"])
        ids = [row["id"] for page in (first, second, third) for row in page["events"]]
        self.assertEqual(len(ids), 205)
        self.assertEqual(len(set(ids)), 205)
        self.assertIsNone(third["next"])
        self.assertEqual(restarted.analytics("bilibili:1")["messages"], 206)
        exported = [json.loads(line) for line in b"".join(restarted.export("bilibili:1")).splitlines()]
        self.assertEqual(len(exported), 206)
        self.assertTrue(all(row["room"] == "bilibili:1" for row in exported))
        self.assertEqual(len(restarted.rooms()), 2)
        self.assertEqual(restarted.delete("bilibili:1"), {"deleted": 206})
        self.assertEqual(restarted.page("bilibili:1")["events"], [])
        self.assertEqual(restarted.analytics("bilibili:2")["messages"], 7)

    def test_viewer_changes_and_missing_counts_are_not_fabricated(self):
        previous = {}
        for value in (10, 10, "10", "", None, 0, 5):
            current = {"bilibili:1": {"live": True, "viewers": value}}
            self.store.append(RoomEvents.statuses(current, previous, 1700000000))
            previous = current
        rows = self.store.page("bilibili:1")["events"]
        viewers = [event for event in reversed(rows) if event["kind"] == "viewer_count"]
        self.assertEqual([event["payload"]["viewers"] for event in viewers], [10, 0, 5])
        self.assertEqual(viewers[-1]["payload"]["delta"], 5)
        result = self.store.analytics("bilibili:1")
        self.assertEqual(result["viewers"], [{"site": "bilibili", "now": 5, "peak": 10}])
        self.assertEqual(result["counts"]["live_status"], 1)

    def test_messages_per_minute_uses_system_local_timezone(self):
        timestamp = 1700000000
        message = {"_monitor_id": "bilibili:1", "platform": "bilibili",
                   "type": "danmaku", "text": "message"}
        self.store.append([RoomEvents.message(message, timestamp)])

        rows = [row for row in self.store.analytics("bilibili:1")["rows"]
                if row[0] == "Messages/minute"]

        self.assertEqual(rows, [[
            "Messages/minute", "", 1, datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        ]])

    def test_export_preserves_original_event_metadata_and_history(self):
        message = {"_monitor_id": "youtube:abcdefghijk", "platform": "youtube",
                   "type": "gift", "id": "gift-1", "author": "Viewer", "author_id": "u1",
                   "text": "ありがとう", "history": True, "value": 2.5, "currency": "USD",
                   "gift_count": 3, "original_value": 5, "nested": {"effect": "image"}}
        self.store.append([RoomEvents.message(message, 1700000000)])
        data = b"".join(self.store.export("youtube:abcdefghijk")).decode("utf-8")
        event = json.loads(data)
        self.assertEqual(event["payload"], message)
        self.assertEqual(event["kind"], "gift")
        self.assertEqual(event["room"], "youtube:abcdefghijk")
        self.assertEqual(event["session"], self.store.session)
        self.assertEqual(list(self.store.export("bilibili:1")), [])
        result = self.store.analytics("youtube:abcdefghijk")
        self.assertIn(["Paid value", "", "2.5 USD", "Original platform currency"], result["rows"])
        self.assertEqual(self.store.hotspots("youtube:abcdefghijk", 30), ([], None))

    def test_invalid_page_arguments_are_reported(self):
        for before, limit in ((-1, 100), (True, 100), (0, 0), (0, 201), ("1", 100)):
            with self.subTest(before=before, limit=limit), self.assertRaises(ValueError):
                self.store.page("bilibili:1", before, limit)

    def test_author_history_uses_id_across_renames_and_paginates_within_room(self):
        events = []
        for index in range(105):
            events.append(RoomEvents.message({
                "_monitor_id": "bilibili:1", "platform": "bilibili",
                "type": "danmaku", "author_id": 42,
                "author": "Old" if index < 50 else "New", "text": str(index),
            }, 1700000000 + index))
        for room, uid, kind in (("bilibili:2", "42", "danmaku"),
                                ("bilibili:1", "43", "danmaku"),
                                ("bilibili:1", "42", "enter")):
            events.append(RoomEvents.message({
                "_monitor_id": room, "platform": "bilibili", "author_id": uid,
                "author": "New", "type": kind, "text": "excluded",
            }, 1700000200))
        self.store.append(events)
        store = RoomEvents(self.path)
        first = store.author_history("bilibili:1", "42", "New")
        second = store.author_history("bilibili:1", "42", "New", first["next"])
        self.assertEqual(len(first["events"]), 100)
        self.assertEqual(len(second["events"]), 5)
        self.assertIsNone(second["next"])
        self.assertEqual(first["events"][0]["payload"]["text"], "104")
        self.assertEqual(second["events"][-1]["payload"]["author"], "Old")

    def test_author_history_falls_back_to_name_and_validates_input(self):
        self.store.append([RoomEvents.message({
            "_monitor_id": "youtube:1", "platform": "youtube", "author": "Viewer",
            "text": "hello", "type": "textMessageEvent",
        }, 1700000000)])
        self.assertEqual(len(self.store.author_history("youtube:1", "0", "Viewer")["events"]), 1)
        for uid, name, before, limit in (("", "", 0, 100), (None, "Viewer", 0, 100),
                                        ("", "Viewer", -1, 100), ("", "Viewer", 0, 201)):
            with self.subTest(uid=uid, before=before, limit=limit), self.assertRaises(ValueError):
                self.store.author_history("youtube:1", uid, name, before, limit)

if __name__ == "__main__":
    unittest.main()
