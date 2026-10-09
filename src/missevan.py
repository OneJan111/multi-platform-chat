"""MissEvan (猫耳FM) live rooms: room status, a chat listener (no login needed) and sending chat (login cookies)."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
_API = "https://fm.missevan.com/api"
_WS_URL = "wss://im.missevan.com/ws?room_id={room_id}"
_HEARTBEAT = "\u2764\ufe0f"  # the site's keep-alive frame is literally "❤️"
_HEARTBEAT_EVERY = 25
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def parse_room_id(text: str) -> str:
    """Accept a room ID or a room URL such as https://fm.missevan.com/live/869215180."""
    text = (text or "").strip()
    m = re.search(r"missevan\.com/live/(\d+)", text) or re.fullmatch(r"(\d+)", text)
    return m.group(1) if m else ""


def parse_cookie_string(raw: str) -> dict[str, str]:
    """'a=1; b=2' (as copied from browser dev tools) -> {"a": "1", "b": "2"}."""
    cookies = {}
    for part in (raw or "").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            cookies[name.strip()] = value.strip()
    return cookies


def login_cookies() -> dict[str, str]:
    return parse_cookie_string(os.getenv("MISSEVAN_COOKIE", ""))


def has_login() -> bool:
    return bool(login_cookies())


def _session(cookies: Optional[dict[str, str]] = None) -> requests.Session:
    """Session with the saved login cookies (if any); /api/user/info adds the FM_SESS cookies the chat server needs."""
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Referer": "https://fm.missevan.com/", "Origin": "https://fm.missevan.com"})
    for name, value in (login_cookies() if cookies is None else cookies).items():
        s.cookies.set(name, value, domain=".missevan.com")
    s.get(f"{_API}/user/info", timeout=10)
    return s


def verify_login(cookies: Optional[dict[str, str]] = None) -> dict:
    """Who the cookies belong to: {"is_login", "username", "user_id"} (+ "error" on failure)."""
    try:
        s = _session(cookies)
        user = (s.get(f"{_API}/user/info", timeout=10).json().get("info") or {}).get("user") or {}
        return {"is_login": bool(user.get("user_id")), "username": user.get("username", ""), "user_id": user.get("user_id", 0)}
    except Exception as exc:
        return {"is_login": False, "username": "", "user_id": 0, "error": str(exc)}


def save_login(cookies: dict[str, str], persist: bool = False) -> None:
    """Apply the cookies (as one Cookie-header string) to the running process; also write .env when `persist`."""
    value = "; ".join(f"{k}={v}" for k, v in cookies.items())
    if persist:
        from dotenv import set_key

        _ENV_FILE.touch(exist_ok=True)
        set_key(str(_ENV_FILE), "MISSEVAN_COOKIE", value)
    os.environ["MISSEVAN_COOKIE"] = value


def send_message(room_id: str, message: str) -> tuple[bool, str]:
    """Post a chat message to a live room as the logged-in user. Returns (ok, error message)."""
    if not has_login():
        return False, "Not logged in to MissEvan — import cookies in the 🍪 Cookies tab."
    try:
        s = _session()
        body = {"room_id": int(room_id), "message": message, "uuid": str(uuid.uuid4())}
        csrf = s.cookies.get("bili_jct")
        if csrf:
            body["csrf"] = csrf
        r = s.post(f"{_API}/chatroom/message/send", json=body, headers={"Referer": f"https://fm.missevan.com/live/{room_id}"}, timeout=10)
        data = r.json()
        if data.get("code") == 0:
            return True, ""
        return False, str(data.get("info") or data.get("message") or f"HTTP {r.status_code}")
    except Exception as exc:
        return False, str(exc)


