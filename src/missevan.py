"""MissEvan (猫耳FM) live rooms: room status, a chat listener (no login needed) and sending chat (login cookies)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

import requests

from src import emotes, gifts, user_login
from src.config import (
    MISSEVAN_CHAT_HISTORY_URL,
    MISSEVAN_CHATROOM_META_URL,
    MISSEVAN_ROOM_INFO_URL,
    MISSEVAN_SEND_MESSAGE_URL,
    MISSEVAN_SEND_STICKER_URL,
    MISSEVAN_STICKER_LIST_URL,
    MISSEVAN_STICKER_TABS_URL,
    MISSEVAN_USER_INFO_URL,
    MISSEVAN_WEB_ORIGIN,
    MISSEVAN_WEBSOCKET_URL,
)

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
_HEARTBEAT = "\u2764\ufe0f"  # the site's keep-alive frame is literally "❤️"
_HEARTBEAT_EVERY = 25
_PRESET_KAOMOJI = (
    "_(┐「ε:)_",
    "_(:3 」∠)_ ",
    "(￣y▽￣)~*",
    "(ง •̀_•́)ง",
    " (•̀ᴗ•́)و ̑̑ ",
    "ヽ(•̀ω•́ )ゝ",
    "(,,• ₃ •,,)",
    "(｡˘•ε•˘｡) ",
    "(=ﾟωﾟ)ﾉ",
    "(○’ω’○) ",
    "(´・ω・`)",
    "ヽ(･ω･｡)ﾉ",
    "(。-`ω´-)",
    "(´・ω・`)",
    "(´・ω・)ﾉ",
    "(ﾉ･ω･)ﾉﾞ",
    "(ó㉨ò)",
    "・㉨・",
    "( ・◇・)？",
    "ヽ(*´Д｀*)ﾉ",
    "(´°̥̥̥̥̥̥̥̥ω°̥̥̥̥̥̥̥̥｀)",
    "(╭￣3￣)╭♡",
    "(☆ﾟ∀ﾟ)",
    "⁄(⁄ ⁄•⁄ω⁄•⁄ ⁄)⁄",
    "(´-ι_-｀)",
    "ಠ౪ಠ",
    "ಥ_ಥ",
    "(/≥▽≤/)",
    "ヾ (o ° ω ° O ) ノ゙",
    "╰(*°▽°*)╯",
    "o(*≧▽≦)ツ",
    ">ㅂ<",
    "ˋ▽ˊ",
    "✪ε✪",
    "✪υ✪",
    "✪ω✪",
    "눈_눈",
    ",,Ծ‸Ծ,,",
    "π__π",
    "（/TДT)/ ",
    "(｡☉౪ ⊙｡)",
    "o(*≧▽≦)ツ┏━┓",
    "<(▰˘◡˘▰)>",
    "(｡・`ω´･)",
    "ʅ(‾◡◝)",
    "（´∀｀*) ",
    "（＾∀＾）",
    " (o^∇^o)ﾉ ",
    "ヾ(=^▽^=)ノ",
    "(*￣∇￣*)",
    "(*´∇｀*)",
    "(*ﾟ▽ﾟ*)",
    "(｡･ω･)ﾉﾞ",
    "(≡ω≡．)",
    "(｀･ω･´) ",
    "(´･ω･｀) ",
    "(●´ω｀●)φ",
    "(/= _ =)/~┴┴",
    "(/\"≡ _ ≡)/~┴┴",
    "(╯‵□′)╯︵┻━┻",
    "(┙>∧<)┙へ┻┻",
    "（╯－＿－）╯╧╧",
    "(╬▔皿▔)",
    "(╬￣皿￣)凸",
    "(｀･д･´)",
    "(ノ｀Д´)ノ",
    "(ﾟ皿ﾟﾒ)",
    "(＃｀皿´)",
    "( -д-)ﾉ",
    "（°ο°）",
    "Σ( ° △ °|||)︴",
    "∑(っ °Д °;)っ",
    "(°□°；)",
    "(⊙□⊙)",
    "( ° ▽、° )",
    "⊙▂⊙",
    "ミ ﾟДﾟ彡",
    "╮(╯▽╰)╭",
    "╮(╯_╰)╭",
    "(￣▽￣\")",
    "（￣工￣lll）",
    "ᕕ( ᐛ )ᕗ",
    " ( ＿ ＿)ノ｜",
    "ㄟ( ▔, ▔ )ㄏ",
    " (*´Д｀*) ",
    "_(:з」∠)_",
    "ヽ(*´Д｀*)ﾉ",
    "(´ﾟДﾟ`)",
    "(;´Д`)",
    "(｀･ω･)",
    "(=ﾟωﾟ)=",
    "| ω・´)",
    "|-` )",
    "|д` )",
    "|ー` )",
    "|∀` )",
    "(つд⊂)",
    "(ﾟДﾟ≡ﾟДﾟ)",
    "(＾o＾)ﾉ",
    "(|||ﾟДﾟ)",
    "( ﾟ∀ﾟ)",
    "( ´∀`)",
    "(*´∀`)",
    "(*ﾟ∇ﾟ)",
    "(*ﾟーﾟ)",
    "(　ﾟ 3ﾟ)",
    "(*´д`)",
    "(・∀・)",
    "(ゝ∀･)",
    "(〃∀〃)",
    "(*ﾟ∀ﾟ*)",
    "( ﾟ∀。)",
    "( `д´)",
    "(`ε´ )",
    "(`ヮ´ )",
    "σ`∀´)",
    "ﾟ∀ﾟ)σ",
    "ﾟ ∀ﾟ)ノ",
    "(╬ﾟдﾟ)",
    "(|||ﾟдﾟ)",
    "( ﾟдﾟ)",
    "Σ( ﾟдﾟ)",
    "( ;ﾟдﾟ)",
    "( ;´д`)",
    "( ☉д⊙)",
    "(((　ﾟдﾟ)))",
    "( ` ・´)",
    "( ´д`)",
    "( -д-)",
    "( ﾉд`ﾟ)",
    "( TдT)",
    "(￣ｰ￣)",
    "(￣ . ￣)",
    "(￣皿￣)",
    "(￣艸￣)",
    "(￣︿￣)",
    "(￣︶￣)",
    "ヾ(´ωﾟ｀)",
    "(*´ω`*)",
    "(・ω・)",
    "( ´・ω)",
    "(｀・ω)",
    "(´・ω・`)",
    "(`・ω・´)",
    "( `ー´)",
    "( ´ρ`)",
    "( ﾟωﾟ)",
    "(oﾟωﾟo)",
    "(　^ω^)",
    "(｡◕∀◕｡)",
    "/( ◕‿‿◕ )\\",
    "ヾ(´ε`ヾ)",
    "(ノﾟ∀ﾟ)ノ",
    "(σﾟдﾟ)σ",
    "(σﾟ∀ﾟ)σ",
    "|дﾟ )\"",
    "(つﾟд`ﾟ)",
    "←_←",
    "→_→",
    "(|||￢ω￢)",
    "(￣﹃￣)",
)


def preset_kaomoji() -> tuple[str, ...]:
    """Preset kaomoji from MissEvan's room chat composer."""
    return _PRESET_KAOMOJI


