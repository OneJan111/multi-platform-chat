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
from src.config import (
    BILIBILI_ANCHOR_INFO_URL,
    BILIBILI_GARB_SEARCH_URL,
    BILIBILI_GUARD_ICON_URL,
    BILIBILI_LIVE_ORIGIN,
    BILIBILI_MASTER_INFO_URL,
    BILIBILI_POWER_RIGHTS_URL,
    BILIBILI_ROOM_ID,
    BILIBILI_ROOM_INFO_URL,
    BILIBILI_SHORT_LINK_ORIGIN,
    BILIBILI_WEB_ORIGIN,
)

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
    if url.startswith(("http://", "https://")):
        target = url
    else:
        _, separator, path = url.partition("/")
        target = BILIBILI_SHORT_LINK_ORIGIN + (f"/{path}" if separator else "")
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
        resp = requests.get(BILIBILI_ROOM_INFO_URL, params={"room_id": room_id}, timeout=5)
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
def _guard_icon(level) -> str:
    try:
        level = int(level or 0)
    except (TypeError, ValueError):
        return ""
    return BILIBILI_GUARD_ICON_URL.format(level) if level in _GUARD_NAMES else ""


def _is_red_pocket_gift(data: dict) -> bool:
    """SEND_GIFT for a 红包 purchase (gift 13000); handled with the POPULARITY_RED_POCKET_* packets."""
    return str(data.get("giftId") or data.get("gift_id") or "") == "13000" or (
        (data.get("giftName") or data.get("gift_name")) == "红包")


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