def get_room_info(room_id: str) -> dict:
    """Room title, streamer, live flag and audience size. Returns {} on failure."""
    try:
        r = requests.get(f"{_API}/v2/live/{room_id}", headers={"User-Agent": _UA}, timeout=10)
        data = r.json()
        if data.get("code") != 0:
            return {}
        info = data["info"]
        room = info.get("room", {})
        status = room.get("status", {})
        stats = room.get("statistics", {})
        open_ms = status.get("open_time") or 0
        return {
            "room_id": room.get("room_id"),
            "title": room.get("name", ""),
            "uname": room.get("creator_username", ""),
            "creator_id": room.get("creator_id"),
            "live": bool(status.get("open")),
            "online": stats.get("online", 0),
            "followers": stats.get("attention_count", 0),
            "cover": room.get("cover_url", ""),
            "start_time": datetime.fromtimestamp(open_ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if open_ms and status.get("open") else "",
        }
    except Exception:
        log.exception("MissEvan room info failed")
        return {}


def _admins(s: requests.Session, room_id: str) -> set[int]:
    try:
        d = s.get(f"{_API}/v2/chatroom/meta", params={"room_id": room_id}, timeout=10).json()
        return {a["user_id"] for a in (d.get("info") or {}).get("members", {}).get("admin", [])}
    except Exception:
        return set()


def _decode(raw) -> list:
    """Frames are text, JSON bytes, or 0x01 + 3-byte length + brotli-compressed JSON."""
    if isinstance(raw, str):
        if raw == _HEARTBEAT:
            return []
        data = json.loads(raw)
    elif raw[:1] == b"\x01":
        import brotli
        data = json.loads(brotli.decompress(raw[4:]))
    else:
        data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def _epoch(ms) -> str:
    try:
        return str(int(ms) // 1000)
    except (TypeError, ValueError):
        return str(int(time.time()))


class MissEvanListener:
    """Reads a room's chat over WebSocket in a background thread; poll with pop_messages()."""

    def __init__(self, room_id: str):
        self.room_id = str(room_id)
        self.messages: list[dict] = []
        self.connected = False
        self.error = ""
        self.online: Optional[int] = None
        self._running = False
        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._creator_id: Optional[int] = None
        self._admins: set[int] = set()
        self._seen: set[str] = set()

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        if self._running:
            return True
        try:
            import brotli  # noqa: F401
            import websocket  # noqa: F401
        except ImportError:
            self.error = "Missing packages: pip install websocket-client brotli"
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run, name=f"missevan-{self.room_id}", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        ws = self._ws
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    def pop_messages(self) -> list[dict]:
        msgs, self.messages = self.messages, []
        return msgs

    # ── internals ──────────────────────────────────────────────────────────────

    def _run(self):
        import websocket

        info = get_room_info(self.room_id)
        self._creator_id = info.get("creator_id")
        first = True
        delay = 2
        while self._running:
            try:
                s = _session()
                self._admins = _admins(s, self.room_id)
                if first:
                    self._load_history(s)
                    first = False
                cookie = "; ".join(f"{c.name}={c.value}" for c in s.cookies)
                self._ws = websocket.create_connection(
                    _WS_URL.format(room_id=self.room_id),
                    header=[f"User-Agent: {_UA}", f"Cookie: {cookie}"],
                    origin="https://fm.missevan.com",
                    timeout=5,
                )
                self._ws.send(json.dumps({"action": "join", "uuid": str(uuid.uuid4()), "type": "room", "room_id": int(self.room_id)}))
                self.connected, self.error, delay = True, "", 2
                last_beat = time.time()
                while self._running:
                    if time.time() - last_beat > _HEARTBEAT_EVERY:
                        self._ws.send(_HEARTBEAT)
                        last_beat = time.time()
                    try:
                        raw = self._ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw:
                        raise ConnectionError("connection closed")
                    for item in _decode(raw):
                        if isinstance(item, dict):
                            self._handle(item)
            except Exception as e:
                if self._running:
                    self.error = f"MissEvan chat disconnected ({e.__class__.__name__}); reconnecting…"
                    log.warning("MissEvan room %s: %s", self.room_id, e)
            finally:
                self.connected = False
                if self._ws:
                    try:
                        self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
            end = time.time() + delay
            while self._running and time.time() < end:
                time.sleep(0.5)
            delay = min(delay * 2, 60)

    def _load_history(self, s: requests.Session):
        try:
            d = s.get(f"{_API}/v2/chatroom/history/message", params={"room_id": self.room_id}, timeout=10).json()
            for h in (d.get("info") or {}).get("history") or []:
                if h.get("type") == "message":
                    msg = self._chat(h.get("msg_id", ""), h.get("user") or {}, h.get("message", ""), h.get("create_time"))
                    if msg:
                        msg["history"] = True
                        self.messages.append(msg)
        except Exception:
            log.exception("MissEvan history failed")

    def _base(self, mid: str, user: dict, text: str, mtype: str, ts) -> dict:
        uid = user.get("user_id") or 0
        return {
            "id": mid,
            "platform": "missevan",
            "author": user.get("username") or "?",
            "author_id": str(uid),
            "is_owner": bool(uid) and uid == self._creator_id,
            "is_moderator": uid in self._admins,
            "is_verified": False,
            "text": text,
            "type": mtype,
            "timestamp": _epoch(ts) if ts else str(int(time.time())),
            "avatar": user.get("iconurl", ""),
            "color": 16777215,
        }

    def _chat(self, mid: str, user: dict, text: str, ts=None) -> Optional[dict]:
        mid = f"me_{mid or time.time_ns()}"
        if mid in self._seen:
            return None
        self._seen.add(mid)
        if len(self._seen) > 4000:
            self._seen = set(list(self._seen)[-2000:])
        return self._base(mid, user, text, "danmaku", ts)

    def _handle(self, m: dict):
        kind, event = m.get("type"), m.get("event")
        if m.get("room_id") not in (None, int(self.room_id)):
            return  # site-wide broadcasts (notify:*) are about other rooms
        if kind == "message" and event == "new":
            msg = self._chat(m.get("msg_id", ""), m.get("user") or {}, m.get("message", ""))
            if msg:
                self.messages.append(msg)
        elif kind == "question" and event == "ask":
            q = m.get("content") or {}
            user = m.get("user") or q.get("user") or q
            self.messages.append(self._base(
                f"me_q_{q.get('question_id') or time.time_ns()}", user,
                f"[提问 💎{q.get('price', 0)}] {q.get('question', '')}", "superchat", q.get("created_time"),
            ))
        elif kind == "gift" and event == "send":
            g = m.get("gift") or {}
            oid = str(m.get("oid") or "").strip("0")  # some gifts carry a placeholder all-zero oid
            self.messages.append(self._base(
                f"me_gift_{oid or time.time_ns()}", m.get("user") or {},
                f"🎁 {g.get('name', '')} ×{g.get('num', 1)}", "gift", m.get("time"),
            ))
        elif kind == "member" and event == "join_queue":
            for u in m.get("queue") or []:
                if u.get("user_id"):
                    self.messages.append(self._base(f"me_enter_{time.time_ns()}", u, "entered the room", "enter", None))
        elif kind == "room" and event == "statistics":
            self.online = (m.get("statistics") or {}).get("online", self.online)
