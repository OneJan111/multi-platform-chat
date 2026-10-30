import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

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
            "translation": "en: message 2", "platform": "missevan", "at": 0,
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
            "text": "hello", "translation": "translated", "platform": "youtube", "at": 0,
        }])
        self.assertNotIn("private-name", json.dumps(data))

    def test_message_count_is_configurable_and_clamped(self):
        messages = [{"type": "danmaku", "text": f"m{i}", "platform": "bilibili"} for i in range(60)]
        fetch = lambda count: [m["text"] for m in overlay_server.snapshot(
            messages, False, "en", lambda *_: "", count=count)["messages"]]
        self.assertEqual(fetch(3), ["m57", "m58", "m59"])
        self.assertEqual(fetch(0), [])  # 0 = chat off (Super Chats-only overlay)
        self.assertEqual(len(fetch(-5)), 0)
        self.assertEqual(len(fetch(999)), overlay_server.MAX_MESSAGES)

    def test_paid_events_are_separate_from_regular_chat(self):
        messages = [
            {"type": "danmaku", "text": "hi", "platform": "bilibili"},
            {"type": "superchat", "text": "[SC ¥30] thanks", "platform": "bilibili"},
            {"type": "superChatEvent", "text": "[Super Chat $5] yo", "platform": "youtube"},
            {"type": "superStickerEvent", "text": "[Super Sticker $2]", "platform": "youtube"},
            {"type": "gift", "text": "gift", "platform": "bilibili"},
        ]
        data = overlay_server.snapshot(messages, False, "en", lambda *_: "", paid_count=2)
        self.assertEqual([m["text"] for m in data["messages"]], ["hi"])
        self.assertEqual([m["text"] for m in overlay_server.view(data, set(), count=0)["paid"]],
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

    def test_http_overlay_can_require_proxy_token(self):
        server = overlay_server.OverlayServer(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with patch.dict("os.environ", {"OVERLAY_PROXY_TOKEN": "a" * 32}):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + "/overlay")
                self.assertEqual(error.exception.code, 401)
                self.assertEqual(error.exception.headers["Cache-Control"], "no-store")
                error.exception.close()

                request = Request(
                    base + "/overlay",
                    headers={"Authorization": f"Bearer {'a' * 32}"},
                )
                with urlopen(request) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b"background: transparent", response.read())
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
        self.assertEqual(texts(everything), ["[SC] b", "b7", "b8", "b9"])  # no stamps: paid first
        yt_only = overlay_server.view(data, overlay_server.parse_sites(["yt"]))
        self.assertEqual(texts(yt_only), ["[SC] yt", "y0", "y1", "y2"])
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
                self.assertEqual(texts(json.load(response)), ["[SC] yt", "y0", "y1", "y2"])
            with urlopen(base + "/overlay/data?ch=alice&site=missevan") as response:
                self.assertEqual(json.load(response)["messages"], [])
            with urlopen(base + "/overlay/data?ch=alice") as response:
                self.assertEqual(texts(json.load(response)), ["[SC] b", "b7", "b8", "b9"])
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
        # Stamped on arrival: the Super Chat and the gift came after the chat lines.
        self.assertEqual([m["text"] for m in data["messages"]], ["b5", "b6", "b7", "[SC ¥30] hi", "free"])
        self.assertNotIn("author", data["messages"][0])
        self.assertEqual([m.get("paid", False) for m in data["messages"]], [False] * 3 + [True] * 2)
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

    def test_standalone_url_mirrors_open_dashboard_reading_same_rooms(self):
        from unittest import mock
        from src import overlay_feeds
        server = overlay_server.OverlayServer(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            key = overlay_feeds.parse_key({"bilibili": ["25760587"]})
            dashboard = {"messages": [{"text": "dash", "platform": "bilibili"},
                                      {"text": "yt", "platform": "youtube"}],
                         "paid": [], "custom_text": "", "count": 5, "paid_count": 3}
            server.publish(dashboard, "alice", source=key)
            standalone = {"messages": [{"text": "own", "platform": "bilibili"}], "paid": [], "custom_text": ""}
            feed = mock.Mock(last_used=0)
            with mock.patch.object(overlay_feeds, "get", return_value=feed), \
                    mock.patch.object(overlay_server, "feed_snapshot", return_value=standalone):
                with urlopen(base + "/overlay/data?bilibili=25760587") as response:
                    # Only the URL's sites, even though the dashboard snapshot has more.
                    self.assertEqual([m["text"] for m in json.load(response)["messages"]], ["dash"])
                self.assertGreater(feed.last_used, 0)  # standalone feed kept warm for fallback
                with urlopen(base + "/overlay/data?bilibili=999") as response:
                    self.assertEqual([m["text"] for m in json.load(response)["messages"]], ["own"])
                with mock.patch.object(overlay_server.time, "time",
                                       return_value=time.time() + overlay_server.MIRROR_TTL + 1):
                    with urlopen(base + "/overlay/data?bilibili=25760587") as response:
                        self.assertEqual([m["text"] for m in json.load(response)["messages"]], ["own"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

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


class OverlayHtmlTests(unittest.TestCase):
    def test_snapshot_and_html_render_trusted_avatars(self):
        for site, url in (
            ("youtube", "https://yt3.ggpht.com/avatar.png"),
            ("bilibili", "https://i0.hdslb.com/bfs/face/avatar.jpg"),
            ("missevan", "https://static.maoercdn.com/avatar.png"),
        ):
            with self.subTest(site=site):
                data = overlay_server.snapshot(
                    [{"type": "danmaku", "platform": site, "text": "hi",
                      "author": 'A<&"', "avatar": url}],
                    False, "", lambda *_: "",
                )
                self.assertEqual(data["messages"][0]["avatar"], url)
                rendered = overlay_server.render_html(data)
                self.assertIn(f'src="{url}"', rendered)
                self.assertIn('class="avatar"', rendered)
                self.assertIn("A&lt;&amp;&quot;", rendered)
        unsafe = overlay_server.snapshot(
            [{"type": "danmaku", "platform": "youtube", "text": "hi",
              "author": "Bob", "avatar": "https://evil.example/avatar.png"}],
            False, "", lambda *_: "",
        )
        self.assertNotIn("avatar", unsafe["messages"][0])
        self.assertIn('class="avatar" title="Bob">B</span>', overlay_server.render_html(unsafe))
        rendered = overlay_server.render_html({
            "messages": [{"text": "hi", "avatar": "javascript:alert(1)", "author": "Bob"}],
        })
        self.assertNotIn("javascript:", rendered)
        self.assertIn('class="avatar" title="Bob">B</span>', rendered)
        page = overlay_server._PAGE.decode("utf-8")
        self.assertIn('image(avatarUrl, msg.author || "", "avatar")', page)

    def test_standalone_all_link_limits_combined_messages_to_ten(self):
        from unittest.mock import Mock, patch
        from src import overlay_feeds

        chat = [
            {"type": "danmaku", "platform": "bilibili", "text": f"chat{i}", "_arrived": i}
            for i in range(12)
        ]
        paid = [
            {"type": "gift", "platform": "bilibili", "text": f"gift{i}", "_arrived": 100 + i}
            for i in range(8)
        ]
        feed = Mock()
        feed.messages.return_value = (chat, paid)
        with patch.object(overlay_feeds, "get", return_value=feed):
            data = overlay_server.overlay_data({"bilibili": ["123"], "n": ["10"]})
        self.assertEqual(len(data["messages"]), 10)
        self.assertEqual(data["paid"], [])
        self.assertEqual(data["layout"], "mixed")
        self.assertEqual(
            [msg["text"] for msg in data["messages"]],
            ["chat10", "chat11"] + [f"gift{i}" for i in range(8)],
        )

    def test_render_html_escapes_and_inlines_safe_images(self):
        me_sticker = "https://static.maoercdn.com/stickers/room.png"
        out = overlay_server.render_html({
            "paid": [{"text": "[SC] <b>hi</b>", "author": "A&B", "platform": "youtube", "kind": "gift"}],
            "messages": [{"text": "yo :_wave: [x]", "platform": "bilibili",
                          "emotes": {":_wave:": "https://yt3.ggpht.com/w", "[x]": "https://evil.example/x"}},
                         {"text": "", "platform": "missevan", "sticker": me_sticker}],
            "custom_text": "<script>",
        })
        self.assertIn("[SC] &lt;b&gt;hi&lt;/b&gt;", out)
        self.assertIn('class="author youtube">A&amp;B<', out)
        self.assertIn('class="message paid-item gift"', out)
        self.assertIn('src="https://yt3.ggpht.com/w"', out)
        self.assertIn(f'src="{me_sticker}"', out)
        self.assertNotIn("evil.example", out)
        self.assertIn("&lt;script&gt;", out)

    def test_overlay_data_reads_channel_without_http(self):
        server = overlay_server.OverlayServer(0, "127.0.0.1")
        try:
            server.publish({"messages": [{"text": "hi"}], "paid": [], "custom_text": "", "count": 5, "paid_count": 3},
                           channel="me")
            self.assertEqual(overlay_server.overlay_data({"ch": ["me"]}, server)["messages"], [{"text": "hi"}])
            self.assertEqual(overlay_server.overlay_data({"ch": ["me"]}, None)["messages"], [])
        finally:
            server.server_close()

    def test_url_counts_split_super_chats_and_chat(self):
        server = overlay_server.OverlayServer(0, "127.0.0.1")
        try:
            server.publish({"messages": [{"text": "a"}, {"text": "b"}], "paid": [{"text": "sc"}],
                            "custom_text": "", "count": 5, "paid_count": 3}, channel="me")
            paid_only = overlay_server.overlay_data({"ch": ["me"], "n": ["0"], "sc": ["3"]}, server)
            self.assertEqual((paid_only["messages"], paid_only["paid"], paid_only["layout"]),
                             ([], [{"text": "sc"}], "only-paid"))
            chat_only = overlay_server.overlay_data({"ch": ["me"], "n": ["1"], "sc": ["0"]}, server)
            self.assertEqual((chat_only["messages"], chat_only["paid"], chat_only["layout"]),
                             ([{"text": "b"}], [], "only-chat"))
            # URL counts can lower the dashboard's, not raise them; bad values are ignored.
            both = overlay_server.overlay_data({"ch": ["me"], "n": ["50"], "sc": ["x"]}, server)
            self.assertEqual((len(both["messages"]), both["paid"], both["layout"]), (3, [], "mixed"))
        finally:
            server.server_close()
        self.assertIn('<div class="only-paid">', overlay_server.render_html({"layout": "only-paid"}))
        self.assertEqual(overlay_server.snapshot([{"type": "danmaku", "text": "x"}], False, "", lambda *_: "",
                                                 count=0)["messages"], [])

    def test_all_mixes_paid_and_chat_in_arrival_order(self):
        chat = [{"type": "danmaku", "text": f"c{i}", "platform": "bilibili", "_arrived": i * 10}
                for i in range(1, 6)]
        paid = [{"type": "superchat", "text": "sc", "platform": "bilibili", "_arrived": 25},
                {"type": "gift", "text": "gift", "platform": "bilibili", "_arrived": 45}]
        data = overlay_server.snapshot(chat, False, "en", lambda *_: "", count=3,
                                       paid_count=3, paid_messages=paid)
        mixed = overlay_server.view(data, set())
        self.assertEqual(mixed["layout"], "mixed")
        self.assertEqual([m["text"] for m in mixed["messages"]], ["sc", "c3", "c4", "gift", "c5"])
        self.assertEqual([bool(m.get("paid")) for m in mixed["messages"]], [True, False, False, True, False])
        self.assertNotIn("paid", data["paid"][0])  # shared snapshot isn't modified
        out = overlay_server.render_html(mixed)
        self.assertIn('class="message paid-item gift"', out)
        self.assertIn('<div class="mixed">', out)
        # Per-URL counts and the other variants are unchanged.
        self.assertEqual([m["text"] for m in overlay_server.view(data, set(), count=1)["messages"]],
                         ["sc", "gift", "c5"])
        self.assertEqual(overlay_server.view(data, set(), paid_count=0)["layout"], "only-chat")
        self.assertEqual(overlay_server.view(data, set(), count=0)["layout"], "only-paid")
        self.assertEqual(overlay_server.order_key({"timestamp": "1700000000"}), 1700000000 * 10**9)
        self.assertEqual(overlay_server.order_key({"timestamp": "1700000000123"}), 1700000000123 * 10**6)
        self.assertGreater(overlay_server.order_key({"timestamp": "2024-01-01T00:00:00Z"}), 0)
        self.assertEqual(overlay_server.order_key({}), 0)

    def test_n_without_sc_is_one_chat_of_n_messages(self):
        chat = [{"type": "danmaku", "text": f"c{i}", "platform": "bilibili", "_arrived": i * 10}
                for i in range(1, 6)]
        paid = [{"type": "gift", "text": f"g{i}", "platform": "bilibili", "_arrived": 100 + i} for i in range(4)]
        data = overlay_server.snapshot(chat, False, "en", lambda *_: "", count=5,
                                       paid_count=2, paid_messages=paid)
        server = overlay_server.OverlayServer(0, "127.0.0.1")
        try:
            server.publish(data, channel="me")
            single = overlay_server.overlay_data({"ch": ["me"], "n": ["5"]}, server)
            # All four recent gifts (more than sc's 2) and the last chat line, as one chat of 5.
            self.assertEqual([m["text"] for m in single["messages"]], ["c5", "g0", "g1", "g2", "g3"])
            self.assertEqual((single["paid"], single["layout"]), ([], "mixed"))
            separate = overlay_server.overlay_data({"ch": ["me"], "n": ["5"], "sc": ["2"]}, server)
            self.assertEqual([m["text"] for m in separate["messages"]], ["c1", "c2", "c3", "c4", "c5", "g2", "g3"])
            server.publish(dict(data, paid_count=0), channel="me")  # dashboard hides paid events
            self.assertEqual([m["text"] for m in overlay_server.overlay_data({"ch": ["me"], "n": ["3"]}, server)
                              ["messages"]], ["c3", "c4", "c5"])
        finally:
            server.server_close()


class OverlayReadingTests(unittest.TestCase):
    def test_parse_reading(self):
        for value, mode in (("auto", "auto"), ("Pinyin", "pinyin"), ("furigana", "hiragana"),
                            ("1", "auto"), ("both", "off"), ("", "off"), ("<x>", "off")):
            self.assertEqual(overlay_server.parse_reading(value), mode, value)

    def test_snapshot_ruby_is_off_by_default_and_skips_emote_codes(self):
        msgs = [{"type": "danmaku", "platform": "bilibili", "text": "\u4f60\u597d[\u5999\u554a]",
                 "emotes": {"[\u5999\u554a]": "https://i0.hdslb.com/e.png"}}]
        off = overlay_server.snapshot(msgs, False, "", lambda *_: "")
        self.assertNotIn("ruby", off["messages"][0])
        item = overlay_server.snapshot(msgs, False, "", lambda *_: "", reading_mode="pinyin")["messages"][0]
        self.assertEqual(list(item["ruby"]), ["\u4f60\u597d"])
        self.assertEqual("".join(rt for _, rt in item["ruby"]["\u4f60\u597d"]).replace(" ", ""), "n\u01d0h\u01ceo")

    def test_snapshot_translation_ruby_follows_target_language(self):
        msgs = [{"type": "textMessageEvent", "platform": "youtube", "text": "hello"}]
        item = overlay_server.snapshot(msgs, True, "ja", lambda *_: "\u65e5\u672c", reading_mode="pinyin")["messages"][0]
        self.assertNotIn("ruby", item)
        self.assertTrue(item["translation_ruby"])
        # Furigana is in hiragana, not pinyin.
        self.assertTrue(all("\u3040" <= ch <= "\u309f" for _, rt in item["translation_ruby"] for ch in rt if rt))

    def test_render_html_ruby_is_escaped(self):
        out = overlay_server.render_html({"messages": [{
            "text": "<i>\u4f60", "platform": "bilibili",
            "ruby": {"<i>\u4f60": [["<i>", ""], ["\u4f60", "<b>"]]},
        }]})
        self.assertIn("<ruby>\u4f60<rt>&lt;b&gt;</rt></ruby>", out)
        self.assertIn("&lt;i&gt;", out)
        self.assertNotIn("<b>", out)