def _decode_interact_word_v2(pb: str) -> dict:
    """Decode an INTERACT_WORD_V2 packet into an INTERACT_WORD-shaped dict (schema from blivedm)."""
    try:
        f = _pb_fields(base64.b64decode(pb))
    except Exception:
        return {}

    def num(n: int) -> int:
        return f[n][0] if n in f and isinstance(f[n][0], int) else 0

    return {
        "uid": num(1),
        "uname": bytes(f[2][0]).decode("utf-8", "replace") if 2 in f else "",
        "msg_type": num(5),
        "timestamp": num(7),
    }


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
                if _is_red_pocket_gift(data):
                    self._red_pocket("gift", data)
                elif self._new_gift(data):
                    self.messages.append(self._gift_message(data))

            # Newer clients receive gifts (e.g. batched ×20 sends) as protobuf.
            @danmaku.on("SEND_GIFT_V2")
            async def on_gift_v2(event):
                for data in _decode_send_gift_v2(event["data"]["data"].get("pb", "")):
                    if _is_red_pocket_gift(data):
                        self._red_pocket("gift", data)
                    elif self._new_gift(data):
                        self.messages.append(self._gift_message(data))

            # 红包: NEW = bought (like a gift), START = draw opens with its contents,
            # WINNER_LIST = who grabbed what.
            @danmaku.on("POPULARITY_RED_POCKET_NEW")
            async def on_red_pocket(event):
                self._red_pocket("new", event["data"]["data"])

            @danmaku.on("POPULARITY_RED_POCKET_START")
            async def on_red_pocket_start(event):
                self._red_pocket("start", event["data"]["data"])

            @danmaku.on("POPULARITY_RED_POCKET_WINNER_LIST")
            async def on_red_pocket_winners(event):
                self._red_pocket("winners", event["data"]["data"])

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
                self._enter(event["data"]["data"])

            # Bilibili now sends room entries as protobuf; the JSON INTERACT_WORD no longer arrives.
            @danmaku.on("INTERACT_WORD_V2")
            async def on_enter_v2(event):
                self._enter(_decode_interact_word_v2(event["data"]["data"].get("pb", "")))

            if not self._running:
                return
            self._task = asyncio.ensure_future(danmaku.connect())
            await self._task
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            self._running = False

    def _enter(self, data: dict) -> None:
        """Record a viewer entering the room (msg_type 1); other interactions are follows/shares."""
        if data.get("msg_type") != 1:
            return
        # Don't list the same viewer twice if one entry arrives as both INTERACT_WORD and _V2.
        key = (data.get("uid"), data.get("uname"), data.get("timestamp"))
        recent = self.__dict__.setdefault("_recent_enters", [])
        if key in recent:
            return
        recent.append(key)
        del recent[:-50]
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

    def _red_pocket(self, kind: str, data: dict) -> None:
        """Track a 红包 from purchase to draw.

        The purchase (POPULARITY_RED_POCKET_NEW, or SEND_GIFT 红包 on some clients — whichever
        arrives first) is one paid gift row; the draw's contents are added to it in place.
        The winner list is a separate free row, so it's shown but not read aloud.
        """
        now = time.time()
        lots = self.__dict__.setdefault("_red_lots", {})      # lot_id -> entry
        recent = self.__dict__.setdefault("_red_recent", {})  # sender uid -> entry from the last minute
        for d, ttl in ((lots, 1800), (recent, 60)):
            for k in [k for k, v in d.items() if now - v["at"] > ttl]:
                del d[k]
        lot = data.get("lot_id")

        if kind == "winners":
            entry = lots.get(lot)
            awards = data.get("awards") or {}
            winners = []
            for w in data.get("winner_info") or []:
                if isinstance(w, list) and len(w) > 1:
                    prize = (awards.get(str(w[3])) or {}).get("award_name", "") if len(w) > 3 else ""
                    winners.append(f"{w[1]}({prize})" if prize else str(w[1]))
            shown = "、".join(winners[:15]) + (f" 等{len(winners)}人" if len(winners) > 15 else "")
            sender = entry["msg"]["author"] if entry else ""
            msg = self._gift_msg(sender or "红包", entry["msg"]["author_id"] if entry else "",
                                 entry["msg"]["avatar"] if entry else "",
                                 f"🧧 红包开奖 · {len(winners)}人抢到: {shown}".rstrip(": "), free=True)
            msg["winners"] = [{"uid": str(w[0]), "name": w[1]} for w in data.get("winner_info") or []
                              if isinstance(w, list) and len(w) > 1]
            self.messages.append(msg)
            return

        uid = str(data.get("uid") or data.get("sender_uid") or "")
        entry = lots.get(lot) if lot else None
        if entry is None and kind != "start":
            entry = recent.get(uid)
        if entry is None and kind == "start":
            # START also follows the purchase within seconds; reuse it unless it already has a draw.
            cand = recent.get(uid)
            entry = cand if cand and cand.get("lot") in (None, lot) else None
        if entry is None:
            name = data.get("uname") or data.get("sender_name") or ""
            face = data.get("face") or data.get("sender_face") or ""
            msg = self._gift_msg(name, uid, face, "")
            entry = {"at": now, "msg": msg, "num": 1, "coins": 0, "awards": "", "lot": None}
            self.messages.append(msg)
            recent[uid] = entry
        elif kind == "gift" and entry.get("gift_seen"):
            return  # duplicate SEND_GIFT / SEND_GIFT_V2 packet

        if kind in ("new", "gift"):
            entry["num"] = int(data.get("num") or 1)
            if kind == "gift":
                entry["gift_seen"] = True
                coins = data.get("total_coin") or (data.get("price") or 0) * entry["num"]
            else:
                coins = (data.get("price") or 0) * 100 * entry["num"]  # price is in 电池 (1 = 100 gold coins)
            entry["coins"] = entry["coins"] or coins
            medal = data.get("medal_info") or {}
            guard = data.get("guard_level") or medal.get("guard_level")
            if guard:
                entry["msg"]["membership"] = _guard_name(guard)
                entry["msg"]["membership_icon"] = _guard_icon(guard)
        elif kind == "start":
            entry["awards"] = " ".join(
                f"{a.get('gift_name', '')}×{a.get('num', 1)}" for a in data.get("awards") or [] if a.get("gift_name")
            )
            if not entry["coins"] and data.get("total_price"):
                entry["coins"] = round(data["total_price"] / 0.8)  # total_price is the 80% that goes into the draw
        if lot:
            entry["lot"] = lot
            lots[lot] = entry
        text = f"🧧 红包 ×{entry['num']}"
        if entry["coins"]:
            text += f" (¥{_yuan(entry['coins'])})"
        if entry["awards"]:
            text += f" · 内含 {entry['awards']}"
        # Mutate in place: the row may already be on screen when the draw's contents arrive.
        entry["msg"]["text"] = text

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


_EMOTE_SERVER_ERR = "Bilibili's emote server returned an error. Try 🔄 Refresh in a moment."