def _missevan_message_uuid(source: Optional[uuid.UUID] = None) -> str:
    """Generate the message UUID used by the current MissEvan web client."""
    if source is None:
        node = secrets.randbits(48) | (1 << 40)
        source = uuid.uuid1(node=node, clock_seq=secrets.randbits(14))

    raw = bytearray(source.bytes)
    checksum_input = raw[:8] + b"\x03\x00" + raw[8:12]
    digest = hmac.new(
        b"d6fc3a4a06adbde89223bvefedc24fecde188aaa9161",
        checksum_input,
        hashlib.sha1,
    ).digest()
    encoded_digest = base64.b64encode(digest).decode("ascii")

    checksum = 0
    for character in encoded_digest:
        checksum = ((31 * checksum + ord(character) + 2**31) % 2**32) - 2**31
    raw[12:16] = (checksum % 2**32).to_bytes(4, "big")
    return str(uuid.UUID(bytes=bytes(raw)))


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
    """The current user's MissEvan cookies (per browser session, see user_login)."""
    return user_login.get("missevan")


def has_login() -> bool:
    return bool(login_cookies())


def _session(cookies: Optional[dict[str, str]] = None) -> requests.Session:
    """Session with the saved login cookies (if any); /api/user/info adds the FM_SESS cookies the chat server needs."""
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Referer": f"{MISSEVAN_WEB_ORIGIN}/", "Origin": MISSEVAN_WEB_ORIGIN})
    for name, value in (login_cookies() if cookies is None else cookies).items():
        s.cookies.set(name, value, domain=".missevan.com")
    s.get(MISSEVAN_USER_INFO_URL, timeout=10)
    return s


