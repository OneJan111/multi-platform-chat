import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import desktop_app
from src.room_events import RoomEvents


@unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
class DesktopRoomEventsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.addCleanup(self.executor.shutdown)
        self.window = SimpleNamespace(
            _event_store=RoomEvents(Path(self.directory.name) / "events.sqlite3"),
            _event_executor=self.executor,
        )
        for name in ("_record_room_events", "_event_query"):
            setattr(self.window, name, getattr(desktop_app._DesktopWindow, name).__get__(self.window))

    def test_recorded_messages_are_queryable_by_room_and_author(self):
        message = {"_monitor_id": "bilibili:1", "platform": "bilibili", "author": "A",
                   "author_id": "7", "text": "hello"}
        self.window._record_room_events([RoomEvents.message(message, 1700000000)])
        message["text"] = "mutated"
        store = self.window._event_store
        page = self.window._event_query(store.page, "bilibili:1")
        self.assertEqual([event["payload"]["text"] for event in page["events"]], ["hello"])
        history = self.window._event_query(store.author_history, "bilibili:1", "7", "A")
        self.assertEqual(len(history["events"]), 1)
        self.assertEqual(self.window._event_query(store.delete, "bilibili:1"), {"deleted": 1})


if __name__ == "__main__":
    unittest.main()
