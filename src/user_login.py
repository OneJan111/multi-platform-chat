"""Per-user site logins (YouTube / Bilibili / MissEvan cookies).

Each browser session keeps its own logins in Streamlit session state, so one viewer's
cookies are never used by another. To survive a page refresh or server restart, the
logins are also kept in the user's own browser as an encrypted cookie: the server holds
only the key (LOGIN_SECRET, or a generated .login_secret file), never the cookies.

Layout of the login dict:
    {"youtube": {cookie: value}, "youtube_page_id": "...",
     "bilibili": {cookie: value}, "missevan": {cookie: value}}
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

SITES = ("youtube", "bilibili", "missevan")
SESSION_KEY = "_user_logins"
COOKIE_NAME = "mpc_login"
CHUNK_SIZE = 3800           # browsers cap each cookie at ~4 KB
MAX_CHUNKS = 12
COOKIE_MAX_AGE = 60 * 60 * 24 * 180  # 180 days

_SECRET_FILE = Path(__file__).resolve().parent.parent / ".login_secret"
_local = threading.local()


# ── Current user's logins ─────────────────────────────────────────────────────

def _session_logins() -> Optional[dict]:
    """The logins dict of the Streamlit session running on this thread (None off the script thread)."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except ImportError:
        return None
    ctx = get_script_run_ctx(suppress_warning=True)
    if ctx is None:
        return None
    state = ctx.session_state
    if SESSION_KEY not in state:
        state[SESSION_KEY] = {}
    return state[SESSION_KEY]


def current() -> dict:
    """Logins of the current user: an explicit `using()` override, else the Streamlit session's."""
    override = getattr(_local, "logins", None)
    if override is not None:
        return override
    logins = _session_logins()
    return logins if logins is not None else {}


@contextmanager
def using(logins: dict) -> Iterator[None]:
    """Run code (tests, background helpers) as a given user's logins."""
    previous = getattr(_local, "logins", None)
    _local.logins = logins
    try:
        yield
    finally:
        _local.logins = previous


def get(site: str) -> dict[str, str]:
    return dict(current().get(site) or {})


def set_site(site: str, cookies: dict[str, str]) -> None:
    logins = current()
    logins[site] = {k: v for k, v in cookies.items() if v}
    if site == "youtube":
        logins.pop("youtube_page_id", None)  # a new Google login starts on its main channel
    _mark_changed(logins)


def clear_site(site: str) -> bool:
    """Forget one site's login. Returns True when something was removed."""
    logins = current()
    removed = bool(logins.pop(site, None))
    if site == "youtube":
        removed = bool(logins.pop("youtube_page_id", None)) or removed
    _mark_changed(logins)
    return removed


def youtube_page_id() -> str:
    return str(current().get("youtube_page_id") or "").strip()


def set_youtube_page_id(page_id: str) -> None:
    logins = current()
    if page_id:
        logins["youtube_page_id"] = page_id
    else:
        logins.pop("youtube_page_id", None)
    _mark_changed(logins)


def _mark_changed(logins: dict) -> None:
    logins["_changed"] = True


def take_changed() -> bool:
    """True once after the logins changed (the app then rewrites the browser cookie)."""
    return bool(current().pop("_changed", False))


def cookie_string(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def parse_cookie_string(raw: str) -> dict[str, str]:
    """Inverse of cookie_string(): 'a=1; b=2' -> {"a": "1", "b": "2"}."""
    cookies = {}
    for part in (raw or "").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            cookies[name.strip()] = value.strip()
    return cookies


# ── Encrypted browser cookie ──────────────────────────────────────────────────

def _fernet():
    from cryptography.fernet import Fernet

    secret = os.getenv("LOGIN_SECRET", "").strip()
    if not secret:
        if not _SECRET_FILE.exists():
            _SECRET_FILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")
            try:
                _SECRET_FILE.chmod(0o600)
            except OSError:
                pass
        secret = _SECRET_FILE.read_text(encoding="utf-8").strip()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encode(logins: dict) -> str:
    """Encrypt the logins into a cookie-safe token ("" when there is nothing to keep)."""
    data = {k: v for k, v in logins.items() if not k.startswith("_") and v}
    if not data:
        return ""
    raw = zlib.compress(json.dumps(data, separators=(",", ":")).encode())
    return _fernet().encrypt(raw).decode()


def decode(token: str) -> dict:
    """Inverse of encode(); {} when the token is missing, tampered with or from another key."""
    if not token:
        return {}
    try:
        data = json.loads(zlib.decompress(_fernet().decrypt(token.encode())))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    logins = {s: {str(k): str(v) for k, v in data[s].items()}
              for s in SITES if isinstance(data.get(s), dict)}
    if isinstance(data.get("youtube_page_id"), str):
        logins["youtube_page_id"] = data["youtube_page_id"]
    return logins


def split_token(token: str) -> list[str]:
    return [token[i:i + CHUNK_SIZE] for i in range(0, len(token), CHUNK_SIZE)]


def join_cookies(cookies) -> str:
    """Reassemble the token from request cookies {mpc_login_n, mpc_login_0, …}."""
    try:
        count = int(cookies.get(f"{COOKIE_NAME}_n", "0"))
    except (TypeError, ValueError):
        return ""
    if not 0 < count <= MAX_CHUNKS:
        return ""
    parts = [cookies.get(f"{COOKIE_NAME}_{i}", "") for i in range(count)]
    return "".join(parts) if all(parts) else ""


def cookie_script(logins: dict) -> str:
    """JavaScript that stores the encrypted logins in the browser (or deletes them when empty)."""
    chunks = split_token(encode(logins))
    if len(chunks) > MAX_CHUNKS:
        chunks = []
    values = {f"{COOKIE_NAME}_n": str(len(chunks)) if chunks else ""}
    values.update({f"{COOKIE_NAME}_{i}": c for i, c in enumerate(chunks)})
    for i in range(len(chunks), MAX_CHUNKS):
        values[f"{COOKIE_NAME}_{i}"] = ""
    return (
        "<script>(function(){var v=" + json.dumps(values) + ";"
        "var sec=location.protocol==='https:'?';Secure':'';"
        "for(var k in v){document.cookie=k+'='+v[k]+';path=/;SameSite=Strict'+sec+"
        f"(v[k]?';max-age={COOKIE_MAX_AGE}':';max-age=0');}}}})();</script>"
    )
