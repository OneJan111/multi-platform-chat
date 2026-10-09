"""
Bilibili Live integration using the bilibili-api-python library and direct HTTP.

bilibili-api-python uses asyncio; we run coroutines via asyncio.run() helpers
so they work seamlessly inside Streamlit's synchronous execution model.
"""
from __future__ import annotations

import asyncio
import base64
import re
import time
from collections import deque
from typing import Optional

import requests

from src import emotes, user_login
from src.config import BILIBILI_ROOM_ID

try:
    from bilibili_api import Credential, live, user
    BILIBILI_LIB_OK = True
except ImportError:
    BILIBILI_LIB_OK = False


def _cookie_values() -> tuple[str, str, str, str]:
    """The current user's Bilibili login (per browser session, see user_login)."""
    c = user_login.get("bilibili")
    return (c.get("SESSDATA", ""), c.get("bili_jct", ""), c.get("buvid3", ""), c.get("DedeUserID", ""))


def has_login_credentials() -> bool:
    return bool(_cookie_values()[0])


def parse_room_id(text: str) -> str:
    """Accept a room ID, a room URL such as https://live.bilibili.com/21452505, or a b23.tv share link."""
    text = (text or "").strip()
    short = re.search(r"(?:https?://)?b23\.tv/[\w-]+", text)
    if short:
        text = _resolve_short_link(short.group(0))
    m = (
        re.search(r"live\.bilibili\.com/(?:h5/|blanc/)?(\d+)", text)
        or re.search(r"bilibili\.com/blackboard/live/[^?#]*\?(?:[^#]*&)?cid=(\d+)", text)
        or re.fullmatch(r"(\d+)", text)
    )
    return m.group(1) if m else ""


_short_links: dict[str, str] = {}


