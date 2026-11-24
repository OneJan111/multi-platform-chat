import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from desktop_app import DesktopChatArchive
from repair_chat_archives import convert_archive, repair_archives


class RepairChatArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.folder = Path(self.temp_dir.name) / "chat_archive"
        self.folder.mkdir()
        self.store = DesktopChatArchive(self.folder.parent / "chat_archive.json")
        self.data = {
            "Id": "bilibili:101", "Platform": "bilibili", "Identity": "101",
            "UpdatedAt": "2026-11-22T19:00:00+08:00",
            "Messages": [{
                "Timestamp": "1792321020", "Platform": "bilibili",
                "Author": "viewer", "Text": "saved message", "Type": "gift",
                "AuthorId": "42", "AvatarUrl": None, "VideoId": None,
                "Currency": "CNY", "Amount": 2.5, "ImageUrl": None,
            }],
        }
        self.source = self.folder / "dotnet-room.json"
        self.source.write_text(json.dumps(self.data), encoding="utf-8")
        self.output = io.StringIO()

    def run_repair(self, apply=False):
        with contextlib.redirect_stdout(self.output):
            return repair_archives(self.folder, apply=apply)

    def test_preview_does_not_modify_files(self):
        original = self.source.read_bytes()
        self.assertEqual(self.run_repair(), 1)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(list(self.folder.parent.glob("chat_archive_backup_*")))

    def test_apply_backs_up_and_restores_python_loading_and_appending(self):
        original = self.source.read_bytes()
        self.assertEqual(self.run_repair(apply=True), 1)
        backup = next(self.folder.parent.glob("chat_archive_backup_*"))
        self.assertEqual((backup / self.source.name).read_bytes(), original)
        target = self.store._session_path("bilibili:101")
        self.assertTrue(target.exists())
        self.assertFalse(self.source.exists())
        loaded = self.store.load_archive()
        self.assertTrue(loaded["ok"], loaded)
        message = loaded["archive"]["sessions"][0]["messages"][0]
        self.assertEqual(message["text"], "saved message")
        self.assertEqual(message["author_id"], "42")
        self.assertEqual(message["amount"], 2.5)
        result = self.store.append_messages(
            "bilibili:101",
            [{"timestamp": "later", "author": "viewer", "text": "new message"}],
            platform="bilibili",
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.store.load_archive()["archive"]["sessions"][0]["messages"]), 2)
        self.assertEqual(self.run_repair(apply=True), 0)

    def test_invalid_file_aborts_before_changing_any_archives(self):
        broken = self.folder / "invalid.json"
        broken.write_text('{"unrecognized": true}', encoding="utf-8")
        original = self.source.read_bytes()
        with self.assertRaisesRegex(ValueError, "invalid.json"):
            self.run_repair(apply=True)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(list(self.folder.parent.glob("chat_archive_backup_*")))

    def test_conflicting_room_files_are_not_overwritten(self):
        target = self.store._session_path("bilibili:101")
        target.write_bytes(self.source.read_bytes())
        with self.assertRaisesRegex(ValueError, "Conflicting room files"):
            self.run_repair(apply=True)
        self.assertTrue(self.source.exists())
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertFalse(list(self.folder.parent.glob("chat_archive_backup_*")))

    def test_invalid_message_reports_field_and_type_without_message_content(self):
        for field, value, type_name in (
            ("Timestamp", 123, "int"),
            ("Text", None, "NoneType"),
        ):
            with self.subTest(field=field):
                self.data["Messages"][0][field] = value
                with self.assertRaisesRegex(
                    ValueError, f"message 0: field '{field.lower()}' must be a string, got {type_name}"
                ):
                    convert_archive(self.data)
                self.data["Messages"][0][field] = ""

    def test_null_type_is_repaired_in_python_archive_without_losing_messages(self):
        data = convert_archive(self.data)
        data["sessions"][0]["messages"][0]["type"] = None
        target = self.store._session_path("bilibili:101")
        self.source.rename(target)
        target.write_text(json.dumps(data), encoding="utf-8")
        original = target.read_bytes()
        self.assertEqual(self.run_repair(apply=True), 1)
        backup = next(self.folder.parent.glob("chat_archive_backup_*"))
        self.assertEqual((backup / target.name).read_bytes(), original)
        loaded = self.store.load_archive()
        self.assertTrue(loaded["ok"], loaded)
        messages = loaded["archive"]["sessions"][0]["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "")
        self.assertEqual(messages[0]["text"], "saved message")
        self.assertIsNone(data["sessions"][0]["messages"][0]["type"])
        self.assertEqual(self.run_repair(), 0)

    def test_null_type_is_repaired_in_dotnet_archive(self):
        self.data["Messages"][0]["Type"] = None
        converted = convert_archive(self.data)
        self.assertEqual(converted["sessions"][0]["messages"][0]["type"], "")
        self.assertIsNone(self.data["Messages"][0]["Type"])

    def test_python_format_message_also_gets_specific_diagnostics(self):
        data = convert_archive(self.data)
        data["sessions"][0]["messages"][0]["translation"] = None
        self.source.write_text(json.dumps(data), encoding="utf-8")
        original = self.source.read_bytes()
        with self.assertRaisesRegex(ValueError, "field 'translation'.*NoneType"):
            self.run_repair(apply=True)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(list(self.folder.parent.glob("chat_archive_backup_*")))


if __name__ == "__main__":
    unittest.main()
