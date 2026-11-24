"""Restore .NET room archives to the Python desktop archive format."""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from desktop_app import DesktopChatArchive


def validate_archive(archive: dict) -> dict:
    sessions = archive.get("sessions")
    if isinstance(sessions, list):
        for session_index, session in enumerate(sessions):
            if not isinstance(session, dict) or not isinstance(session.get("messages"), list):
                continue
            for message_index, message in enumerate(session["messages"]):
                location = f"session {session_index}, message {message_index}"
                if not isinstance(message, dict):
                    raise ValueError(f"{location}: expected a message object, got {type(message).__name__}.")
                for field in ("timestamp", "author", "text", "platform", "type", "translation"):
                    required = field in ("timestamp", "author", "text")
                    if field not in message:
                        if required:
                            raise ValueError(f"{location}: missing required field '{field}'.")
                        continue
                    if field == "type" and message[field] is None:
                        message[field] = ""
                        continue
                    if not isinstance(message[field], str):
                        raise ValueError(
                            f"{location}: field '{field}' must be a string, "
                            f"got {type(message[field]).__name__}."
                        )
    return DesktopChatArchive._validate_archive(archive)


def convert_archive(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Archive must be a JSON object.")
    if "version" in data or "sessions" in data:
        return validate_archive(copy.deepcopy(data))

    for key in ("Id", "Platform", "Identity", "UpdatedAt"):
        if not isinstance(data.get(key), str):
            raise ValueError(f"Missing or invalid .NET archive field: {key}.")
    platform = data["Platform"]
    identity = data["Identity"]
    if platform not in ("youtube", "bilibili", "missevan") or not identity:
        raise ValueError("Invalid .NET archive platform or identity.")
    if data["Id"] != f"{platform}:{identity}":
        raise ValueError(".NET archive ID does not match its platform and identity.")
    if not isinstance(data.get("Messages"), list):
        raise ValueError("Missing or invalid .NET archive Messages.")

    messages = []
    for message in data["Messages"]:
        if not isinstance(message, dict):
            raise ValueError(".NET archive contains an invalid message.")
        messages.append({
            re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower(): value
            for key, value in message.items()
        })
    session = {
        "session_id": data["Id"],
        "platform": platform,
        "room_id": identity if platform != "youtube" else "",
        "channel_id": identity if platform == "youtube" else "",
        "room_name": "",
        "started_at": data["UpdatedAt"],
        "updated_at": data["UpdatedAt"],
        "messages": messages,
    }
    return validate_archive({"version": 1, "sessions": [session]})


def repair_archives(directory: Path, *, apply: bool = False) -> int:
    directory = directory.resolve()
    if not directory.is_dir():
        raise ValueError(f"Archive folder does not exist: {directory}")
    store = DesktopChatArchive(directory.parent / "chat_archive.json")
    store.sessions_path = directory
    changes = []
    destinations = set()
    for source in sorted(directory.glob("*.json")):
        try:
            original = source.read_bytes()
            data = json.loads(original.decode("utf-8-sig"))
            archive = convert_archive(data)
            if len(archive["sessions"]) != 1:
                raise ValueError("A room file must contain exactly one session.")
            target = store._session_path(archive["sessions"][0]["session_id"])
            if target in destinations or (target != source and target.exists()):
                raise ValueError(f"Conflicting room files for {target.name}; nothing was changed.")
            destinations.add(target)
            if archive != data or target != source or original.startswith(b"\xef\xbb\xbf"):
                changes.append((source, target, archive, original))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"{source.name}: {exc}") from exc

    for source, target, _, _ in changes:
        print(f"{'Repair' if apply else 'Would repair'}: {source.name} -> {target.name}")
    if not apply:
        print(f"Preview: {len(changes)} file(s) need repair. Use --apply after closing all dashboard apps.")
        return len(changes)
    if not changes:
        print("No repairs needed.")
        return 0

    backup = Path(tempfile.mkdtemp(prefix="chat_archive_backup_", dir=directory.parent))
    print(f"Backup folder: {backup}", flush=True)
    for source, _, _, original in changes:
        if source.read_bytes() != original:
            raise ValueError(f"{source.name} changed during repair. Close all dashboard apps and retry.")
        shutil.copy2(source, backup / source.name)
    for source, target, archive, original in changes:
        if source.read_bytes() != original:
            raise ValueError(f"{source.name} changed during repair. Originals are in {backup}.")
        if target != source and target.exists():
            raise ValueError(f"{target.name} appeared during repair. Originals are in {backup}.")
        store._write_path(target, archive)
        if target != source:
            source.unlink()
    print(f"Repaired {len(changes)} file(s). Original files are preserved in {backup}.")
    return len(changes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--folder", type=Path, default=DesktopChatArchive().sessions_path,
        help="Archive folder (default: the current Python desktop archive folder).",
    )
    parser.add_argument("--apply", action="store_true", help="Back up originals and apply repairs.")
    args = parser.parse_args()
    try:
        repair_archives(args.folder, apply=args.apply)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