def get_emoticons(room_id: str) -> tuple[list[dict], str]:
    """The room's emote packs usable for danmaku, plus the streamer's 充电 pack. Returns (packs, error).

    Each pack: {"name", "type", "emotes": [{"name", "unique", "url", "locked", "hint"}]}.
    `unique` is what send_emoticon posts; `locked` emotes need e.g. a fan medal, a guard or 充电.
    Without a login only the 充电 pack is listed (all locked), with the login error.
    """
    if not BILIBILI_LIB_OK:
        return [], "bilibili-api-python is not installed."
    upower, up_err = fetch_upower_emotes(room_id)
    if not has_login_credentials():
        return upower, "Not logged in to Bilibili — import cookies in the 🍪 Cookies tab."
    for attempt in range(2):  # Bilibili's emote API sometimes answers a one-off -500 服务器错误
        try:
            room = live.LiveRoom(room_display_id=int(room_id), credential=_credential())
            resp = _run(room.get_emoticons())
            break
        except Exception as exc:
            if attempt:
                if getattr(exc, "code", None) is not None:
                    print(f"[bilibili] get_emoticons failed: {exc}")
                    return upower, _EMOTE_SERVER_ERR
                return upower, str(exc) or type(exc).__name__
            time.sleep(1)
    packs = parse_emoticons(resp)
    uid, uname = _room_owner(room_id)
    # Skip ours only if Bilibili already lists *this* streamer's 充电 pack (it may list other streamers' ones).
    ours = {e["unique"] for p in upower for e in p["emotes"]}
    if not (ours and any(e["unique"] in ours for p in packs for e in p["emotes"])):
        packs = packs + upower
    else:
        up_err = ""
    garb = garb_packs_owned_by(uid, [p for p in packs if _pack_kind(p) == "garb"])
    packs = rank_packs(packs, uid, uname, garb)
    label_garb_packs(packs)
    return (packs,
            f"充电表情 couldn't be loaded: {up_err}" if up_err else "")


_GARB_RE = re.compile(r"^upower_\[(.+)_[^_\]]+\]$")


def _pack_kind(p: dict) -> str:
    """"charge" (充电), "room" (房间专属), "general" (通用) or "garb" (装扮)."""
    if p.get("type") == "upower" or any(e["unique"].startswith("upower_[UPOWER_") for e in p["emotes"]):
        return "charge"
    return {1: "general", 2: "room"}.get(p.get("type"), "garb")


def garb_name(p: dict) -> str:
    """The 装扮 the pack comes from: Bilibili's live client names its emotes `upower_[<装扮名>_<emote>]`."""
    for e in p["emotes"]:
        m = _GARB_RE.match(e["unique"])
        if m:
            return m.group(1)
    return p.get("name") or ""


_garb_owner_cache: dict[str, set[int]] = {}


def _garb_owners(name: str) -> set[int]:
    """UIDs of the streamers whose 装扮 shop items match `name` (from the items' `fan_mid`)."""
    if name in _garb_owner_cache:
        return _garb_owner_cache[name]
    owners: set[int] = set()
    try:
        resp = requests.get(BILIBILI_GARB_SEARCH_URL,
                            params={"key_word": name, "pn": 1, "ps": 20}, timeout=5,
                            headers={"User-Agent": _BROWSER_UA, "Referer": f"{BILIBILI_WEB_ORIGIN}/"})
        items = ((resp.json().get("data") or {}).get("list")) or []
    except (requests.RequestException, ValueError, AttributeError):
        return owners  # not cached: retry on the next refresh
    key = name.lower()
    for it in items:
        item_name = str(it.get("name") or "").lower()
        mid = str((it.get("properties") or {}).get("fan_mid") or "")
        if mid.isdigit() and item_name and (key in item_name or item_name in key):
            owners.add(int(mid))
    _garb_owner_cache[name] = owners
    return owners


