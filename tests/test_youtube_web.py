import unittest

from src.youtube_web import _parse_action


class YouTubeWebChatTests(unittest.TestCase):
    def test_parses_paid_sticker_ticker_action(self):
        message = _parse_action({
            "addLiveChatTickerItemAction": {
                "item": {
                    "liveChatTickerPaidStickerItemRenderer": {
                        "id": "sticker-123",
                        "authorExternalChannelId": "channel-123",
                        "authorPhoto": {"thumbnails": [{"url": "https://example.com/avatar.jpg"}]},
                        "showItemEndpoint": {
                            "showLiveChatItemEndpoint": {
                                "renderer": {
                                    "liveChatPaidStickerRenderer": {
                                        "purchaseAmountText": {"simpleText": "$2.00"},
                                        "sticker": {"thumbnails": []},
                                        "backgroundColor": 0,
                                        "authorName": {"simpleText": "Viewer"},
                                        "authorPhoto": {"thumbnails": []},
                                        "authorBadges": [],
                                        "timestampUsec": "1000000",
                                    }
                                }
                            }
                        },
                    }
                }
            }
        })

        self.assertEqual(message["id"], "sticker-123")
        self.assertEqual(message["platform"], "youtube")
        self.assertEqual(message["author"], "Viewer")
        self.assertEqual(message["author_id"], "channel-123")
        self.assertEqual(message["type"], "superStickerEvent")
        self.assertEqual(message["text"], "[Super Sticker $2.00]")
        self.assertEqual((message["currency"], message["value"]), ("$", 2.0))
        self.assertEqual(message["avatar"], "https://example.com/avatar.jpg")

    def test_custom_emoji_stamps_become_inline_images(self):
        message = _parse_action({"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
            "id": "e1", "authorName": {"simpleText": "V"},
            "message": {"runs": [
                {"text": "hi "},
                {"emoji": {"emojiId": "UC/abc", "isCustomEmoji": True, "shortcuts": [":_wave:"],
                           "image": {"thumbnails": [{"url": "https://yt3.ggpht.com/wave=w24"},
                                                    {"url": "https://yt3.ggpht.com/wave=w48"}]}}},
                {"emoji": {"emojiId": "😀", "shortcuts": [":grinning:"],
                           "image": {"thumbnails": [{"url": "https://www.youtube.com/s/gaming/emoji/1f600.svg"}]}}},
                {"emoji": {"emojiId": "UC/bad", "isCustomEmoji": True, "shortcuts": [":_bad:"],
                           "image": {"thumbnails": [{"url": "https://evil.example/x.png"}]}}},
            ]},
        }}}})

        self.assertEqual(message["text"], "hi :_wave:😀:_bad:")
        self.assertEqual(message["emotes"], {":_wave:": "https://yt3.ggpht.com/wave=w48"})
        self.assertEqual(message["sticker_url"], "")

    def test_channel_stamps_remembered_for_sending(self):
        from src import youtube_web as w
        wave = {"emojiId": "UC1/wave", "isCustomEmoji": True, "shortcuts": [":_wave:", ":wave:"],
                "image": {"thumbnails": [{"url": "https://yt3.ggpht.com/wave=w48"}],
                          "accessibility": {"accessibilityData": {"label": "wave"}}}}
        w._channel_emojis.pop("vid1", None)
        w._remember_emojis("vid1", [{"emoji": wave}, {"emoji": {"emojiId": "😀", "shortcuts": [":grinning:"]}}])
        # The logged-in picker marks member-only stamps; a later chat sighting keeps that.
        w._remember_emojis("vid1", {"emojis": [dict(wave, emojiId="UC1/hug", shortcuts=[":_hug:"], isLocked=True)]})
        w._remember_emojis("vid1", [{"emoji": dict(wave, emojiId="UC1/hug", shortcuts=[":_hug:"])}])

        emojis = w.channel_emojis("vid1")
        self.assertEqual([(e["id"], e["code"], e["locked"]) for e in emojis],
                         [("UC1/wave", ":_wave:", None), ("UC1/hug", ":_hug:", True)])
        self.assertEqual(w.message_segments("hi :_wave::wave: bye", emojis),
                         [{"text": "hi "}, {"emojiId": "UC1/wave"}, {"emojiId": "UC1/wave"}, {"text": " bye"}])
        self.assertEqual(w.message_segments("plain", []), [{"text": "plain"}])
        self.assertEqual(w.strip_emoji_codes("hi :_wave: :wave: :_other: there", emojis), "hi there")
        self.assertEqual(w.strip_emoji_codes(":_wave:", emojis), "")
        self.assertEqual(w.strip_emoji_codes("time 12:30:45", emojis), "time 12:30:45")

    def test_super_sticker_keeps_amount_with_image(self):
        from src.emotes import text_to_html
        message = _parse_action({"addChatItemAction": {"item": {"liveChatPaidStickerRenderer": {
            "id": "s1", "authorName": {"simpleText": "V"},
            "purchaseAmountText": {"simpleText": "¥200"},
            "sticker": {"thumbnails": [{"url": "//lh3.googleusercontent.com/sticker=s40"},
                                       {"url": "//lh3.googleusercontent.com/sticker=s80"}]},
        }}}})

        self.assertEqual(message["sticker_url"], "https://lh3.googleusercontent.com/sticker=s80")
        rendered = text_to_html(message["text"], message["emotes"], message["sticker_url"], message["sticker_caption"])
        self.assertTrue(rendered.startswith("[Super Sticker ¥200]<br><img"))

    def test_channel_member_badge_sets_membership(self):
        message = _parse_action({"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
            "id": "m1",
            "message": {"runs": [{"text": "hi"}]},
            "authorName": {"simpleText": "Viewer"},
            "authorBadges": [
                {"liveChatAuthorBadgeRenderer": {"icon": {"iconType": "MODERATOR"}, "tooltip": "Moderator"}},
                {"liveChatAuthorBadgeRenderer": {"customThumbnail": {"thumbnails": [
                    {"url": "https://yt3.ggpht.com/badge=s16", "width": 16},
                    {"url": "https://yt3.ggpht.com/badge=s32", "width": 32}]},
                                                 "tooltip": "Member (6 months)"}},
            ],
        }}}})

        self.assertTrue(message["is_moderator"])
        self.assertEqual(message["membership"], "Member (6 months)")
        self.assertEqual(message["membership_icon"], "https://yt3.ggpht.com/badge=s32")

    def test_non_member_has_no_membership(self):
        message = _parse_action({"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
            "id": "m2", "message": {"runs": [{"text": "hi"}]}, "authorName": {"simpleText": "V"},
        }}}})

        self.assertEqual(message["membership"], "")

    def test_membership_gift_purchase_and_redemption(self):
        bought = _parse_action({"addChatItemAction": {"item": {
            "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer": {
                "id": "g1", "authorExternalChannelId": "UCgifter", "timestampUsec": "1700000000000000",
                "header": {"liveChatSponsorshipsHeaderRenderer": {
                    "authorName": {"simpleText": "Gifter"},
                    "primaryText": {"runs": [{"text": "Gifted "}, {"text": "10"}, {"text": " Ya-chan memberships"}]},
                }},
            }}}})
        got = _parse_action({"addChatItemAction": {"item": {
            "liveChatSponsorshipsGiftRedemptionAnnouncementRenderer": {
                "id": "r1", "authorExternalChannelId": "UCfan", "authorName": {"simpleText": "Fan"},
                "message": {"runs": [{"text": "received a gift membership by "}, {"text": "Gifter", "bold": True}]},
            }}}})

        self.assertEqual(bought["type"], "membershipGiftingEvent")
        self.assertEqual(bought["author"], "Gifter")
        self.assertEqual(bought["gift_count"], 10)
        self.assertEqual(bought["text"], "[Gifted 10 Ya-chan memberships]")
        self.assertEqual(got["type"], "giftMembershipReceivedEvent")
        self.assertEqual(got["author"], "Fan")
        self.assertEqual(got["gifted_by"], "Gifter")
        self.assertEqual(got["text"], "[Gift membership] received a gift membership by Gifter")
        self.assertTrue(got["free"])


if __name__ == "__main__":
    unittest.main()
