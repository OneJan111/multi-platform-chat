"""Chat filter module: keyword/regex filters and per-user blocklist."""
from __future__ import annotations

import re
from typing import NamedTuple


class FilterResult(NamedTuple):
    allowed: bool
    reason: str  # empty when allowed


class ChatFilter:
    def __init__(self):
        self._blocked_users: set[str] = set()      # author_id
        self._blocked_names: set[str] = set()       # lower-case display name
        self._keyword_patterns: list[re.Pattern] = []
        self._allow_patterns: list[re.Pattern] = [] # always allow if matched

    # ── User blocklist ─────────────────────────────────────────────────────────

    def block_user(self, author_id: str) -> None:
        self._blocked_users.add(author_id)

    def unblock_user(self, author_id: str) -> None:
        self._blocked_users.discard(author_id)

    def block_name(self, name: str) -> None:
        self._blocked_names.add(name.lower())

    def unblock_name(self, name: str) -> None:
        self._blocked_names.discard(name.lower())

    @property
    def blocked_users(self) -> set[str]:
        return set(self._blocked_users)

    # ── Keyword / regex patterns ───────────────────────────────────────────────

    def add_block_pattern(self, pattern: str, flags: int = re.IGNORECASE) -> None:
        self._keyword_patterns.append(re.compile(pattern, flags))

    def remove_block_pattern(self, pattern: str) -> None:
        self._keyword_patterns = [
            p for p in self._keyword_patterns if p.pattern != pattern
        ]

    def add_allow_pattern(self, pattern: str, flags: int = re.IGNORECASE) -> None:
        self._allow_patterns.append(re.compile(pattern, flags))

    @property
    def block_patterns(self) -> list[str]:
        return [p.pattern for p in self._keyword_patterns]

    # ── Evaluate ───────────────────────────────────────────────────────────────

    def check(self, msg: dict) -> FilterResult:
        """Return FilterResult(allowed, reason)."""
        author_id = msg.get("author_id", "")
        author = msg.get("author", "")
        text = msg.get("text", "")

        if author_id in self._blocked_users:
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


# Shared singleton – the Streamlit app keeps it in session_state
def make_default_filter() -> ChatFilter:
    f = ChatFilter()
    # sensible defaults
    f.add_block_pattern(r"(?:https?://|www\.)\S+")  # URLs
    return f
