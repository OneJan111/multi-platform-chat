import json
import unittest

from src import emotes, overlay_server

URL = "https://i0.hdslb.com/bfs/live/doge.png"


class EmoteTests(unittest.TestCase):
    def test_missevan_sticker_cdn_is_allowed_but_untrusted_suffix_is_not(self):
        url = "https://static.maoercdn.com/stickers/room.png"
        self.assertEqual(emotes.safe_chat_image_url(url), url)
        self.assertEqual(
            emotes.safe_chat_image_url("https://maoercdn.com.evil.example/sticker.png"), ""
        )

    def test_parse_inline_emots_and_sticker_from_danmu_meta(self):
        meta = [0] * 16
        meta[15] = {"extra": json.dumps({"emots": {
            "[doge]": {"url": URL},
            "[bad]": {"url": "https://evil.example/x.png"},
        }})}
        self.assertEqual(emotes.parse_danmu_emotes(meta), ({"[doge]": URL}, ""))

        meta[12] = 1
        meta[13] = json.dumps({"url": "http://i0.hdslb.com/bfs/live/big.png"})
        self.assertEqual(emotes.parse_danmu_emotes(meta)[1], "https://i0.hdslb.com/bfs/live/big.png")
        self.assertEqual(emotes.parse_danmu_emotes([]), ({}, ""))

    def test_text_to_html_escapes_text_and_inlines_images(self):
        out = emotes.text_to_html("<b>hi</b>[doge]!", {"[doge]": URL})
        self.assertTrue(out.startswith("&lt;b&gt;hi&lt;/b&gt;<img "))
        self.assertIn(f'src="{URL}"', out)
        self.assertIn('referrerpolicy="no-referrer"', out)
        self.assertTrue(out.endswith("!"))
        sticker = emotes.text_to_html('"x"', None, URL)
        self.assertIn('alt="&quot;x&quot;"', sticker)

    def test_overlay_snapshot_only_includes_used_safe_emotes(self):
        messages = [{"type": "danmaku", "text": "hi [doge]", "platform": "bilibili",
                     "emotes": {"[doge]": URL, "[unused]": URL, "[x]": "javascript:alert(1)"},
                     "sticker_url": "https://static.maoercdn.com/stickers/room.png"}]
        item = overlay_server.snapshot(messages, False, "en", lambda *_: "")["messages"][0]
        self.assertEqual(item["emotes"], {"[doge]": URL})
        self.assertEqual(item["sticker"], "https://static.maoercdn.com/stickers/room.png")


if __name__ == "__main__":
    unittest.main()
