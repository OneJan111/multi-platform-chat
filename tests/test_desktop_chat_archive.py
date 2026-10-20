import json
import tempfile
import unittest
from pathlib import Path

from desktop_app import DesktopChatArchive, _saved_session_room_label


class DesktopChatArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "chat_archive.json"
        self.archive = DesktopChatArchive(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def message(text):
        return {
            "timestamp": "1792321020",
            "platform": "bilibili",
            "author": "viewer",
            "text": text,
        }

    def save_room(self, room_id, text, room_name=""):
        return self.archive.save_snapshot(
            f"bilibili:{room_id}",
            [self.message(text)],
            platform="bilibili",
            room_id=room_id,
            room_name=room_name,
        )

    def test_rooms_are_saved_in_separate_files_and_load_together(self):
        self.assertTrue(self.save_room("101", "room one")["ok"])
        self.assertTrue(self.save_room("202", "room two")["ok"])

        room_files = list(self.archive.sessions_path.glob("*.json"))
        self.assertEqual(len(room_files), 2)
        self.assertTrue(all(len(json.loads(path.read_text())["sessions"]) == 1 for path in room_files))

        loaded = self.archive.load_archive()
        self.assertTrue(loaded["ok"])
        sessions = {
            session["session_id"]: session
            for session in loaded["archive"]["sessions"]
        }
        self.assertEqual(sessions["bilibili:101"]["messages"][0]["text"], "room one")
        self.assertEqual(sessions["bilibili:202"]["messages"][0]["text"], "room two")

    def test_room_name_is_persisted_and_used_for_saved_session_label(self):
        saved = self.save_room("101", "room one", "Channel Name")

        self.assertTrue(saved["ok"])
        session = saved["archive"]["sessions"][0]
        self.assertEqual(session["room_name"], "Channel Name")
        self.assertEqual(_saved_session_room_label(session), "Channel Name")

    def test_saved_session_label_falls_back_to_room_id_for_older_archives(self):
        self.assertEqual(
            _saved_session_room_label(
                {"session_id": "bilibili:101", "room_id": "101"}
            ),
            "101",
        )

    def test_existing_combined_archive_is_migrated_on_save(self):
        legacy = {
            "version": 1,
            "sessions": [
                {
                    "session_id": "bilibili:101",
                    "platform": "bilibili",
                    "room_id": "101",
                    "channel_id": "",
                    "started_at": "start",
                    "updated_at": "",
                    "messages": [self.message("legacy room one")],
                },
                {
                    "session_id": "bilibili:202",
                    "platform": "bilibili",
                    "room_id": "202",
                    "channel_id": "",
                    "started_at": "start",
                    "updated_at": "",
                    "messages": [self.message("legacy room two")],
                },
            ],
        }
        self.path.write_text(json.dumps(legacy), encoding="utf-8")

        self.assertTrue(self.save_room("101", "new room one")["ok"])

        self.assertFalse(self.path.exists())
        self.assertEqual(len(list(self.archive.sessions_path.glob("*.json"))), 2)
        loaded = self.archive.load_archive()
        self.assertTrue(loaded["ok"])
        sessions = {
            session["session_id"]: session
            for session in loaded["archive"]["sessions"]
        }
        self.assertEqual(
            {message["text"] for message in sessions["bilibili:101"]["messages"]},
            {"legacy room one", "new room one"},
        )
        self.assertEqual(
            sessions["bilibili:202"]["messages"][0]["text"],
            "legacy room two",
        )

    def test_loading_existing_combined_archive_splits_it_by_room(self):
        legacy = {
            "version": 1,
            "sessions": [
                {
                    "session_id": "bilibili:101",
                    "platform": "bilibili",
                    "room_id": "101",
                    "channel_id": "",
                    "started_at": "start",
                    "updated_at": "",
                    "messages": [self.message("room one")],
                },
                {
                    "session_id": "youtube:channel-id",
                    "platform": "youtube",
                    "room_id": "",
                    "channel_id": "channel-id",
                    "started_at": "start",
                    "updated_at": "",
                    "messages": [self.message("room two")],
                },
            ],
        }
        self.path.write_text(json.dumps(legacy), encoding="utf-8")

        loaded = self.archive.load_archive()

        self.assertTrue(loaded["ok"])
        self.assertFalse(self.path.exists())
        self.assertEqual(len(list(self.archive.sessions_path.glob("*.json"))), 2)
        self.assertEqual(
            {session["session_id"] for session in loaded["archive"]["sessions"]},
            {"bilibili:101", "youtube:channel-id"},
        )

    def test_deleting_room_removes_only_its_file(self):
        self.assertTrue(self.save_room("101", "room one")["ok"])
        self.assertTrue(self.save_room("202", "room two")["ok"])

        deleted = self.archive.delete_session("bilibili:101")

        self.assertTrue(deleted["ok"])
        loaded = self.archive.load_archive()
        self.assertTrue(loaded["ok"])
        self.assertEqual(
            [session["session_id"] for session in loaded["archive"]["sessions"]],
            ["bilibili:202"],
        )


if __name__ == "__main__":
    unittest.main()
