import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from desktop_app import DesktopChatArchive


@unittest.skipUnless(shutil.which("dotnet"), ".NET SDK is not installed")
class DotNetArchiveCompatibilityTests(unittest.TestCase):
    def test_dotnet_writes_python_compatible_archives_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = DesktopChatArchive(root / "chat_archive.json")
            store.sessions_path.mkdir()
            python_path = store._session_path("bilibili:101")
            python_path.write_text(json.dumps({
                "version": 1,
                "sessions": [{
                    "session_id": "bilibili:101", "platform": "bilibili",
                    "room_id": "101", "channel_id": "", "room_name": "Room name",
                    "started_at": "original start", "updated_at": "previous update",
                    "messages": [{
                        "timestamp": "earlier", "platform": "bilibili", "author": "viewer",
                        "text": "original", "type": None, "translation": "translated",
                        "sticker_url": "https://example.invalid/sticker.png",
                    }],
                }],
            }), encoding="utf-8")
            identity = "https://www.youtube.com/channel/" + "U" * 90
            digest = hashlib.sha256(f"youtube:{identity}".encode()).hexdigest()[:12]
            safe = "".join(character if character.isalnum() or character in "-_" else "_"
                           for character in identity)[:60]
            legacy_path = store.sessions_path / f"youtube_{safe}_{digest}.json"
            legacy_path.write_text(json.dumps({
                "Id": f"youtube:{identity}", "Platform": "youtube", "Identity": identity,
                "UpdatedAt": "previous update",
                "Messages": [{
                    "Timestamp": "earlier", "Platform": "youtube", "Author": "viewer",
                    "Text": "legacy", "Type": "gift",
                }],
            }), encoding="utf-8")
            original_legacy = legacy_path.read_bytes()
            targets = root / "targets.json"
            targets.write_text(json.dumps([
                {"Id": "one", "Platform": "bilibili", "Target": "101"},
                {"Id": "two", "Platform": "youtube", "Target": identity},
                {"Id": "three", "Platform": "missevan", "Target": "..room.name"},
            ]), encoding="utf-8")
            project = Path(__file__).parent / "dotnet_chat_archive" / "ArchiveCompatibility.csproj"
            environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1")
            result = subprocess.run(
                ["dotnet", "run", "--project", str(project), "--", str(store.sessions_path), str(targets)],
                capture_output=True, text=True, timeout=180, env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            loaded = store.load_archive()
            self.assertTrue(loaded["ok"], loaded)
            sessions = {session["session_id"]: session for session in loaded["archive"]["sessions"]}
            self.assertEqual(len(sessions), 3)
            for session in sessions.values():
                self.assertTrue(store._session_path(session["session_id"]).is_file())
                self.assertEqual(session["messages"][-1]["text"], "new message")
            session = sessions["bilibili:101"]
            self.assertEqual(session["started_at"], "original start")
            self.assertEqual(session["room_name"], "Room name")
            original = session["messages"][0]
            self.assertEqual(original["text"], "original")
            self.assertEqual(original["type"], "")
            self.assertEqual(original["translation"], "translated")
            self.assertEqual(original["sticker_url"], "https://example.invalid/sticker.png")
            self.assertFalse(legacy_path.exists())
            backups = list(store.sessions_path.glob("*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original_legacy)
            self.assertEqual(len(sessions[f"youtube:{identity}"]["messages"]), 2)


if __name__ == "__main__":
    unittest.main()