def verify_login(cookies: Optional[dict[str, str]] = None) -> dict:
    """Who the cookies belong to: {"is_login", "username", "user_id"} (+ "error" on failure)."""
    try:
        s = _session(cookies)
        user = (s.get(MISSEVAN_USER_INFO_URL, timeout=10).json().get("info") or {}).get("user") or {}
        return {"is_login": bool(user.get("user_id")), "username": user.get("username", ""), "user_id": user.get("user_id", 0)}
    except Exception as exc:
        return {"is_login": False, "username": "", "user_id": 0, "error": str(exc)}


def save_login(cookies: dict[str, str]) -> None:
    """Use these cookies for the current user only."""
    user_login.set_site("missevan", cookies)


def send_message(room_id: str, message: str) -> tuple[bool, str]:
    """Post a chat message to a live room as the logged-in user. Returns (ok, error message)."""
    cookies = login_cookies()
    if not cookies:
        return False, "Not logged in to MissEvan — import cookies in the 🍪 Cookies tab."
    try:
        s = _session(cookies)
        message_id = _missevan_message_uuid()
        body = {"room_id": int(room_id), "uuid": str(message_id), "message": message}
        csrf_token = s.cookies.get("bili_jct")
        if csrf_token:
            body["csrf"] = csrf_token
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Referer": f"{MISSEVAN_WEB_ORIGIN}/live/{room_id}",
            "X-Requested-With": "XMLHttpRequest",
        }
        r = s.post(
            MISSEVAN_SEND_MESSAGE_URL,
            json=body,
            headers=headers,
            timeout=10,
        )
        data = r.json()
        info = data.get("info")
        message_id = info.get("msg_id") if isinstance(info, dict) else None
        if (data.get("code") == 0 and isinstance(info, dict)
                and info.get("ok") == 1 and message_id):
            user = info.get("user") if isinstance(info.get("user"), dict) else {}
            user_id = user.get("user_id")
            details = f" (UID {user_id})" if user_id else ""
            return True, f"{message_id}{details}"
        error = info if isinstance(info, str) else (
            info.get("message") or info.get("error") if isinstance(info, dict) else None
        )
        if data.get("code") == 0 and isinstance(info, dict) and info.get("ok") == 1:
            return False, "MissEvan acknowledged the request without a message ID; delivery could not be verified."
        return False, str(error or data.get("message") or f"HTTP {r.status_code}")
    except Exception as exc:
        return False, str(exc)


def get_sticker_tabs(room_id: str) -> tuple[list[dict], str]:
    """Return the logged-in user's available room-sticker packages."""
    cookies = login_cookies()
    if not cookies:
        return [], "Log in to MissEvan in the 🍪 Cookies tab to load room stickers."
    try:
        response = _session(cookies).get(
            MISSEVAN_STICKER_TABS_URL, params={"room_id": int(room_id)}, timeout=10
        )
        data = response.json()
        info = data.get("info") or {}
        if data.get("code") != 0:
            return [], str(info or data.get("message") or f"HTTP {response.status_code}")
        tabs = info.get("tabs") or []
        return ([tab for tab in tabs if isinstance(tab, dict)], "")
    except Exception as exc:
        return [], str(exc)


