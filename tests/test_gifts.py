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


if __name__ == "__main__":
    unittest.main()
