import base64
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.bilibili import DanmakuListener, _decode_interact_word_v2, _decode_send_gift_v2


class BilibiliRoomInfoTests(unittest.TestCase):
    def test_room_info_falls_back_to_user_cover(self):
        from src import bilibili as bili

        room = Mock()
        room.get_room_play_info.return_value = object()
        room.get_room_info.return_value = object()
        with patch.object(bili, "BILIBILI_LIB_OK", True), \
             patch.object(bili, "live", SimpleNamespace(LiveRoom=Mock(return_value=room))), \
             patch.object(bili, "_credential"), \
             patch.object(bili, "_run", side_effect=[
                 {"live_status": 1},
                 {"room_info": {"title": "Room", "cover": None,
                                "user_cover": "https://i0.hdslb.com/bfs/live/cover.jpg"}},
             ]):
            info = bili.get_room_info("123")

        self.assertEqual(info["cover"], "https://i0.hdslb.com/bfs/live/cover.jpg")


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(number: int, value) -> bytes:
    if isinstance(value, int):
        return _varint(number << 3) + _varint(value)
    if isinstance(value, str):
        value = value.encode()
    return _varint(number << 3 | 2) + _varint(len(value)) + value


class BilibiliGiftTests(unittest.TestCase):
    def test_normalizes_send_gift_packet(self):
        message = DanmakuListener._gift_message({
            "uname": "viewer",
            "uid": 42,
            "face": "https://example.com/avatar.jpg",
            "giftName": "花",
            "num": 2,
            "coin_type": "gold",
            "total_coin": 2000,
        })

        self.assertEqual(message["type"], "gift")
        self.assertEqual(message["text"], "🎁 花 ×2 (¥2)")
        self.assertEqual(message["gift_count"], 2)
        self.assertEqual(message["author"], "viewer")
        self.assertFalse(message["free"])

    def test_normalizes_combo_send_packet(self):
        message = DanmakuListener._gift_message({
            "uname": "viewer",
            "uid": 42,
            "gift_name": "辣条",
            "combo_num": 5,
            "gift_type": 1,
            "combo_total_coin": 5000,
        }, combo=True)

        self.assertEqual(message["type"], "gift")
        self.assertEqual(message["text"], "🎁 辣条 ×5 (¥5)")
        self.assertEqual(message["gift_count"], 5)
        self.assertFalse(message["free"])

    def test_combo_send_treating_gift_is_paid_without_coin_type(self):
        message = DanmakuListener._gift_message({
            "action": "投喂",
            "uname": "viewer",
            "uid": 42,
            "gift_name": "牛哇牛哇",
            "gift_num": 0,
            "combo_num": 2,
            "combo_total_coin": 200,
        }, combo=True)

        self.assertEqual(message["text"], "🎁 牛哇牛哇 ×2 (¥0.2)")
        self.assertFalse(message["free"])

    def test_silver_coin_gift_is_not_marked_paid(self):
        message = DanmakuListener._gift_message({
            "uname": "viewer",
            "giftName": "小心心",
            "num": 1,
            "coin_type": "silver",
        })

        self.assertTrue(message["free"])

    def test_discounted_gift_shows_paid_and_list_price(self):
        message = DanmakuListener._gift_message({
            "uname": "viewer",
            "giftName": "小花花",
            "num": 2,
            "coin_type": "gold",
            "price": 1000,
            "discount_price": 800,
            "total_coin": 1600,
        })

        self.assertEqual(message["text"], "🎁 小花花 ×2 (¥1.6, list ¥2)")
        self.assertEqual((message["currency"], message["value"]), ("¥", 1.6))

    def test_blind_gift_shows_box_price_and_value(self):
        message = DanmakuListener._gift_message({
            "uname": "viewer",
            "giftName": "浪漫城堡",
            "num": 1,
            "coin_type": "gold",
            "price": 22330000,
            "total_coin": 15000,
            "blind_gift": {"original_gift_name": "心动盲盒", "original_gift_price": 15000},
        })

        self.assertEqual(message["text"], "🎁 浪漫城堡 ×1 (¥15 via 心动盲盒, worth ¥22330)")

    def test_guard_toast_corrects_list_price_to_paid_price(self):
        listener = DanmakuListener.__new__(DanmakuListener)
        listener.messages = []
        listener._record_guard({"uid": 7, "username": "fan", "guard_level": 3, "num": 1,
                                "price": 198000, "gift_name": "舰长"}, paid=False)
        listener._record_guard({"uid": 7, "username": "fan", "guard_level": 3, "num": 1,
                                "price": 138000, "role_name": "舰长", "unit": "月"}, paid=True)

        self.assertEqual(len(listener.messages), 1)
        self.assertEqual(listener.messages[0]["text"], "🎁 舰长 ×1月 (¥138, list ¥198)")
        self.assertEqual(listener.messages[0]["value"], 138.0)

    def test_guard_toast_alone_is_recorded(self):
        listener = DanmakuListener.__new__(DanmakuListener)
        listener.messages = []
        listener._record_guard({"uid": 7, "username": "fan", "guard_level": 3, "num": 1,
                                "price": 198000, "role_name": "舰长", "unit": "月"}, paid=True)

        self.assertEqual(listener.messages[0]["text"], "🎁 舰长 ×1月 (¥198)")

    def test_red_pocket_purchase_draw_and_winners(self):
        listener = DanmakuListener.__new__(DanmakuListener)
        listener.messages = []
        listener._red_pocket("new", {"lot_id": 5, "uid": 7, "uname": "boss", "num": 1, "price": 20,
                                     "gift_name": "红包", "medal_info": {"guard_level": 3}})
        listener._red_pocket("gift", {"uid": 7, "uname": "boss", "giftId": 13000, "num": 1, "total_coin": 2000})
        listener._red_pocket("start", {"lot_id": 5, "sender_uid": 7, "sender_name": "boss", "total_price": 1600,
                                       "awards": [{"gift_name": "打call", "num": 2}, {"gift_name": "牛哇", "num": 3}]})
        listener._red_pocket("winners", {"lot_id": 5, "winner_info": [[1, "a", 0, 31212], [2, "b", 0, 31214]],
                                         "awards": {"31212": {"award_name": "打call"}, "31214": {"award_name": "牛哇"}}})

        self.assertEqual(len(listener.messages), 2)
        bought, winners = listener.messages
        self.assertEqual(bought["text"], "🧧 红包 ×1 (¥2) · 内含 打call×2 牛哇×3")
        self.assertEqual(bought["value"], 2.0)
        self.assertNotIn("value", winners)
        self.assertFalse(bought["free"])
        self.assertEqual(bought["membership"], "舰长")
        self.assertEqual(winners["author"], "boss")
        self.assertEqual(winners["text"], "🧧 红包开奖 · 2人抢到: a(打call)、b(牛哇)")
        self.assertTrue(winners["free"])

    def test_red_pocket_start_alone_uses_draw_value(self):
        listener = DanmakuListener.__new__(DanmakuListener)
        listener.messages = []
        listener._red_pocket("start", {"lot_id": 9, "sender_uid": 7, "sender_name": "boss", "total_price": 1600,
                                       "awards": []})

        self.assertEqual(listener.messages[0]["text"], "🧧 红包 ×1 (¥2)")

    def test_send_gift_v2_protobuf_batch(self):
        item = b"".join([
            _field(1, 31039), _field(2, "牛哇牛哇"), _field(3, 20), _field(4, 0),
            _field(5, 100), _field(7, 2000), _field(8, "gold"), _field(9, "tid-1"),
            _field(18, "投喂"),
        ])
        pb = b"".join([_field(1, 42), _field(2, "viewer"), _field(3, "https://x/face.jpg"),
                       _field(10, item)])

        gifts = _decode_send_gift_v2(base64.b64encode(pb).decode())

        self.assertEqual(len(gifts), 1)
        self.assertEqual(gifts[0]["uname"], "viewer")
        self.assertEqual(gifts[0]["tid"], "tid-1")
        message = DanmakuListener._gift_message(gifts[0])
        self.assertEqual(message["text"], "🎁 牛哇牛哇 ×20 (¥2)")
        self.assertFalse(message["free"])

    def test_same_gift_from_v1_and_v2_is_deduplicated(self):
        listener = DanmakuListener.__new__(DanmakuListener)
        self.assertTrue(listener._new_gift({"tid": "abc"}))
        self.assertFalse(listener._new_gift({"tid": "abc"}))
        self.assertTrue(listener._new_gift({}))

    def test_invalid_protobuf_is_ignored(self):
        self.assertEqual(_decode_send_gift_v2("not base64!!"), [])
        self.assertEqual(_decode_interact_word_v2("not base64!!"), {})

    def test_interact_word_v2_entry_is_recorded_once(self):
        pb = b"".join([_field(1, 42), _field(2, "观众"), _field(5, 1), _field(7, 1760000000)])
        data = _decode_interact_word_v2(base64.b64encode(pb).decode())
        self.assertEqual(data, {"uid": 42, "uname": "观众", "msg_type": 1, "timestamp": 1760000000})

        listener = DanmakuListener.__new__(DanmakuListener)
        listener.messages = []
        listener._enter(data)
        listener._enter(dict(data))  # same entry again (e.g. V1 + V2)
        listener._enter({**data, "msg_type": 2})  # a follow, not an entry
        self.assertEqual([(m["type"], m["author"]) for m in listener.messages], [("enter", "观众")])

    def test_gift_from_guard_member_carries_membership(self):
        message = DanmakuListener._gift_message({
            "uname": "viewer", "giftName": "花", "num": 1, "coin_type": "gold",
            "total_coin": 1000, "guard_level": 3,
        })

        self.assertEqual(message["membership"], "舰长")
        self.assertTrue(message["membership_icon"].endswith("/icon-guard3.png"))

    def test_badge_url_allows_only_known_image_cdns(self):
        from src.emotes import safe_badge_url
        self.assertTrue(safe_badge_url("https://yt3.ggpht.com/x"))
        self.assertTrue(safe_badge_url("https://i0.hdslb.com/x.png"))
        self.assertTrue(safe_badge_url("https://lh3.googleusercontent.com/x"))
        self.assertEqual(safe_badge_url("http://yt3.ggpht.com/x"), "")
        self.assertEqual(safe_badge_url("https://evilggpht.com/x"), "")
        self.assertEqual(safe_badge_url("javascript:alert(1)"), "")
        self.assertEqual(safe_badge_url(None), "")

    def test_guard_name(self):
        from src.bilibili import _guard_name
        self.assertEqual([_guard_name(n) for n in (0, 1, 2, 3, None, "x")],
                         ["", "总督", "提督", "舰长", "", ""])


