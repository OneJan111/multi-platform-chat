import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from src import overlay_server


class OverlayTests(unittest.TestCase):
    def test_snapshot_excludes_non_chat_and_private_fields(self):
        messages = [
            {"type": "danmaku", "author": "viewer", "text": f"message {i}",
             "platform": "missevan", "cookie": "private"}
            for i in range(7)
        ]
        messages.append({"type": "gift", "text": "gift"})
        translate = lambda text, target: f"{target}: {text}"
        data = overlay_server.snapshot(messages, True, "en", translate, "hello")
        self.assertEqual(len(data["messages"]), 5)
        self.assertEqual(data["messages"][0], {
            "author": "viewer", "text": "message 2",
            "translation": "en: message 2", "platform": "missevan",
        })
        self.assertEqual(data["custom_text"], "hello")
        self.assertNotIn("private", json.dumps(data))

        disabled = overlay_server.snapshot(messages, False, "en",
                                           lambda *_: self.fail("translation requested"))
        self.assertEqual(disabled["messages"][-1]["translation"], "")

    def test_hidden_usernames_are_not_sent_to_browser_source(self):
        messages = [{"type": "danmaku", "author": "private-name", "text": "hello",
                     "platform": "youtube"}]
        data = overlay_server.snapshot(messages, True, "en", lambda *_: "translated",
                                       show_username=False)
        self.assertEqual(data["messages"], [{
            "text": "hello", "translation": "translated", "platform": "youtube",
        }])
        self.assertNotIn("private-name", json.dumps(data))

    def test_message_count_is_configurable_and_clamped(self):
        messages = [{"type": "danmaku", "text": f"m{i}", "platform": "bilibili"} for i in range(60)]
        fetch = lambda count: [m["text"] for m in overlay_server.snapshot(
            messages, False, "en", lambda *_: "", count=count)["messages"]]
        self.assertEqual(fetch(3), ["m57", "m58", "m59"])
        self.assertEqual(len(fetch(0)), 1)
        self.assertEqual(len(fetch(999)), overlay_server.MAX_MESSAGES)

    def test_paid_events_are_separate_from_regular_chat(self):
        messages = [
            {"type": "danmaku", "text": "hi", "platform": "bilibili"},
            {"type": "superchat", "text": "[SC ¥30] thanks", "platform": "bilibili"},
            {"type": "superChatEvent", "text": "[Super Chat $5] yo", "platform": "youtube"},
            {"type": "superStickerEvent", "text": "[Super Sticker $2]", "platform": "youtube"},
            {"type": "gift", "text": "gift", "platform": "bilibili"},
        ]
        data = overlay_server.view(
            overlay_server.snapshot(messages, False, "en", lambda *_: "", paid_count=2), set())
        self.assertEqual([m["text"] for m in data["messages"]], ["hi"])
        self.assertEqual([m["text"] for m in data["paid"]],
                         ["[Super Chat $5] yo", "[Super Sticker $2]"])
        hidden = overlay_server.snapshot(messages, False, "en", lambda *_: "", paid_count=0)
        self.assertEqual(hidden["paid"], [])

    def test_busy_chat_cannot_push_paid_events_away(self):
        # The trimmed chat list no longer holds the Super Chat; the separate paid list still does.
        chat = [{"type": "danmaku", "text": f"m{i}", "platform": "bilibili"} for i in range(100)]
        paid = [
            {"type": "superchat", "text": "[SC ¥30] old", "platform": "bilibili"},
            {"type": "gift", "text": "🎁 Rocket ×1", "platform": "bilibili"},
        ]
        translate = lambda text, target: f"{target}: {text}"
        data = overlay_server.snapshot(chat, True, "en", translate, count=5,
                                       paid_count=3, paid_messages=paid)
        self.assertEqual([m["text"] for m in data["paid"]], ["[SC ¥30] old", "🎁 Rocket ×1"])
        self.assertEqual(data["paid"][1]["kind"], "gift")
        self.assertEqual(data["paid"][1]["translation"], "")
        self.assertEqual(data["paid"][0]["translation"], "en: [SC ¥30] old")
        self.assertEqual(len(data["messages"]), 5)

    def test_http_serves_only_overlay_and_live_snapshot(self):
        server = overlay_server.OverlayServer(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/overlay") as response:
                page = response.read().decode("utf-8")
                self.assertIn('background: transparent', page)
                self.assertIn('fetch("/overlay/data" + location.search', page)
                self.assertNotIn("Streamer", page)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            server.publish({"messages": [{"text": "<script>", "author": "a",
                                          "platform": "youtube", "translation": ""}],
                            "custom_text": ""})
            with urlopen(base + "/overlay/data") as response:
                self.assertEqual(json.load(response)["messages"][0]["text"], "<script>")
                self.assertEqual(response.headers["Content-Type"], "application/json; charset=utf-8")
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/")
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_site_filter_gets_full_count_per_site(self):
        messages = [{"type": "danmaku", "text": f"y{i}", "platform": "youtube"} for i in range(3)]
        messages += [{"type": "danmaku", "text": f"b{i}", "platform": "bilibili"} for i in range(10)]
        paid = [{"type": "superChatEvent", "text": "[SC] yt", "platform": "youtube"},
                {"type": "superchat", "text": "[SC] b", "platform": "bilibili"}]
        data = overlay_server.snapshot(messages, False, "en", lambda *_: "", count=3,
                                       paid_count=1, paid_messages=paid)
        texts = lambda d, k="messages": [m["text"] for m in d[k]]
        everything = overlay_server.view(data, set())
        self.assertEqual(texts(everything), ["b7", "b8", "b9"])
        self.assertEqual(texts(everything, "paid"), ["[SC] b"])
        yt_only = overlay_server.view(data, overlay_server.parse_sites(["yt"]))
        self.assertEqual(texts(yt_only), ["y0", "y1", "y2"])
        self.assertEqual(texts(yt_only, "paid"), ["[SC] yt"])
        self.assertEqual(overlay_server.parse_sites(["bili,ME", "youtube", "bogus"]),
                         {"bilibili", "missevan", "youtube"})
        self.assertEqual(overlay_server.parse_sites([]), set())

        server = overlay_server.OverlayServer(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            server.publish(data, "alice")
            with urlopen(base + "/overlay/data?ch=alice&site=youtube") as response:
                self.assertEqual(texts(json.load(response)), ["y0", "y1", "y2"])
            with urlopen(base + "/overlay/data?ch=alice&site=missevan") as response:
                self.assertEqual(json.load(response)["messages"], [])
            with urlopen(base + "/overlay/data?ch=alice") as response:
                self.assertEqual(texts(json.load(response)), ["b7", "b8", "b9"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_standalone_feed_url_parsing_and_snapshot(self):
        from src import overlay_feeds
        key = overlay_feeds.parse_key({
            "youtube": ["@Ya-chan"], "bilibili": ["https://live.bilibili.com/25760587"],
            "missevan": ["nonsense"],
        })
        self.assertEqual(key, overlay_feeds.FeedKey("https://www.youtube.com/@Ya-chan", "25760587", ""))
        self.assertEqual(overlay_feeds.parse_key({"yt": ["https://youtu.be/dQw4w9WgXcQ"]}).youtube,
                         "dQw4w9WgXcQ")
        self.assertFalse(overlay_feeds.parse_key({"ch": ["alice"]}))

        feed = overlay_feeds.Feed(key)  # not started: no network
        from src.filters import make_default_filter
        feed._filter = make_default_filter(None)  # built-in defaults (blocks links), not the saved file
        feed.add(overlay_feeds._stamp([
            {"type": "danmaku", "text": f"b{i}", "platform": "bilibili", "author": "x"} for i in range(8)
        ] + [
            {"type": "superchat", "text": "[SC ¥30] hi", "platform": "bilibili"},
            {"type": "gift", "text": "free", "platform": "bilibili", "free": True},
            {"type": "enter", "text": "entered the room", "platform": "bilibili"},
            {"type": "danmaku", "text": "spam www.example.com", "platform": "bilibili"},
        ]))
        original_get = overlay_feeds.get
        overlay_feeds.get = lambda k: feed
        try:
            data = overlay_server.view(overlay_server.feed_snapshot(
                key, {"n": ["3"], "names": ["0"], "text": ["hey"]}), set())
        finally:
            overlay_feeds.get = original_get
        self.assertEqual([m["text"] for m in data["messages"]], ["b5", "b6", "b7"])
        self.assertNotIn("author", data["messages"][0])
        self.assertEqual([m["text"] for m in data["paid"]], ["[SC ¥30] hi"])
        self.assertEqual(data["custom_text"], "hey")

    def test_bilibili_room_id_or_url(self):
        from unittest import mock
        from src import bilibili
        for text in ["25760587", " 25760587 ", "https://live.bilibili.com/25760587?live_from=85001",
                     "live.bilibili.com/h5/25760587", "https://m.live.bilibili.com/25760587",
                     "https://www.bilibili.com/blackboard/live/live-activity-player.html?enterTheRoom=0&cid=25760587"]:
            self.assertEqual(bilibili.parse_room_id(text), "25760587", text)
        for text in ["", "abc", "https://live.bilibili.com/", "https://www.bilibili.com/video/BV1xx411c7mD"]:
            self.assertEqual(bilibili.parse_room_id(text), "", text)
        resolved = mock.Mock(url="https://live.bilibili.com/25760587?share_source=copy_link")
        bilibili._short_links.clear()
        with mock.patch.object(bilibili.requests, "head", return_value=resolved) as head:
            self.assertEqual(bilibili.parse_room_id("【直播】 https://b23.tv/AbC123"), "25760587")
            self.assertEqual(bilibili.parse_room_id("【直播】 https://b23.tv/AbC123"), "25760587")
        head.assert_called_once()
        with mock.patch.object(bilibili.requests, "head", side_effect=bilibili.requests.ConnectionError):
            self.assertEqual(bilibili.parse_room_id("https://b23.tv/Other1"), "")

    def test_channels_are_isolated(self):
        server = overlay_server.OverlayServer(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            server.publish({"messages": [], "custom_text": "main"})
            server.publish({"messages": [], "custom_text": "alice"}, "alice")
            with urlopen(base + "/overlay/data") as response:
                self.assertEqual(json.load(response)["custom_text"], "main")
            with urlopen(base + "/overlay/data?ch=alice") as response:
                self.assertEqual(json.load(response)["custom_text"], "alice")
            with urlopen(base + "/overlay/data?ch=nobody") as response:
                self.assertEqual(json.load(response)["messages"], [])
            with urlopen(base + "/overlay?ch=alice") as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(overlay_server.clean_channel("a b/<c>"), "abc")
            self.assertEqual(overlay_server.clean_channel(""), "main")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_singleton_survives_module_reload(self):
        import importlib
        state = overlay_server._STATE
        sentinel = object()
        previous = state["server"]
        state["server"] = sentinel
        try:
            reloaded = importlib.reload(overlay_server)
            self.assertIs(reloaded.ensure_started(), sentinel)
        finally:
            state["server"] = previous

    def test_duplicate_bind_on_same_port_fails(self):
        server = overlay_server.OverlayServer(0)
        try:
            with self.assertRaises(OSError):
                overlay_server.OverlayServer(server.server_address[1])
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
