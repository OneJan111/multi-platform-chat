import unittest

from src import gifts


class ParseAmountTests(unittest.TestCase):
    def test_parses_symbols_and_separators(self):
        cases = {
            "$5.00": ("$", 5.0),
            "¥200": ("¥", 200.0),
            "CA$1,000.00": ("CA$", 1000.0),
            "₩10,000": ("₩", 10000.0),
            "5,00 €": ("€", 5.0),
            "1.234,50 €": ("€", 1234.5),
            "": ("", 0.0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(gifts.parse_amount(text), expected)


class LeaderboardTests(unittest.TestCase):
    def test_ranks_by_main_currency_and_keeps_currencies_apart(self):
        def m(uid, name, cur="", value=0, site="youtube"):
            return gifts.set_value({"platform": site, "author_id": uid, "author": name}, cur, value)

        msgs = [
            m("a", "Alice", "$", 5), m("a", "Alice", "$", 10), m("a", "Alice", "¥", 500),
            m("b", "Bob", "$", 20),
            m("c", "Cara"),  # a membership: counted, no amount
            m("b", "Bob", "¥", 100, site="bilibili"),
        ]
        board = gifts.leaderboard(msgs, "youtube")

        self.assertEqual([r["author"] for r in board], ["Bob", "Alice", "Cara"])
        self.assertEqual([r["rank"] for r in board], [1, 2, 3])
        self.assertEqual(board[1]["count"], 3)
        self.assertEqual(board[1]["total"], "$15 + ¥500")
        self.assertEqual(board[2]["total"], "")
        self.assertEqual(gifts.leaderboard(msgs, "bilibili")[0]["total"], "¥100")

    def test_set_value_ignores_missing_amounts(self):
        self.assertEqual(gifts.set_value({}, "¥", 0), {})
        self.assertEqual(gifts.set_value({}, "", 5), {})
        self.assertEqual(gifts.set_value({}, "¥", "bad"), {})


class PlatformTotalsTests(unittest.TestCase):
    def test_counts_gift_units_and_separates_revenue_currencies(self):
        messages = [
            {"platform": "youtube", "type": "gift", "gift_count": 3, "currency": "¥", "value": 60},
            {"platform": "youtube", "type": "gift", "free": True},
            {"platform": "youtube", "type": "superChatEvent", "currency": "$", "value": 5},
            {"platform": "bilibili", "type": "superchat", "currency": "¥", "value": 30},
            {"platform": "missevan", "type": "gift", "gift_count": 2, "currency": "💎", "value": 20},
            {"platform": "youtube", "type": "newSponsorEvent", "currency": "$", "value": 10},
        ]

        totals = gifts.platform_totals(messages, ("youtube", "bilibili", "missevan"))

        self.assertEqual(totals["youtube"], {
            "gift_count": 4,
            "gift_revenue": {"¥": 60.0},
            "superchat_count": 1,
            "superchat_revenue": {"$": 5.0},
        })
        self.assertEqual(totals["bilibili"]["superchat_revenue"], {"¥": 30.0})
        self.assertEqual(totals["missevan"]["gift_count"], 2)

    def test_amount_totals_sums_gifts_and_super_chats_by_currency(self):
        messages = [
            {"type": "gift", "currency": "¥", "value": 10},
            {"type": "superchat", "currency": "¥", "value": 20},
            {"type": "superStickerEvent", "currency": "$", "value": 5},
            {"type": "newSponsorEvent", "currency": "$", "value": 8},
            {"type": "gift", "currency": "💎", "value": 0},
        ]

        self.assertEqual(gifts.amount_totals(messages), {"¥": 30.0, "$": 5.0})

    def test_gift_price_label_only_adds_unshown_known_prices(self):
        self.assertEqual(gifts.gift_price_label({
            "type": "gift", "currency": "💎", "value": 6, "text": "🎁 花 ×3",
        }), "💎6")
        self.assertEqual(gifts.gift_price_label({
            "type": "gift", "currency": "¥", "value": 2, "text": "🎁 花 ×1 (¥2)",
        }), "")
        self.assertEqual(gifts.gift_price_label({
            "type": "gift", "text": "🎁 免费礼物",
        }), "")
        self.assertEqual(gifts.gift_price_label({
            "type": "superchat", "currency": "¥", "value": 10, "text": "SC ¥10",
        }), "")


if __name__ == "__main__":
    unittest.main()
