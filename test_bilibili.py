import base64
import unittest

from src.bilibili import DanmakuListener, _decode_send_gift_v2


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

    def test_guard_toast_alone_is_recorded(self):
        listener = DanmakuListener.__new__(DanmakuListener)
        listener.messages = []
        listener._record_guard({"uid": 7, "username": "fan", "guard_level": 3, "num": 1,
                                "price": 198000, "role_name": "舰长", "unit": "月"}, paid=True)

        self.assertEqual(listener.messages[0]["text"], "🎁 舰长 ×1月 (¥198)")

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


if __name__ == "__main__":
    unittest.main()
