"""Chat filter module: keyword/regex filters and per-user blocklist, saved to a JSON file."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import NamedTuple

DEFAULT_FILTER_FILE = Path(__file__).resolve().parent.parent / "chat_filters.json"


class FilterResult(NamedTuple):
    allowed: bool
    reason: str  # empty when allowed


class ChatFilter:
    def __init__(self, path: str | Path | None = None):
        # key -> display name. Key is "platform:author_id" (from the 🚫 button) or a bare
        # author_id (typed in by hand), which matches that ID on any platform.
        self._blocked_users: dict[str, str] = {}
        self._blocked_names: set[str] = set()       # lower-case display name
        self._keyword_patterns: list[re.Pattern] = []
        self._allow_patterns: list[re.Pattern] = [] # always allow if matched
        self.path: Path | None = Path(path) if path else None

    # ── Persistence ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "blocked_users": self._blocked_users,
            "blocked_names": sorted(self._blocked_names),
            "block_patterns": self.block_patterns,
            "allow_patterns": self.allow_patterns,
        }

    def load(self) -> bool:
        """Load from self.path. Returns False if there is no saved file."""
        if not self.path or not self.path.exists():
            return False
        data = json.loads(self.path.read_text(encoding="utf-8"))
        users = data.get("blocked_users", {})
        self._blocked_users = dict(users) if isinstance(users, dict) else {u: "" for u in users}
        self._blocked_names = {n.lower() for n in data.get("blocked_names", [])}
        self._keyword_patterns = [re.compile(p, re.IGNORECASE) for p in data.get("block_patterns", [])]
        self._allow_patterns = [re.compile(p, re.IGNORECASE) for p in data.get("allow_patterns", [])]
        return True

    def save(self) -> None:
        if not self.path:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic, so a crash can't leave a half-written file

    # ── User blocklist ─────────────────────────────────────────────────────────

    @staticmethod
    def user_key(platform: str, author_id: str) -> str:
        return f"{platform}:{author_id}" if platform else author_id

    def block_user(self, author_id: str, name: str = "", platform: str = "") -> None:
        self._blocked_users[self.user_key(platform, author_id)] = name
        self.save()

    def unblock_user(self, key: str) -> None:
        self._blocked_users.pop(key, None)
        self.save()

    def block_name(self, name: str) -> None:
        self._blocked_names.add(name.lower())
        self.save()

    def unblock_name(self, name: str) -> None:
        self._blocked_names.discard(name.lower())
        self.save()

    @property
    def blocked_users(self) -> dict[str, str]:
        """{key: display name}; key is "platform:author_id" or a bare author_id."""
        return dict(self._blocked_users)

    @property
    def blocked_names(self) -> list[str]:
        return sorted(self._blocked_names)

    def is_blocked_user(self, msg: dict) -> bool:
        author_id = msg.get("author_id", "")
        if not author_id:
            return False
        return (
            self.user_key(msg.get("platform", ""), author_id) in self._blocked_users
            or author_id in self._blocked_users
        )

    # ── Keyword / regex patterns ───────────────────────────────────────────────

    def add_block_pattern(self, pattern: str, flags: int = re.IGNORECASE) -> None:
        self._keyword_patterns.append(re.compile(pattern, flags))
        self.save()

    def remove_block_pattern(self, pattern: str) -> None:
        self._keyword_patterns = [
            p for p in self._keyword_patterns if p.pattern != pattern
        ]
        self.save()

    def add_allow_pattern(self, pattern: str, flags: int = re.IGNORECASE) -> None:
        self._allow_patterns.append(re.compile(pattern, flags))
        self.save()

    def remove_allow_pattern(self, pattern: str) -> None:
        self._allow_patterns = [p for p in self._allow_patterns if p.pattern != pattern]
        self.save()

    @property
    def block_patterns(self) -> list[str]:
        return [p.pattern for p in self._keyword_patterns]

    @property
    def allow_patterns(self) -> list[str]:
        return [p.pattern for p in self._allow_patterns]

    # ── Evaluate ───────────────────────────────────────────────────────────────

    def check(self, msg: dict) -> FilterResult:
        """Return FilterResult(allowed, reason)."""
        author = msg.get("author", "")
        text = msg.get("text", "")

        if self.is_blocked_user(msg):
            return FilterResult(False, f"Blocked user: {author}")

        if author.lower() in self._blocked_names:
            return FilterResult(False, f"Blocked name: {author}")

        # Allow-list takes priority over keyword blocks
        for pat in self._allow_patterns:
            if pat.search(text):
                return FilterResult(True, "")

        for pat in self._keyword_patterns:
            if pat.search(text):
                return FilterResult(False, f"Keyword filter: {pat.pattern}")

        return FilterResult(True, "")

    def filter_messages(self, messages: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Return (allowed_messages, blocked_messages).
        Blocked messages include a 'filter_reason' key.
        """
        allowed, blocked = [], []
        for msg in messages:
            result = self.check(msg)
            if result.allowed:
                allowed.append(msg)
            else:
                msg = dict(msg)
                msg["filter_reason"] = result.reason
                blocked.append(msg)
        return allowed, blocked


# The Streamlit app keeps one in session_state; every change is saved to `path`.
def make_default_filter(path: str | Path | None = DEFAULT_FILTER_FILE) -> ChatFilter:
    f = ChatFilter(path)
    try:
        if f.load():
            return f
    except (OSError, ValueError, re.error):
        pass  # unreadable file: start from the defaults below (the next save overwrites it)
    f.add_block_pattern(r"(?:https?://|www\.)\S+")  # URLs
    return f