def _garb_owner_map(packs: list[dict]) -> dict[str, set[int]]:
    """{装扮 name: streamer UIDs} for the given 装扮 packs, per the 装扮 shop."""
    names = {garb_name(p) for p in packs} - {"", "装扮表情"}
    if not names:
        return {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        return dict(zip(names, pool.map(_garb_owners, names)))


def garb_packs_owned_by(uid: int, packs: list[dict]) -> set[str]:
    """Names (as from garb_name) of the given 装扮 packs that the 装扮 shop says belong to `uid`."""
    if not uid:
        return set()
    return {n for n, mids in _garb_owner_map(packs).items() if uid in mids}


_up_names: dict[int, str] = {}


def _up_name(uid: int) -> str:
    """A Bilibili user's name; "" if it couldn't be fetched."""
    if uid not in _up_names:
        try:
            resp = requests.get(BILIBILI_MASTER_INFO_URL,
                                params={"uid": uid}, timeout=5, headers={"User-Agent": _BROWSER_UA})
            name = str(((resp.json().get("data") or {}).get("info") or {}).get("uname") or "")
        except (requests.RequestException, ValueError, AttributeError):
            return ""  # not cached: retry on the next refresh
        _up_names[uid] = name
    return _up_names[uid]


def label_garb_packs(packs: list[dict]) -> None:
    """Add the UP主 a 装扮 pack belongs to (per the 装扮 shop) to its name: "<装扮> · <UP主>"."""
    garb = [p for p in packs if _pack_kind(p) == "garb"]
    owners = _garb_owner_map(garb)
    for p in garb:
        ups = [n for n in (_up_name(mid) for mid in sorted(owners.get(garb_name(p), ()))) if n]
        if ups and not any(u in p["name"] for u in ups):
            p["name"] = f"{p['name']} · {' / '.join(ups)}"


def _name_tokens(uname: str) -> list[str]:
    return [t for t in re.split(r"[\s_\-・·.|/()（）【】\[\]]+", uname or "") if len(t) >= 2]


def rank_packs(packs: list[dict], uid: int = 0, uname: str = "", owned_garb: set[str] = frozenset()) -> list[dict]:
    """Mark the room owner's packs (`owner: True`) and list them first: 充电, room-exclusive, then the
    streamer's own 装扮 packs (per the 装扮 shop, or named after them); then 通用; then other 装扮 and
    other streamers' 充电 packs."""
    tokens = [t.lower() for t in _name_tokens(uname)]
    own_charge = f"upower_[UPOWER_{uid}_" if uid else None

    def rank(p):
        kind = _pack_kind(p)
        if kind == "charge":
            owner = p.get("type") == "upower" or bool(own_charge and any(
                e["unique"].startswith(own_charge) for e in p["emotes"]))
        elif kind == "garb":
            name = garb_name(p)
            owner = name in owned_garb or any(t in f"{p.get('name') or ''} {name}".lower() for t in tokens)
        else:
            owner = kind == "room"
        p["owner"] = owner
        if owner:
            return {"charge": 0, "room": 1}.get(kind, 2)
        return {"general": 3, "garb": 4}.get(kind, 5)

    return sorted(packs, key=rank)


_room_uids: dict[str, int] = {}
_room_names: dict[str, str] = {}


def _room_owner(room_id: str) -> tuple[int, str]:
    """(uid, uname) of the room's streamer; (0, "") if unknown."""
    rid = str(room_id)
    if rid not in _room_names:
        try:
            resp = requests.get(BILIBILI_ANCHOR_INFO_URL,
                                params={"roomid": rid}, timeout=5, headers={"User-Agent": _BROWSER_UA})
            info = (resp.json().get("data") or {}).get("info") or {}
            if info.get("uid"):
                _room_uids.setdefault(rid, int(info["uid"]))
                _room_names[rid] = str(info.get("uname") or "")
        except (requests.RequestException, ValueError, AttributeError, TypeError):
            pass
    return _room_owner_uid(rid), _room_names.get(rid, "")
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/126.0 Safari/537.36")


def _room_owner_uid(room_id: str) -> int:
    rid = str(room_id)
    if rid in _room_uids:
        return _room_uids[rid]
    uid = 0
    try:
        resp = requests.get(BILIBILI_ROOM_INFO_URL,
                            params={"room_id": rid}, timeout=5, headers={"User-Agent": _BROWSER_UA})
        uid = int((resp.json().get("data") or {}).get("uid") or 0)
    except (requests.RequestException, ValueError, AttributeError):
        pass
    if not uid and BILIBILI_LIB_OK:
        try:  # the library signs requests, which gets past some risk-control blocks
            info = _run(live.LiveRoom(room_display_id=int(rid), credential=_credential()).get_room_info())
            uid = int((info.get("room_info") or {}).get("uid") or 0)
        except Exception:
            pass
    if uid:
        _room_uids[rid] = uid
    return uid


def get_upower_emotes(room_id: str) -> list[dict]:
    return fetch_upower_emotes(room_id)[0]


def fetch_upower_emotes(room_id: str) -> tuple[list[dict], str]:
    """The streamer's 充电 (upower) emote pack, as a one-item pack list, and an error ("" if fine).

    The live emote API doesn't list it; the web client posts it as `upower_[UPOWER_<uid>_<name>]`.
    With a login, `locked` reflects whether this account is charging the streamer.
    An empty list with no error means the streamer has no 充电表情.
    """
    uid = _room_owner_uid(room_id)
    if not uid:
        return [], "couldn't find the streamer's UID for this room"
    c = user_login.get("bilibili")
    login = {k: c.get(k, "") for k in ("SESSDATA", "bili_jct", "buvid3", "DedeUserID") if c.get(k)}
    # Try with the login (shows what this account unlocked); if Bilibili's risk control rejects it,
    # fall back to an anonymous request so the pack is at least listed.
    err = ""
    for cookies in ([login, None] if login else [None]):
        try:
            resp = requests.get(
                BILIBILI_POWER_RIGHTS_URL, params={"up_mid": uid}, timeout=8,
                headers={"User-Agent": _BROWSER_UA, "Referer": f"{BILIBILI_LIVE_ORIGIN}/{room_id}",
                         "Origin": BILIBILI_LIVE_ORIGIN},
                cookies=cookies,
            )
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            err = f"HTTP {getattr(getattr(exc, 'response', None), 'status_code', '')} {type(exc).__name__}".strip()
            continue
        if data.get("code") != 0:
            err = f"Bilibili code {data.get('code')} {data.get('message', '')}".strip()
            continue
        packs = parse_upower_emotes(data, uid)
        if packs:
            return packs, ""
        err = ""  # a valid answer without emotes: the streamer has no 充电表情
    return [], err


def parse_upower_emotes(resp: dict, uid: int) -> list[dict]:
    rights = ((resp or {}).get("data") or {}).get("privilege_rights") or {}
    # Each charging tier lists the emote set; prefer one this account has unlocked.
    sets = [r["emote"] for _, r in sorted(rights.items()) if isinstance(r, dict) and isinstance(r.get("emote"), dict)]
    if not sets:
        return []
    chosen = next((s for s in sets if s.get("locked") is False), sets[0])
    locked = chosen.get("locked") is not False
    items, seen = [], set()
    for e in chosen.get("emojis") or []:
        name, url = str(e.get("name") or ""), emotes.safe_image_url(e.get("icon", ""))
        if not name or not url or name in seen:
            continue
        seen.add(name)
        items.append({"name": name, "unique": f"upower_[UPOWER_{uid}_{name}]", "url": url,
                      "locked": locked, "hint": "为主播充电后可用"})
    return [{"name": "充电表情", "type": "upower", "owner": True, "emotes": items}] if items else []


def parse_emoticons(resp) -> list[dict]:
    raw = resp.get("data") if isinstance(resp, dict) else resp
    packs = []
    for pkg in raw if isinstance(raw, list) else []:
        if not isinstance(pkg, dict):
            continue
        items = []
        for e in pkg.get("emoticons") or []:
            unique = str(e.get("emoticon_unique") or "")
            url = emotes.safe_image_url(e.get("url", ""))
            if not unique or not url:
                continue
            items.append({
                "name": str(e.get("emoji") or e.get("descript") or unique),
                "unique": unique,
                "url": url,
                "locked": e.get("perm", 1) != 1,
                "hint": str(e.get("unlock_show_text") or ""),
            })
        if items:
            pack = {"name": str(pkg.get("pkg_name") or ""), "type": pkg.get("pkg_type"), "emotes": items}
            packs.extend(_split_garb_pack(pack))
    return packs


def _split_garb_pack(pack: dict) -> list[dict]:
    """Bilibili may put every 装扮's emotes in one "装扮表情" pack; split it into one pack per 装扮."""
    if _pack_kind(pack) != "garb":
        return [pack]
    groups: dict[str, list[dict]] = {}
    for e in pack["emotes"]:
        m = _GARB_RE.match(e["unique"])
        groups.setdefault(m.group(1) if m else "", []).append(e)
    # Each 装扮 usually comes as its own pack, also named "装扮表情": name it after the 装扮 too.
    return [{**pack, "name": name or pack["name"], "emotes": items} for name, items in groups.items()]


def send_emoticon(room_id: str, unique: str) -> tuple[bool, str]:
    """Send one emote (sticker danmaku) from get_emoticons. Returns (ok, error)."""
    if not BILIBILI_LIB_OK:
        return False, "bilibili-api-python is not installed."
    try:
        room = live.LiveRoom(room_display_id=int(room_id), credential=_credential())
        _run(room.send_emoticon(live.Danmaku(text=unique)))
        return True, ""
    except Exception as exc:
        return False, str(exc) or type(exc).__name__

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