def _resolve_short_link(url: str) -> str:
    """b23.tv links (the app's Share button) redirect to the real live.bilibili.com URL."""
    if url in _short_links:
        return _short_links[url]
    target = url if url.startswith(("http://", "https://")) else "https://" + url
    try:
        resp = requests.head(target, allow_redirects=True, timeout=5,
                             headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException:
        return ""
    if len(_short_links) > 256:
        _short_links.clear()
    _short_links[url] = resp.url
    return resp.url


def _credential(values: Optional[tuple[str, str, str, str]] = None) -> "Credential":
    sessdata, bili_jct, buvid3, dedeuserid = values or _cookie_values()
    return Credential(
        sessdata=sessdata or None,
        bili_jct=bili_jct or None,
        buvid3=buvid3 or None,
        dedeuserid=dedeuserid or None,
    )


def _run(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── Room info ──────────────────────────────────────────────────────────────────

def get_room_info(room_id: str = "") -> dict:
    """Return live room status, title, viewer count, etc."""
    rid = room_id or BILIBILI_ROOM_ID
    if not rid:
        return {}
    if not BILIBILI_LIB_OK:
        return _get_room_info_http(rid)
    try:
        room = live.LiveRoom(room_display_id=int(rid), credential=_credential())
        info = _run(room.get_room_play_info())
        room_info = _run(room.get_room_info())
        live_status = info.get("live_status", 0)
        room_data = room_info.get("room_info", {})
        anchor_data = room_info.get("anchor_info", {}).get("base_info", {})
        return {
            "room_id": rid,
            "title": room_data.get("title", ""),
            "cover": room_data.get("cover", ""),
            "live_status": live_status,  # 1 = live, 0 = offline, 2 = playback
            "online": room_data.get("online", 0),
            "start_time": room_data.get("live_time", ""),
            "uname": anchor_data.get("uname", ""),
            "face": anchor_data.get("face", ""),
            "area_name": room_data.get("area_name", ""),
            "parent_area_name": room_data.get("parent_area_name", ""),
        }
    except Exception:
        return _get_room_info_http(rid)


def _get_room_info_http(room_id: str) -> dict:
    """Fallback HTTP call to Bilibili API without library."""
    try:
        url = f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}"
        resp = requests.get(url, timeout=5)
        data = resp.json().get("data", {})
        return {
            "room_id": room_id,
            "title": data.get("title", ""),
            "cover": data.get("user_cover", ""),
            "live_status": data.get("live_status", 0),
            "online": data.get("online", 0),
            "start_time": data.get("live_time", ""),
            "uname": "",
            "area_name": data.get("area_name", ""),
            "parent_area_name": data.get("parent_area_name", ""),
        }
    except Exception:
        return {}


# ── Danmaku (chat) via WebSocket listener ─────────────────────────────────────

def _yuan(coins: int) -> str:
    """Format gold coins (1000 = ¥1) as yuan."""
    return f"{coins / 1000:g}"


_GUARD_NAMES = {1: "总督", 2: "提督", 3: "舰长"}
_GUARD_ICON = "https://i0.hdslb.com/bfs/activity-plat/static/20200716/1d0c5a1b042efb59f46d4ba1286c6727/icon-guard{}.png"


def _guard_icon(level) -> str:
    try:
        level = int(level or 0)
    except (TypeError, ValueError):
        return ""
    return _GUARD_ICON.format(level) if level in _GUARD_NAMES else ""


def _guard_name(level) -> str:
    try:
        return _GUARD_NAMES.get(int(level or 0), "")
    except (TypeError, ValueError):
        return ""


def _pb_fields(buf: bytes) -> dict[int, list]:
    """Minimal protobuf wire decoder: field number -> list of raw values."""
    fields: dict[int, list] = {}
    i = 0

    def varint() -> int:
        nonlocal i
        result = shift = 0
        while True:
            b = buf[i]
            i += 1
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7

    while i < len(buf):
        key = varint()
        number, wire = key >> 3, key & 7
        if wire == 0:
            value = varint()
        elif wire == 1:
            value, i = buf[i:i + 8], i + 8
        elif wire == 2:
            size = varint()
            value, i = buf[i:i + size], i + size
        elif wire == 5:
            value, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        fields.setdefault(number, []).append(value)
    return fields


def _decode_send_gift_v2(pb: str) -> list[dict]:
    """Decode a SEND_GIFT_V2 packet into SEND_GIFT-shaped dicts (schema from blivedm)."""
    try:
        root = _pb_fields(base64.b64decode(pb))
    except Exception:
        return []

    def text(f: dict, n: int) -> str:
        return bytes(f[n][0]).decode("utf-8", "replace") if n in f else ""

    def num(f: dict, n: int) -> int:
        return f[n][0] if n in f and isinstance(f[n][0], int) else 0

    blind = None
    if 9 in root:
        b = _pb_fields(root[9][0])
        if text(b, 3):
            blind = {"original_gift_name": text(b, 3), "original_gift_price": num(b, 6)}

    gifts = []
    for raw in root.get(10, []):
        g = _pb_fields(raw)
        gifts.append({
            "uid": num(root, 1), "uname": text(root, 2), "face": text(root, 3),
            "giftId": num(g, 1), "giftName": text(g, 2), "num": num(g, 3),
            "giftType": num(g, 4), "price": num(g, 5), "total_coin": num(g, 7),
            "coin_type": text(g, 8), "tid": text(g, 9), "action": text(g, 18),
            "guard_level": num(root, 5),
            "blind_gift": blind,
        })
    return gifts


class DanmakuListener:
    """
    Starts a bilibili-api LiveDanmaku WebSocket listener in a background thread.
    Messages are accumulated in self.messages (thread-safe append).
    """

    def __init__(self, room_id: str):
        self.room_id = int(room_id)
        self.messages: list[dict] = []
        self._thread = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None
        # UID used in the WebSocket handshake; 0 means anonymous (Bilibili masks usernames).
        self.connected_uid: Optional[int] = None
        # The starting user's login, captured here: the listener thread has no Streamlit session.
        self._login = _cookie_values()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def is_anonymous(self) -> bool:
        return self.connected_uid == 0

    def start(self) -> bool:
        if not BILIBILI_LIB_OK:
            return False
        if self._running:
            return True
        import threading
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        # LiveDanmaku.disconnect() triggers the library's auto-reconnect, so cancel the task instead.
        if self._loop and self._task and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._task.cancel)
            except RuntimeError:
                pass

    def _run_loop(self):
        asyncio.run(self._listen())

    async def _listen(self):
        try:
            self._loop = asyncio.get_running_loop()
            danmaku = live.LiveDanmaku(
                room_display_id=self.room_id,
                credential=_credential(self._login),
            )

            @danmaku.on("VERIFICATION_SUCCESSFUL")
            async def on_verified(event):
                try:
                    self.connected_uid = int(danmaku.credential.dedeuserid or 0)
                except (TypeError, ValueError):
                    self.connected_uid = 0

            @danmaku.on("DANMU_MSG")
            async def on_danmu(event):
                info = event["data"]["info"]
                meta = info[0] if info and isinstance(info[0], list) else []
                emote_map, sticker = emotes.parse_danmu_emotes(meta)
                self.messages.append(
                    {
                        "id": f"bili_{time.time_ns()}",
                        "platform": "bilibili",
                        "author": info[2][1] if len(info) > 2 else "?",
                        "author_id": str(info[2][0]) if len(info) > 2 else "",
                        "is_owner": False,
                        "is_moderator": len(info) > 2 and bool(info[2][2]),
                        "is_verified": False,
                        # info[7] = the sender's 大航海 level in this room
                        "membership": _guard_name(info[7] if len(info) > 7 else 0),
                        "membership_icon": _guard_icon(info[7] if len(info) > 7 else 0),
                        "text": info[1],
                        "type": "danmaku",
                        # dm_type 1 = sticker/emoticon danmaku (big emote image)
                        "is_emoticon": len(meta) > 12 and meta[12] == 1,
                        "emotes": emote_map,
                        "sticker_url": sticker,
                        "timestamp": str(int(time.time())),
                        "avatar": "",
                        "color": meta[3] if len(meta) > 3 else 16777215,
                    }
                )

            @danmaku.on("SUPER_CHAT_MESSAGE")
            async def on_superchat(event):
                data = event["data"]["data"]
                self.messages.append(
                    {
                        "id": f"bili_sc_{time.time_ns()}",
                        "platform": "bilibili",
                        "author": data.get("user_info", {}).get("uname", ""),
                        "author_id": str(data.get("uid", "")),
                        "is_owner": False,
                        "is_moderator": False,
                        "is_verified": False,
                        "membership": _guard_name(data.get("user_info", {}).get("guard_level", 0)),
                        "membership_icon": _guard_icon(data.get("user_info", {}).get("guard_level", 0)),
                        "text": f"[SC ¥{data.get('price',0)}] {data.get('message','')}",
                        "type": "superchat",
                        "timestamp": str(data.get("start_time", int(time.time()))),
                        "avatar": data.get("user_info", {}).get("face", ""),
                        "color": 16711680,
                    }
                )

            @danmaku.on("SEND_GIFT")
            async def on_gift(event):
                data = event["data"]["data"]
                if self._new_gift(data):
                    self.messages.append(self._gift_message(data))

            # Newer clients receive gifts (e.g. batched ×20 sends) as protobuf.
            @danmaku.on("SEND_GIFT_V2")
            async def on_gift_v2(event):
                for data in _decode_send_gift_v2(event["data"]["data"].get("pb", "")):
                    if self._new_gift(data):
                        self.messages.append(self._gift_message(data))

            @danmaku.on("COMBO_SEND")
            async def on_combo_gift(event):
                self.messages.append(self._gift_message(event["data"]["data"], combo=True))

            # GUARD_BUY carries the list price; USER_TOAST_MSG (sent alongside it)
            # carries the price actually paid, e.g. discounted first-time 舰长.
            @danmaku.on("GUARD_BUY")
            async def on_guard(event):
                self._record_guard(event["data"]["data"], paid=False)

            @danmaku.on("USER_TOAST_MSG")
            async def on_guard_toast(event):
                self._record_guard(event["data"]["data"], paid=True)

            @danmaku.on("INTERACT_WORD")
            async def on_enter(event):
                data = event["data"]["data"]
                if data.get("msg_type") == 1:
                    self.messages.append(
                        {
                            "id": f"bili_enter_{time.time_ns()}",
                            "platform": "bilibili",
                            "author": data.get("uname", ""),
                            "author_id": str(data.get("uid", "")),
                            "is_owner": False,
                            "is_moderator": False,
                            "is_verified": False,
                            "text": "entered the room",
                            "type": "enter",
                            "timestamp": str(int(time.time())),
                            "avatar": "",
                            "color": 8421504,
                        }
                    )

            if not self._running:
                return
            self._task = asyncio.ensure_future(danmaku.connect())
            await self._task
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            self._running = False

    def _new_gift(self, data: dict) -> bool:
        """Drop the duplicate when a gift arrives as both SEND_GIFT and SEND_GIFT_V2."""
        tid = str(data.get("tid") or "")
        if not tid:
            return True
        seen = self.__dict__.setdefault("_seen_tids", deque(maxlen=500))
        if tid in seen:
            return False
        seen.append(tid)
        return True

    @staticmethod
    def _gift_message(data: dict, combo: bool = False) -> dict:
        """Normalize Bilibili's individual and combo gift packet formats.

        total_coin is what the viewer actually paid (discounted unit price × num,
        or blind-box price × num); price is the list unit price (or, for blind
        boxes, the unit value of the gift that came out of the box).
        """
        num = int(data.get("num") or 1)
        price_coins = data.get("combo_total_coin") if combo else data.get("total_coin")
        if not price_coins:
            price_coins = data.get("total_coin") or 0
        if not price_coins and data.get("discount_price"):
            price_coins = data["discount_price"] * num
        if data.get("coin_type"):
            paid = data["coin_type"] == "gold"
        elif data.get("gift_type") is not None:
            paid = str(data["gift_type"]) == "1"
        else:
            paid = price_coins > 0
        price = ""
        if paid and price_coins:
            price = f" (¥{_yuan(price_coins)}"
            value_coins = 0 if combo else (data.get("price") or 0) * num
            blind = data.get("blind_gift") if not combo else None
            if isinstance(blind, dict) and blind.get("original_gift_name"):
                price += f" via {blind['original_gift_name']}"
                if value_coins:
                    price += f", worth ¥{_yuan(value_coins)}"
            elif value_coins > price_coins:
                price += f", list ¥{_yuan(value_coins)}"
            price += ")"
        gift_name = data.get("giftName") or data.get("gift_name") or ""
        count = data.get("combo_num") or data.get("num") or data.get("gift_num") or 1
        msg = DanmakuListener._gift_msg(
            data.get("uname", ""), data.get("uid", ""), data.get("face", ""),
            f"🎁 {gift_name} ×{count}{price}", free=not paid,
        )
        msg["membership"] = _guard_name(data.get("guard_level"))
        msg["membership_icon"] = _guard_icon(data.get("guard_level"))
        return msg

    @staticmethod
    def _guard_text(data: dict, paid_coins: int, list_coins: int) -> str:
        name = data.get("gift_name") or data.get("role_name") or ""
        unit = data.get("unit") or ""
        text = f"🎁 {name} ×{data.get('num', 1)}{unit} (¥{_yuan(paid_coins)}"
        if list_coins > paid_coins:
            text += f", list ¥{_yuan(list_coins)}"
        return text + ")"

    def _record_guard(self, data: dict, paid: bool) -> None:
        """Merge the GUARD_BUY (list price) / USER_TOAST_MSG (paid price) pair."""
        num = max(int(data.get("num", 1) or 1), 1)
        coins = (data.get("price") or 0) * num
        key = (str(data.get("uid", "")), data.get("guard_level"))
        now = time.time()
        self._guards = {k: v for k, v in getattr(self, "_guards", {}).items() if now - v["at"] < 30}
        entry = self._guards.get(key)
        if entry is None:
            msg = self._gift_msg(data.get("username", ""), data.get("uid", ""), "", "")
            msg["membership"] = _guard_name(data.get("guard_level"))
            msg["membership_icon"] = _guard_icon(data.get("guard_level"))
            entry = self._guards[key] = {"at": now, "msg": msg, "data": dict(data), "paid": None, "list": None}
            self.messages.append(msg)
        elif entry["paid" if paid else "list"] is not None:
            return  # duplicate packet
        entry["paid" if paid else "list"] = coins
        entry["data"].update({k: v for k, v in data.items() if v not in (None, "")})
        paid_coins = entry["paid"] if entry["paid"] is not None else entry["list"]
        # Mutate in place so a toast arriving after GUARD_BUY corrects the shown price.
        entry["msg"]["text"] = self._guard_text(entry["data"], paid_coins, entry["list"] or 0)

    @staticmethod
    def _gift_msg(author: str, uid, avatar: str, text: str, free: bool = False) -> dict:
        return {
            "id": f"bili_gift_{time.time_ns()}",
            "platform": "bilibili",
            "author": author,
            "author_id": str(uid),
            "is_owner": False,
            "is_moderator": False,
            "is_verified": False,
            "text": text,
            "type": "gift",
            "free": free,  # silver-coin gifts cost nothing; shown but not announced
            "timestamp": str(int(time.time())),
            "avatar": avatar,
            "color": 16753920,
        }

    def pop_messages(self) -> list[dict]:
        """Return and clear the accumulated messages."""
        msgs = list(self.messages)
        self.messages.clear()
        return msgs


