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


if __name__ == "__main__":
    unittest.main()
