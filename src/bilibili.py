"""
Bilibili Live integration using the bilibili-api-python library and direct HTTP.

bilibili-api-python uses asyncio; we run coroutines via asyncio.run() helpers
so they work seamlessly inside Streamlit's synchronous execution model.
"""
from __future__ import annotations

import asyncio
import re
import time
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
    """Accept a room ID or a room URL such as https://live.bilibili.com/21452505."""
    text = (text or "").strip()
    m = re.search(r"live\.bilibili\.com/(?:h5/|blanc/)?(\d+)", text) or re.fullmatch(r"(\d+)", text)
    return m.group(1) if m else ""


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
                paid = data.get("coin_type") == "gold"
                price = f" (¥{data.get('total_coin', 0) / 1000:g})" if paid and data.get("total_coin") else ""
                self.messages.append(self._gift_msg(
                    data.get("uname", ""), data.get("uid", ""), data.get("face", ""),
                    f"🎁 {data.get('giftName', '')} ×{data.get('num', 1)}{price}", free=not paid,
                ))

            @danmaku.on("GUARD_BUY")
            async def on_guard(event):
                data = event["data"]["data"]
                price = data.get("price", 0) * max(int(data.get("num", 1) or 1), 1)
                self.messages.append(self._gift_msg(
                    data.get("username", ""), data.get("uid", ""), "",
                    f"🎁 {data.get('gift_name', '')} ×{data.get('num', 1)} (¥{price / 1000:g})",
                ))

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