# ── Send danmaku ───────────────────────────────────────────────────────────────

def send_danmaku(room_id: str, message: str) -> bool:
    """Send a danmaku message to the live room."""
    if not BILIBILI_LIB_OK:
        return False
    try:
        room = live.LiveRoom(room_display_id=int(room_id), credential=_credential())
        _run(room.send_danmaku(live.Danmaku(text=message)))
        return True
    except Exception:
        return False


# ── Moderation (block user) ────────────────────────────────────────────────────

def block_user(room_id: str, uid: int, hours: int = -1) -> tuple[bool, str]:
    """Mute a user in the live room. hours: -1 = permanent, 0 = until this stream ends, else 1–720.

    Needs a logged-in account that is the room owner or a room admin.
    """
    if not BILIBILI_LIB_OK:
        return False, "bilibili-api-python is not installed."
    if not str(uid).strip() or str(uid).strip() == "0":
        return False, "Bilibili hid this user's ID — log in (🍪 Cookies tab) and restart the Bilibili listener."
    sessdata, bili_jct, _, _ = _cookie_values()
    if not sessdata or not bili_jct:
        return False, "Not logged in to Bilibili — import cookies in the 🍪 Cookies tab."
    try:
        room = live.LiveRoom(room_display_id=int(room_id), credential=_credential())
        _run(room.ban_user(uid=int(uid), hour=int(hours)))
        return True, ""
    except Exception as exc:
        return False, str(exc) or type(exc).__name__


# ── Follower / viewer stats ────────────────────────────────────────────────────

def get_user_stats(uid: int) -> dict:
    """Return follower count etc. for a Bilibili UID."""
    if not BILIBILI_LIB_OK:
        return {}
    try:
        u = user.User(uid=uid, credential=_credential())
        rel = _run(u.get_relation_info())
        info = _run(u.get_user_info())
        return {
            "name": info.get("name", ""),
            "face": info.get("face", ""),
            "followers": rel.get("follower", 0),
            "following": rel.get("following", 0),
            "level": info.get("level", 0),
        }
    except Exception:
        return {}