def get_stickers(room_id: str, package_id: int) -> tuple[list[dict], str]:
    """Return stickers in a room package."""
    cookies = login_cookies()
    if not cookies:
        return [], "Log in to MissEvan in the 🍪 Cookies tab to load room stickers."
    try:
        response = _session(cookies).get(
            MISSEVAN_STICKER_LIST_URL,
            params={"room_id": int(room_id), "package_id": int(package_id)},
            timeout=10,
        )
        data = response.json()
        info = data.get("info") or {}
        if data.get("code") != 0:
            return [], str(info or data.get("message") or f"HTTP {response.status_code}")
        stickers = info.get("stickers") or []
        return ([sticker for sticker in stickers if isinstance(sticker, dict)], "")
    except Exception as exc:
        return [], str(exc)


def send_sticker(room_id: str, package_id: int, sticker_id: int) -> tuple[bool, str]:
    """Send a room sticker using MissEvan's current room-sticker API."""
    cookies = login_cookies()
    if not cookies:
        return False, "Not logged in to MissEvan — import cookies in the 🍪 Cookies tab."
    try:
        response = _session(cookies).post(
            MISSEVAN_SEND_STICKER_URL,
            json={
                "room_id": int(room_id),
                "sticker_id": int(sticker_id),
                "package_id": int(package_id),
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json; charset=UTF-8",
                "Referer": f"{MISSEVAN_WEB_ORIGIN}/live/{room_id}",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=10,
        )
        data = response.json()
        info = data.get("info")
        if data.get("code") == 0 and (not isinstance(info, dict) or info.get("ok", 1) == 1):
            return True, ""
        error = info if isinstance(info, str) else (
            info.get("message") or info.get("error") if isinstance(info, dict) else None
        )
        return False, str(error or data.get("message") or f"HTTP {response.status_code}")
    except Exception as exc:
        return False, str(exc)


def get_room_info(room_id: str) -> dict:
    """Room title, streamer, live flag and audience size. Returns {} on failure."""
    try:
        r = requests.get(MISSEVAN_ROOM_INFO_URL.format(room_id=room_id), headers={"User-Agent": _UA}, timeout=10)
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
            "cover": room.get("cover_url") or room.get("cover", ""),
            "start_time": datetime.fromtimestamp(open_ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if open_ms and status.get("open") else "",
        }
    except Exception:
        log.exception("MissEvan room info failed")
        return {}


def get_live_audio_url(room_id: str) -> str:
    """Return the current signed HLS URL for a live MissEvan room."""
    if not room_id.isdigit():
        raise ValueError("A numeric MissEvan room ID is required.")
    response = requests.get(
        MISSEVAN_ROOM_INFO_URL.format(room_id=room_id),
        headers={"User-Agent": _UA},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("code") != 0:
        raise RuntimeError(f"MissEvan room API error: {data.get('message') or data.get('code')}")
    info = data.get("info") or {}
    room = info.get("room") or {}
    if not (room.get("status") or {}).get("open"):
        raise RuntimeError("The MissEvan room is not live.")
    channel = room.get("channel") or {}
    stream_url = channel.get("hls_pull_url") or channel.get("flv_pull_url")
    if not stream_url:
        raise RuntimeError("MissEvan did not return a live audio stream URL.")
    return stream_url


def _admins(s: requests.Session, room_id: str) -> set[int]:
    try:
        d = s.get(MISSEVAN_CHATROOM_META_URL, params={"room_id": room_id}, timeout=10).json()
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


# Paid subscriptions shown in user.titles: 贵族 (site-wide noble tiers), 上神 and the room's 超粉.
_MEMBERSHIP_TITLES = {"highness": "上神", "noble": "贵族", "super_fan": "超粉"}


def _membership(user: dict) -> str:
    labels = []
    for title in user.get("titles") or []:
        kind = (title or {}).get("type", "")
        if kind in _MEMBERSHIP_TITLES:
            labels.append(title.get("name") or _MEMBERSHIP_TITLES[kind])
    return " · ".join(labels)


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
        # The starting user's login, captured here: the listener thread has no Streamlit session.
        self._cookies = login_cookies()

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
                s = _session(self._cookies)
                self._admins = _admins(s, self.room_id)
                if first:
                    self._load_history(s)
                    first = False
                cookie = "; ".join(f"{c.name}={c.value}" for c in s.cookies)
                self._ws = websocket.create_connection(
                    MISSEVAN_WEBSOCKET_URL.format(room_id=self.room_id),
                    header=[f"User-Agent: {_UA}", f"Cookie: {cookie}"],
                    origin=MISSEVAN_WEB_ORIGIN,
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
            d = s.get(MISSEVAN_CHAT_HISTORY_URL, params={"room_id": self.room_id}, timeout=10).json()
            if not isinstance(d, dict):
                log.warning("MissEvan history returned an unexpected response: %s", type(d).__name__)
                return
            info = d.get("info")
            if not isinstance(info, dict):
                log.warning("MissEvan history unavailable: %s", info)
                return
            history = info.get("history") or []
            if not isinstance(history, list):
                log.warning("MissEvan history returned an unexpected history value: %s", type(history).__name__)
                return
            for h in history:
                if not isinstance(h, dict):
                    continue
                user = h.get("user") or {}
                if not isinstance(user, dict):
                    continue
                if h.get("type") == "message":
                    msg = self._chat(
                        h.get("msg_id", ""), user,
                        h.get("message", ""), h.get("create_time"), h.get("sticker"),
                    )
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
            "membership": _membership(user),
            "text": text,
            "type": mtype,
            "timestamp": _epoch(ts) if ts else str(int(time.time())),
            "avatar": user.get("iconurl", ""),
            "color": 16777215,
        }

    def _chat(self, mid: str, user: dict, text: str, ts=None, sticker=None) -> Optional[dict]:
        mid = f"me_{mid or time.time_ns()}"
        if mid in self._seen:
            return None
        self._seen.add(mid)
        if len(self._seen) > 4000:
            self._seen = set(list(self._seen)[-2000:])
        msg = self._base(mid, user, text, "danmaku", ts)
        if isinstance(sticker, dict):
            image_url = (
                sticker.get("image_url") or sticker.get("url")
                or sticker.get("icon_url") or sticker.get("image")
            )
            image_url = emotes.safe_chat_image_url(image_url)
            if image_url:
                msg["sticker_url"] = image_url
        elif isinstance(sticker, str):
            image_url = emotes.safe_chat_image_url(sticker)
            if image_url:
                msg["sticker_url"] = image_url
        return msg

    def _handle(self, m: dict):
        kind, event = m.get("type"), m.get("event")
        if m.get("room_id") not in (None, int(self.room_id)):
            return  # site-wide broadcasts (notify:*) are about other rooms
        if kind == "message" and event in ("new", "sticker"):
            msg = self._chat(
                m.get("msg_id", ""), m.get("user") or {},
                m.get("message", ""), sticker=m.get("sticker"),
            )
            if msg:
                self.messages.append(msg)
        elif kind == "question" and event == "ask":
            q = m.get("content") or {}
            user = m.get("user") or q.get("user") or q
            self.messages.append(gifts.set_value(self._base(
                f"me_q_{q.get('question_id') or time.time_ns()}", user,
                f"[提问 💎{q.get('price', 0)}] {q.get('question', '')}", "superchat", q.get("created_time"),
            ), "💎", q.get("price")))
        elif kind == "gift" and event == "send":
            g = m.get("gift") or {}
            oid = str(m.get("oid") or "").strip("0")  # some gifts carry a placeholder all-zero oid
            num = g.get("num") or 1
            # Gift prices are in 钻石 (diamonds) per item, when MissEvan sends them.
            value = (g.get("price") or 0) * num if isinstance(g.get("price"), (int, float)) else 0
            self.messages.append(gifts.set_value(self._base(
                f"me_gift_{oid or time.time_ns()}", m.get("user") or {},
                f"🎁 {g.get('name', '')} ×{num}", "gift", m.get("time"),
            ), "💎", value) | {"gift_count": num})
        elif kind == "member" and event == "join_queue":
            for u in m.get("queue") or []:
                if u.get("user_id"):
                    self.messages.append(self._base(f"me_enter_{time.time_ns()}", u, "entered the room", "enter", None))
        elif kind == "room" and event == "statistics":
            self.online = (m.get("statistics") or {}).get("online", self.online)