class MissEvanMembershipTests(unittest.TestCase):
    def test_paid_titles_become_membership(self):
        from src.missevan import _membership
        user = {"titles": [
            {"type": "level", "level": 30},
            {"type": "medal", "name": "粉丝牌", "level": 5},
            {"type": "noble", "name": "大咖", "level": 4},
            {"type": "super_fan"},
        ]}

        self.assertEqual(_membership(user), "大咖 · 超粉")
        self.assertEqual(_membership({}), "")


class BilibiliEmoticonTests(unittest.TestCase):
    def test_room_upower_pack_kept_when_another_streamers_is_listed(self):
        from unittest import mock
        from src import bilibili as b
        ours = [{"name": "充电表情", "type": "upower", "emotes": [
            {"name": "盯", "unique": "upower_[UPOWER_42_盯]", "url": "u", "locked": True, "hint": ""}]}]
        other = [{"name": "别人的充电表情", "type": 2, "emotes": [
            {"name": "x", "unique": "upower_[UPOWER_7_x]", "url": "u", "locked": False, "hint": ""}]}]
        if not b.BILIBILI_LIB_OK:
            self.skipTest("bilibili-api-python not installed")
        with mock.patch.object(b, "fetch_upower_emotes", return_value=(ours, "")), \
             mock.patch.object(b, "_room_owner", return_value=(42, "")), \
             mock.patch.object(b, "garb_packs_owned_by", return_value=set()), \
             mock.patch.object(b, "has_login_credentials", return_value=True), \
             mock.patch.object(b, "_credential"), mock.patch.object(b.live, "LiveRoom"), \
             mock.patch.object(b, "_run"), mock.patch.object(b, "parse_emoticons", return_value=other):
            packs, err = b.get_emoticons("1")
            self.assertEqual([p["name"] for p in packs], ["充电表情", "别人的充电表情"])
            with mock.patch.object(b, "parse_emoticons", return_value=other + ours):
                packs, _ = b.get_emoticons("1")
                self.assertEqual(len(packs), 2)  # already listed by Bilibili: not added twice

    def test_room_owner_packs_listed_first(self):
        from src.bilibili import rank_packs

        def pack(name, type_, unique="x"):
           return {"name": name, "type": type_, "emotes": [{"name": "e", "unique": unique, "url": "u"}]}
        packs = [pack("别人装扮", 5, "upower_[别人装扮_a]"), pack("通用表情", 1), pack("别人的充电", 5, "upower_[UPOWER_7_x]"),
                pack("Ya酱的装扮表情", 5, "upower_[Ya酱的装扮表情_b]"), pack("房间专属表情", 2),
                pack("夏日集", 5, "upower_[夏日集_c]"), pack("主播充电", 5, "upower_[UPOWER_42_y]")]
        ranked = rank_packs(packs, 42, "やーちゃん_Ya酱", {"夏日集"})
        self.assertEqual([p["name"] for p in ranked], ["主播充电", "房间专属表情", "Ya酱的装扮表情", "夏日集",
                                                      "通用表情", "别人装扮", "别人的充电"])
        self.assertEqual([p["owner"] for p in ranked], [True] * 4 + [False] * 3)

    def test_garb_owner_from_shop_fan_mid(self):
        from unittest import mock
        from src import bilibili as b
        resp = mock.Mock()
        resp.json.return_value = {"data": {"list": [
            {"name": "夏日集个性装扮", "properties": {"fan_mid": "42"}},
            {"name": "无关装扮", "properties": {"fan_mid": "7"}}]}}
        b._garb_owner_cache.clear()
        with mock.patch.object(b.requests, "get", return_value=resp):
            pk = {"name": "装扮表情", "type": 5, "emotes": [{"unique": "upower_[夏日集_好耶]"}]}
            self.assertEqual(b.garb_packs_owned_by(42, [pk]), {"夏日集"})
            self.assertEqual(b.garb_packs_owned_by(7, [pk]), set())
        b._garb_owner_cache.clear()

    def test_combined_garb_pack_split_per_garb(self):
        from src.bilibili import parse_emoticons

        def emo(u):
            return {"emoticon_unique": u, "emoji": u, "url": "https://i0.hdslb.com/bfs/emote/a.png", "perm": 1}
        resp = {"data": [{"pkg_name": "装扮表情", "pkg_type": 5,
                         "emoticons": [emo("upower_[甲_1]"), emo("upower_[乙_2]"), emo("upower_[甲_3]")]}]}
        packs = parse_emoticons(resp)
        self.assertEqual([(p["name"], len(p["emotes"])) for p in packs], [("甲", 2), ("乙", 1)])
        resp = {"data": [{"pkg_name": "装扮表情", "pkg_type": 5, "emoticons": [emo("upower_[请吃红小豆吧！_眨眼]")]},
                         {"pkg_name": "装扮表情", "pkg_type": 5, "emoticons": [emo("upower_[夏日集_好耶]")]}]}
        self.assertEqual([p["name"] for p in parse_emoticons(resp)], ["请吃红小豆吧！", "夏日集"])

    def test_garb_pack_labelled_with_up_name(self):
        from unittest import mock
        from src import bilibili as b
        packs = [{"name": "夏日集", "type": 5, "emotes": [{"unique": "upower_[夏日集_好耶]"}]},
                 {"name": "官方装扮", "type": 5, "emotes": [{"unique": "upower_[官方装扮_a]"}]},
                 {"name": "通用表情", "type": 1, "emotes": [{"unique": "official_1"}]}]
        with mock.patch.object(b, "_garb_owners", side_effect=lambda n: {42} if n == "夏日集" else set()), \
             mock.patch.object(b, "_up_name", return_value="Ya酱"):
            b.label_garb_packs(packs)
        self.assertEqual([p["name"] for p in packs], ["夏日集 · Ya酱", "官方装扮", "通用表情"])

    def test_upower_pack_prefers_unlocked_tier(self):
        from src.bilibili import parse_upower_emotes
        emojis = [{"id": 1, "name": "盯", "icon": "https://i0.hdslb.com/bfs/garb/a.png"},
                  {"id": 2, "name": "好耶", "icon": "https://i0.hdslb.com/bfs/garb/b.png"}]
        resp = {"data": {"privilege_rights": {
            "10": {"emote": {"locked": True, "emojis": emojis}},
            "100": {"emote": {"locked": False, "emojis": emojis}, "medal": {"locked": True}},
        }}}

        packs = parse_upower_emotes(resp, 42)

        self.assertEqual(len(packs), 1)
        self.assertEqual(packs[0]["name"], "充电表情")
        self.assertEqual([e["unique"] for e in packs[0]["emotes"]],
                         ["upower_[UPOWER_42_盯]", "upower_[UPOWER_42_好耶]"])
        self.assertFalse(packs[0]["emotes"][0]["locked"])
        self.assertEqual(parse_upower_emotes({"data": {"privilege_rights": {}}}, 42), [])

    def test_emoticon_packs_parsed_with_locks(self):
        from src.bilibili import parse_emoticons
        resp = {"data": [
            {"pkg_name": "房间专属表情", "pkg_type": 2, "emoticons": [
                {"emoji": "冲鸭", "emoticon_unique": "room_25760587_1", "url": "http://i0.hdslb.com/bfs/live/a.png",
                 "perm": 1},
                {"emoji": "贴贴", "emoticon_unique": "room_25760587_2", "url": "//i0.hdslb.com/bfs/live/b.png",
                 "perm": 0, "unlock_show_text": "粉丝勋章 5 级解锁"},
                {"emoji": "坏", "emoticon_unique": "x", "url": "https://evil.example/c.png", "perm": 1},
            ]},
            {"pkg_name": "空", "emoticons": []},
        ], "fans_brand": 1}

        packs = parse_emoticons(resp)

        self.assertEqual(len(packs), 1)
        self.assertEqual(packs[0]["name"], "房间专属表情")
        self.assertEqual(packs[0]["emotes"], [
            {"name": "冲鸭", "unique": "room_25760587_1", "url": "https://i0.hdslb.com/bfs/live/a.png",
             "locked": False, "hint": ""},
            {"name": "贴贴", "unique": "room_25760587_2", "url": "https://i0.hdslb.com/bfs/live/b.png",
             "locked": True, "hint": "粉丝勋章 5 级解锁"},
        ])
        self.assertEqual(parse_emoticons(None), [])


if __name__ == "__main__":
    unittest.main()
