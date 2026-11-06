from copy import deepcopy
import json
from pathlib import Path
import tempfile
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import desktop_app
import html_app
from html_app import Dashboard, make_server


class HtmlDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "settings.json"
        self.dashboard = Dashboard(self.path, start=False)
        self.dashboard.archive = desktop_app.DesktopChatArchive(
            Path(self.temp.name) / "archive.json"
        )

    def tearDown(self):
        self.dashboard.close()
        self.temp.cleanup()

    def wait_job(self, result):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with self.dashboard.lock:
                job = deepcopy(self.dashboard.jobs[result["job"]])
            if job["status"] != "running":
                return job
            time.sleep(0.01)
        self.fail("Background job did not finish")

    def add_room(self, platform="bilibili", target="123"):
        self.dashboard.action({"action": "add_room", "platform": platform, "target": target})
        return self.dashboard.targets[-1]["id"]

    def test_rooms_and_settings_persist_without_cookies(self):
        room = self.add_room()
        self.dashboard.action({"action": "settings", "values": {"max_messages": 20}})
        self.dashboard.logins["bilibili"] = {"SESSDATA": "secret"}
        self.dashboard.login_names["bilibili"] = "Viewer"
        saved = self.path.read_text(encoding="utf-8")
        self.assertNotIn("secret", saved)
        other = Dashboard(self.path, start=False)
        try:
            self.assertEqual(other.settings["max_messages"], 20)
            self.assertEqual(other.targets[0]["id"], room)
            self.assertEqual(other.logins, {})
        finally:
            other.close()

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI")
    def test_site_cookies_restore_encrypted_and_clear_individually(self):
        self.dashboard.logins = {
            "bilibili": {"SESSDATA": "fixture-bili-secret"},
            "youtube": {"SAPISID": "fixture-youtube-secret"},
            "missevan": {"token": "fixture-me-secret"}, "youtube_page_id": "42",
        }
        self.dashboard.login_names = {site: site for site in ("bilibili", "youtube", "missevan")}
        self.dashboard.save_site_cookies(self.dashboard.logins, self.dashboard.login_names)
        stored = self.path.with_name("html_site_cookies.json").read_text(encoding="utf-8")
        self.assertNotIn("fixture-", stored)
        other = Dashboard(self.path, start=False)
        try:
            self.assertEqual(other.logins, self.dashboard.logins)
            self.assertNotIn("fixture-", json.dumps(other.snapshot()))
            other.action({"action": "clear_login", "site": "bilibili"})
            self.assertNotIn("bilibili", other.logins)
            reloaded = Dashboard(self.path, start=False)
            try:
                self.assertNotIn("bilibili", reloaded.logins)
                self.assertEqual(reloaded.logins["youtube_page_id"], "42")
                reloaded.action({"action": "clear_login", "site": "all"})
                self.assertEqual(json.loads(self.path.with_name("html_site_cookies.json").read_text()), {})
            finally:
                reloaded.close()
        finally:
            other.close()

    def test_unreadable_site_cookies_are_reported_without_secret_content(self):
        self.path.with_name("html_site_cookies.json").write_text(
            json.dumps({"bilibili": "fixture-invalid-encryption"}), encoding="utf-8")
        other = Dashboard(self.path, start=False)
        try:
            self.assertEqual(other.logins, {})
            self.assertIn("Could not decrypt", other.errors[0]["message"])
            self.assertNotIn("fixture-invalid", str(other.errors))
        finally:
            other.close()

    def test_failed_cookie_save_does_not_clear_active_login(self):
        self.dashboard.logins["bilibili"] = {"SESSDATA": "fixture"}
        with patch.object(self.dashboard, "save_site_cookies", side_effect=OSError("disk full")), \
             self.assertRaises(OSError):
            self.dashboard.action({"action": "clear_login", "site": "bilibili"})
        self.assertIn("bilibili", self.dashboard.logins)

    def test_corrupt_or_tampered_saved_settings_do_not_break_startup(self):
            self.dashboard.close()
            self.path.write_text("{not json", encoding="utf-8")
            other = Dashboard(self.path, start=False)
            self.assertEqual((other.settings["max_messages"], other.targets), (100, []))
            other.close()
            self.path.write_text(json.dumps({
                "settings": {"font_size": 99, "max_messages": 999, "unknown": 1},
                "targets": [
                    {"id": "bilibili:1", "platform": "bilibili", "target": "1", "enabled": False},
                    {"id": "bilibili:1", "platform": "bilibili", "target": "1"},
                    {"id": "x", "platform": "evil", "target": "2"}, "bad",
                ],
            }), encoding="utf-8")
            self.dashboard = Dashboard(self.path, start=False)
            self.assertEqual(self.dashboard.settings["max_messages"], 100)
            self.assertNotIn("font_size", self.dashboard.settings)
            self.assertNotIn("unknown", self.dashboard.settings)
            self.assertEqual(self.dashboard.targets, [
                {"id": "bilibili:1", "platform": "bilibili", "target": "1", "enabled": False},
            ])

    def test_invalid_settings_and_duplicate_rooms_are_reported(self):
        self.add_room()
        with self.assertRaisesRegex(ValueError, "already added"):
            self.add_room()
        for values in ({"max_messages": 500}, {"tts_language": "bad"}, {"font_size": True},
                       {"translate_target": "invalid"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.dashboard.action({"action": "settings", "values": values})

    def test_translation_is_nonblocking_and_does_not_mutate_originals(self):
        room = self.add_room("youtube", "abcdefghijk")
        self.dashboard.receive_messages([
            {"_monitor_id": room, "platform": "youtube", "type": "danmaku", "text": "こんにちは"},
            {"_monitor_id": room, "platform": "youtube", "type": "gift", "text": "Sent a gift"},
        ])
        self.dashboard.action({"action": "settings", "values": {
            "translate_enabled": True, "translate_target": "en",
        }})
        with patch("src.translate.prefetch") as prefetch, \
             patch("src.translate.get_translation", return_value=None) as lookup:
            self.assertNotIn("translation", self.dashboard.snapshot()["messages"][0])
            self.assertEqual(lookup.call_count, 2)
            prefetch.assert_called_once_with(["こんにちは", "Sent a gift"], "en")
        with patch("src.translate.prefetch"), patch("src.translate.get_translation", return_value="Hello"):
            state = self.dashboard.snapshot()
        self.assertEqual(state["messages"][0]["translation"], "Hello")
        self.assertEqual(state["paid"][0]["translation"], "Hello")
        self.assertNotIn("translation", self.dashboard.messages[0])
        self.assertNotIn("translation", self.dashboard.messages[1])
        self.dashboard.settings["translate_enabled"] = False
        with patch("src.translate.get_translation") as lookup:
            self.assertNotIn("translation", self.dashboard.snapshot()["messages"][0])
            lookup.assert_not_called()

    def test_feeds_show_only_the_selected_room_of_each_visible_site(self):
        first = self.add_room("bilibili", "1")
        second = self.add_room("bilibili", "2")
        self.dashboard.receive_messages([
            {"_monitor_id": first, "platform": "bilibili", "text": "one"},
            {"_monitor_id": second, "platform": "bilibili", "text": "two"},
            {"_monitor_id": second, "platform": "bilibili", "type": "enter", "author": "Joiner"},
        ])
        state = self.dashboard.snapshot()
        self.assertEqual(state["rooms"]["bilibili"], first)
        self.assertEqual([m["text"] for m in state["messages"]], ["one"])
        self.assertEqual(state["joins"], [])
        self.dashboard.action({"action": "settings", "values": {"selected_rooms": {"bilibili": second}}})
        state = self.dashboard.snapshot()
        self.assertEqual([m["text"] for m in state["messages"]], ["two"])
        self.assertEqual([m["author"] for m in state["joins"]], ["Joiner"])
        self.dashboard.action({"action": "settings", "values": {"visible_sites": ["youtube"]}})
        self.assertEqual(self.dashboard.snapshot()["messages"], [])

    def test_messages_archive_and_latest_500_are_browser_downloadable(self):
        room = self.add_room()
        self.dashboard.receive_messages([{
            "id": str(index), "_monitor_id": room, "platform": "bilibili",
            "type": "danmaku", "text": str(index), "author": "Viewer", "timestamp": "",
        } for index in range(505)])
        job = self.wait_job(self.dashboard.action({"action": "archives"}))
        self.assertEqual(job["status"], "done", job)
        messages = job["result"][0]["messages"]
        self.assertEqual(len(messages), 500)
        self.assertEqual(messages[0]["text"], "504")
        self.assertEqual(messages[-1]["text"], "5")
        session = job["result"][0]["session_id"]
        deleted = self.wait_job(self.dashboard.action({"action": "delete_archive", "session": session}))
        self.assertEqual(deleted["result"], [])

    def test_saving_disabled_does_not_stop_chat(self):
        room = self.add_room()
        self.dashboard.action({"action": "allow_saving", "room": room, "enabled": False})
        self.dashboard.receive_messages([{
            "_monitor_id": room, "platform": "bilibili", "type": "danmaku",
            "text": "hello", "author": "Viewer", "timestamp": "",
        }])
        self.assertEqual(self.dashboard.snapshot()["messages"][0]["text"], "hello")
        self.assertEqual(self.dashboard.load_archives(), [])

    def test_live_notifications_only_fire_on_transitions(self):
        room = self.add_room()
        self.dashboard.receive_statuses({room: {"live": False}})
        self.dashboard.receive_statuses({room: {
            "live": True, "room_name": "Viewer", "title": "Stream title",
            "thumbnail": "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
            "video_id": "abcdefghijk",
        }})
        self.dashboard.receive_statuses({room: {"live": True, "room_name": "Viewer"}})
        self.assertEqual(len(self.dashboard.notifications), 1)
        notification = self.dashboard.notifications[0]
        self.assertEqual(notification["channel"], "Viewer")
        self.assertEqual(notification["platform"], "Bilibili")
        self.assertEqual(notification["detail"], "Stream title")
        self.assertEqual(notification["url"], "https://live.bilibili.com/123")
        self.assertEqual(notification["thumbnail"], "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg")

    def test_live_notification_link_does_not_expose_unsupported_scheme(self):
        room = self.add_room("youtube", "https://www.youtube.com/@creator")
        self.dashboard.receive_statuses({room: {
            "live": True, "room_name": "Creator", "thumbnail": "javascript:alert(1)",
        }})
        notice = self.dashboard.snapshot()["notifications"][0]
        self.assertEqual(notice["url"], "https://www.youtube.com/@creator")
        self.assertEqual(notice["thumbnail"], "")

    def test_gifts_keep_actual_prices_and_untrusted_images_are_removed(self):
        room = self.add_room("youtube", "abcdefghijk")
        self.dashboard.receive_messages([{
            "_monitor_id": room, "platform": "youtube", "type": "gift", "text": "Sent Fired up",
            "currency": "Jewels", "value": 5, "avatar": "https://evil.test/image.png",
            "sticker_url": "https://yt3.ggpht.com/gift.png",
        }])
        state = self.dashboard.snapshot()
        self.assertEqual(state["messages"], [])
        self.assertEqual(state["paid"][0]["value"], 5)
        self.assertEqual(state["paid"][0]["avatar"], "")
        self.assertEqual(state["paid"][0]["sticker_url"], "https://yt3.ggpht.com/gift.png")

    def test_monitor_state_tracks_bilibili_gift_revenue_for_tooltips(self):
        room = self.add_room("bilibili", "123")
        self.dashboard.receive_messages([
            {"_monitor_id": room, "platform": "bilibili", "type": "gift",
             "id": "gift-1", "currency": "¥", "value": 10},
            {"_monitor_id": room, "platform": "bilibili", "type": "gift",
             "id": "gift-1", "currency": "¥", "value": 15},
            {"_monitor_id": room, "platform": "bilibili", "type": "gift",
             "id": "gift-2", "currency": "¥", "value": 2.5},
        ])

        self.assertEqual(self.dashboard.snapshot()["bilibili_gift_revenue"][room], "¥17.5")

    def test_tts_uses_selected_language_and_skips_backlog_and_other_rooms(self):
        room = self.add_room("youtube", "abcdefghijk")
        other = self.add_room("youtube", "bcdefghijkl")
        self.dashboard.action({"action": "settings", "values": {"tts_enabled": True, "tts_language": "ja"}})
        self.dashboard.receive_messages([
            {"_monitor_id": room, "platform": "youtube", "type": "gift", "author": "Viewer", "text": "gift"},
            {"_monitor_id": room, "platform": "youtube", "text": "history", "history": True},
            {"_monitor_id": other, "platform": "youtube", "text": "other room"},
        ])
        self.dashboard.pools["speech"].submit(lambda: None).result(3)
        speech = self.dashboard.snapshot()["speech"]
        self.assertEqual(len(speech), 1)
        self.assertEqual((speech[0]["language"], speech[0]["paid"], speech[0]["room"]), ("ja", True, room))
        self.assertIn("Viewer", speech[0]["text"])

    def test_skip_name_changes_new_and_queued_chat_without_affecting_gift_announcements(self):
        room = self.add_room("youtube", "abcdefghijk")
        for enabled in (False, True):
            self.dashboard.action({"action": "settings", "values": {
                "tts_enabled": True, "tts_skip_name": enabled, "tts_language": "en",
            }})
            self.dashboard.receive_messages([{
                "_monitor_id": room, "platform": "youtube", "author": "Viewer", "text": "hello",
            }])
            self.dashboard.pools["speech"].submit(lambda: None).result(3)
            speech = self.dashboard.snapshot()["speech"][-1]
            self.assertEqual(speech["text_without_name"], "hello")
            self.assertEqual(speech["text_with_name"], "Viewer says hello")
            self.assertEqual(speech["text"], "hello" if enabled else "Viewer says hello")
        message = self.dashboard.snapshot()["messages"][-1]
        self.dashboard.action({"action": "message", "command": "read", "id": message["_html_id"]})
        self.assertEqual(self.dashboard.snapshot()["speech"][-1]["text"], "hello")

    def test_ruby_readings_preserve_text_and_colour_and_can_be_disabled(self):
        room = self.add_room()
        self.dashboard.receive_messages([{
            "_monitor_id": room, "platform": "bilibili", "author": "中文",
            "text": "你好 [doge] 日本語です <script>", "color": 0x12ab34,
            "emotes": {"[doge]": "https://i0.hdslb.com/a.png"},
        }])
        message = self.dashboard.snapshot()["messages"][0]
        self.assertEqual(message["color"], 0x12ab34)
        for key, original in (("_author_readings", "中文"), ("_text_readings", message["text"])):
            self.assertEqual("".join(base for base, _ in message[key]), original)
            self.assertTrue(any(reading for _, reading in message[key]))
        self.assertNotIn("_reading", message)
        self.dashboard.action({"action": "settings", "values": {"show_reading": False}})
        message = self.dashboard.snapshot()["messages"][0]
        self.assertNotIn("_text_readings", message)
        self.assertNotIn("_author_readings", message)

    def test_obs_calls_existing_helpers_and_reports_disconnection(self):
        with patch("src.obs_ctrl.retry_now"), patch("src.obs_ctrl.start_recording", return_value=True) as start:
            self.assertTrue(self.dashboard.obs_action({"command": "start_record"})["ok"])
            start.assert_called_once()
        with patch("src.obs_ctrl.retry_now"), patch("src.obs_ctrl.get_status", return_value={"connected": False}):
            with self.assertRaises(ConnectionError):
                self.dashboard.obs_action({"command": "status"})

    def test_send_goes_to_each_checked_sites_selected_room_in_background(self):
        self.add_room("missevan", "123")
        self.dashboard.logins["missevan"] = {"token": "value"}
        with self.assertRaisesRegex(ValueError, "at least one site"):
            self.dashboard.action({"action": "send", "sites": [], "text": "hello"})
        with patch("src.missevan.send_message", return_value=(True, "")) as send:
            job = self.wait_job(self.dashboard.action({
                "action": "send", "sites": ["missevan", "bilibili"], "text": "hello",
            }))
        self.assertEqual(job["status"], "done", job)
        send.assert_called_once_with("123", "hello")
        self.assertEqual(job["result"]["missevan"], {"ok": True, "error": ""})
        self.assertFalse(job["result"]["bilibili"]["ok"])

    def test_message_actions_block_thank_read_and_mute(self):
        room = self.add_room("bilibili", "123")
        self.dashboard.receive_messages([
            {"_monitor_id": room, "platform": "bilibili", "id": "g1", "type": "gift",
             "author": "Giver", "author_id": "7", "text": "Sent gift", "value": 1, "currency": "CNY"},
            {"_monitor_id": room, "platform": "bilibili", "author": "Spammer", "author_id": "9", "text": "spam"},
        ])
        state = self.dashboard.snapshot()
        gift, spam = state["paid"][0]["_html_id"], state["messages"][0]["_html_id"]
        self.assertEqual(self.dashboard.action({"action": "message", "command": "thank", "id": gift})["thanked"], True)
        with self.assertRaisesRegex(ValueError, "gift or paid"):
            self.dashboard.action({"action": "message", "command": "thank", "id": spam})
        self.dashboard.action({"action": "message", "command": "read", "id": spam})
        self.assertTrue(self.dashboard.snapshot()["speech"][-1]["manual"])
        with patch("src.bilibili.block_user", return_value=(True, "")) as block:
            job = self.wait_job(self.dashboard.action({"action": "message", "command": "mute", "id": spam}))
        self.assertEqual(job["result"], {"muted": "Spammer"})
        block.assert_called_once_with("123", 9)
        self.dashboard.action({"action": "message", "command": "block", "id": spam})
        self.assertEqual(self.dashboard.snapshot()["messages"], [])
        self.assertEqual(self.dashboard.snapshot()["filters"]["blocked_users"], {"bilibili:9": "Spammer"})
        self.dashboard.action({"action": "moderation", "unblock": "bilibili:9", "kind": "user"})
        self.assertEqual(self.dashboard.snapshot()["filters"]["blocked_users"], {})
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.dashboard.action({"action": "message", "command": "block", "id": spam})
        other = Dashboard(self.path, start=False)
        try:
            self.assertEqual(other.thanked, {"g1"})
        finally:
            other.close()

    def test_moderation_allow_and_block_patterns(self):
        for allow in (False, True):
            self.dashboard.action({"action": "moderation", "pattern": "spam", "allow": allow})
        with self.assertRaisesRegex(ValueError, "Invalid pattern"):
            self.dashboard.action({"action": "moderation", "pattern": "(", "allow": True})
        filters = self.dashboard.snapshot()["filters"]
        self.assertIn("spam", json.dumps(filters))
        for allow in (False, True):
            self.dashboard.action({"action": "moderation", "pattern": "spam", "allow": allow, "remove": True})
        self.assertNotIn("spam", json.dumps(self.dashboard.snapshot()["filters"]))

    def test_analytics_and_hotspot_exports(self):
        room = self.add_room()
        with self.assertRaisesRegex(ValueError, "No chat hotspots"):
            self.dashboard.action({"action": "export_hotspots", "format": "csv", "room": room})
        self.dashboard.receive_messages([{
            "_monitor_id": room, "platform": "bilibili", "author": f"V{index % 3}", "text": "lol",
            "timestamp": 1700000000 + (index * 30 if index < 20 else 600),
        } for index in range(40)])
        result = self.dashboard.action({"action": "analytics", "room": room})
        self.assertEqual(result["messages"], 40)
        self.assertIn(["Messages", "bilibili", 40, "All recorded messages"], result["rows"])
        self.assertGreater(result["hotspots"], 0)
        for kind in ("csv", "edl"):
            exported = self.dashboard.action({"action": "export_hotspots", "format": kind, "room": room})
            self.assertEqual(exported["filename"], f"chat-hotspots.{kind}")
            self.assertTrue(exported["text"])
        with self.assertRaisesRegex(ValueError, "Unknown export"):
            self.dashboard.action({"action": "export_hotspots", "format": "exe", "room": room})

    def test_overlay_url_starts_shared_server(self):
        room = self.add_room("bilibili", "123")
        self.dashboard.action({"action": "settings", "values": {"overlay_count": 7, "overlay_show_names": False}})
        with patch("src.overlay_server.ensure_started") as started:
            job = self.wait_job(self.dashboard.action({"action": "overlay", "rooms": {"bilibili": room}}))
        self.assertEqual(job["status"], "done", job)
        started.assert_called_once()
        url = job["result"]["url"]
        self.assertIn("/overlay?", url)
        self.assertIn("bili=123", url)
        self.assertIn("n=7", url)
        self.assertIn("names=0", url)
        failed = self.wait_job(self.dashboard.action({"action": "overlay", "rooms": {}}))
        self.assertEqual(failed["status"], "failed")

    def test_room_event_log_ignores_feed_filters_and_survives_restart(self):
        first = self.add_room("bilibili", "1")
        second = self.add_room("bilibili", "2")
        self.dashboard.action({"action": "allow_saving", "room": second, "enabled": False})
        self.dashboard.action({"action": "settings", "values": {"visible_sites": []}})
        self.dashboard.action({"action": "moderation", "pattern": "blocked"})
        self.dashboard.receive_messages([{
            "_monitor_id": second, "platform": "bilibili", "type": "danmaku",
            "author": "Viewer", "text": "blocked", "id": str(index),
        } for index in range(3105)])
        self.dashboard.receive_messages([
            {"_monitor_id": first, "platform": "bilibili", "type": "gift", "value": 2,
             "currency": "CNY", "text": "gift", "gift_count": 3, "original_value": 6},
            {"_monitor_id": first, "platform": "bilibili", "type": "enter", "author": "Joiner"},
        ])
        self.dashboard.receive_statuses({
            first: {"live": True, "viewers": 10}, second: {"live": True, "viewers": 50}})
        self.dashboard.receive_statuses({
            first: {"live": False, "viewers": 0}, second: {"live": True, "viewers": 60}})
        self.dashboard.action({"action": "clear_chat"})
        first_result = self.dashboard.action({"action": "analytics", "room": first})
        second_result = self.dashboard.action({"action": "analytics", "room": second})
        self.assertEqual(first_result["messages"], 1)
        self.assertEqual(first_result["counts"]["join"], 1)
        self.assertEqual(first_result["viewers"], [{"site": "bilibili", "now": 0, "peak": 10}])
        self.assertEqual(second_result["messages"], 3105)
        self.assertEqual(second_result["viewers"], [{"site": "bilibili", "now": 60, "peak": 60}])
        self.assertEqual(self.dashboard.snapshot()["messages"], [])
        self.dashboard.close()
        self.dashboard = Dashboard(self.path, start=False)
        self.assertEqual(self.dashboard.action({"action": "analytics", "room": second})["messages"], 3105)
        self.dashboard.action({"action": "remove_room", "room": first})
        rooms = self.dashboard.action({"action": "event_rooms"})
        self.assertIn(first, [row["room"] for row in rooms])
        self.dashboard.action({"action": "delete_room_events", "room": first})
        self.assertEqual(self.dashboard.action({"action": "analytics", "room": first})["events"], 0)
        self.assertEqual(self.dashboard.action({"action": "analytics", "room": second})["messages"], 3105)

    def test_event_recording_failure_is_visible_and_analysis_requires_room(self):
        room = self.add_room()
        with patch.object(self.dashboard.event_store, "append", side_effect=OSError("disk full")):
            self.dashboard.receive_messages([{
                "_monitor_id": room, "platform": "bilibili", "text": "hello",
            }])
            self.dashboard.event_query(lambda: None)
        self.assertEqual(self.dashboard.snapshot()["event_recording"]["error"], "disk full")
        self.assertIn("Room event recording failed", self.dashboard.errors[-1]["message"])
        for action in ("analytics", "room_events", "delete_room_events", "export_hotspots"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "Select a room"):
                self.dashboard.action({"action": action})

    def test_record_arming_persists_and_kaomoji_emotes_load_offline(self):
        room = self.add_room()
        with patch.object(self.dashboard, "sync_recording"):
            self.wait_job(self.dashboard.action({"action": "record", "room": room, "enabled": True}))
        self.assertEqual(self.dashboard.snapshot()["record_armed"], [room])
        other = Dashboard(self.path, start=False)
        try:
            self.assertEqual(other.record_armed, {room})
        finally:
            other.close()
        job = self.wait_job(self.dashboard.action({"action": "emotes", "site": "kaomoji"}))
        self.assertEqual(job["status"], "done", job)
        self.assertTrue(job["result"]["groups"][0]["entries"])
        failed = self.wait_job(self.dashboard.action({"action": "emotes", "site": "youtube"}))
        self.assertEqual(failed["status"], "failed")

    def test_youtube_account_actions_require_cookies_and_use_shared_helpers(self):
        with self.assertRaisesRegex(ValueError, "YouTube cookies"):
            self.dashboard.action({"action": "youtube_accounts"})
        self.dashboard.logins["youtube"] = {"SAPISID": "x"}
        channels = [{"name": "Main", "page_id": ""}, {"name": "Brand", "page_id": "42"}]
        with patch("src.youtube_web.list_channels", return_value={"channels": channels}):
            job = self.wait_job(self.dashboard.action({"action": "youtube_accounts"}))
        self.assertEqual(job["result"], {"channels": channels, "selected": ""})
        result = self.dashboard.action({"action": "youtube_account", "page_id": "42"})
        self.assertEqual(result, {"ok": True, "page_id": "42"})
        self.assertEqual(self.dashboard.logins["youtube_page_id"], "42")
        self.assertEqual(self.dashboard.snapshot()["logins"]["youtube"]["page_id"], "42")
        self.add_room("youtube", "abcdefghijk")

        def send(*args):
            from src import youtube_web
            self.assertEqual(youtube_web.selected_page_id(), "42")
            return True, ""

        with patch("src.youtube.send_chat", side_effect=send):
            job = self.wait_job(self.dashboard.action({
                "action": "send", "sites": ["youtube"], "text": "hello",
            }))
        self.assertEqual(job["result"]["youtube"], {"ok": True, "error": ""})
        with patch("src.youtube_web.list_channels", return_value={"channels": channels}):
            job = self.wait_job(self.dashboard.action({"action": "youtube_accounts"}))
        self.assertEqual(job["result"]["selected"], "42")
        result = self.dashboard.action({"action": "youtube_account", "page_id": ""})
        self.assertEqual(result, {"ok": True, "page_id": ""})
        self.assertNotIn("youtube_page_id", self.dashboard.logins)

    def test_transcription_uses_existing_source_resolver(self):
        room = self.add_room("youtube", "abcdefghijk")
        transcriber = Mock()
        with patch("src.caption_engine.StreamingTranscriber", return_value=transcriber) as create:
            self.dashboard.transcribe({"room": room, "model": "base", "language": "ja"})
            resolver = create.call_args.args[2]
            with patch("src.transcription.resolve_youtube_audio_source", return_value={"url": "audio"}) as source:
                self.assertEqual(resolver(), {"url": "audio"})
                source.assert_called_once_with("https://www.youtube.com/watch?v=abcdefghijk")
        transcriber.start.assert_called_once()

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI")
    def test_transcription_settings_and_encrypted_key_persist_without_key_in_snapshot(self):
        values = {
            "transcribe_provider": "openai_compatible", "transcribe_model": "base",
            "transcribe_source_language": "zh", "transcribe_target_language": "ja",
            "transcribe_api_base": "http://localhost:1234/v1", "transcribe_api_model": "custom",
            "transcribe_background": "Gaming", "transcribe_glossary": "HP: health",
            "transcribe_context_sentences": 2,
        }
        self.dashboard.action({"action": "transcription_settings", "values": values, "api_key": "fixture-api-key"})
        saved = self.path.read_text(encoding="utf-8")
        self.assertNotIn("fixture-api-key", saved)
        self.assertTrue(json.loads(saved)["transcription_api_key_dpapi"])
        self.assertNotIn("fixture-api-key", json.dumps(self.dashboard.snapshot()))
        other = Dashboard(self.path, start=False)
        try:
            self.assertEqual(other.transcription_api_key, "fixture-api-key")
            for key, value in values.items():
                self.assertEqual(other.settings[key], value)
            self.assertEqual(other.settings["translate_target"], "en")
            other.action({"action": "transcription_settings", "api_key": ""})
            self.assertEqual(other.transcription_api_key, "fixture-api-key")
            other.action({"action": "transcription_settings", "clear_api_key": True})
            self.assertFalse(other.snapshot()["transcription_api"]["key_saved"])
            self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["transcription_api_key_dpapi"], "")
        finally:
            other.close()

    @patch("src.api_secrets.protect", return_value="encrypted-fixture")
    def test_transcription_start_uses_saved_engine_and_translation_options(self, protect):
        room = self.add_room()
        self.dashboard.action({"action": "transcription_settings", "values": {
            "transcribe_model": "base", "transcribe_source_language": "zh",
            "transcribe_target_language": "ja", "transcribe_provider": "openai_compatible",
        }, "api_key": "fixture-api-key"})
        with patch("src.caption_engine.StreamingTranscriber") as create:
            self.dashboard.transcribe({"room": room})
        self.assertEqual(create.call_args.args[3], "ja")
        self.assertEqual(create.call_args.kwargs["model_size"], "base")
        self.assertEqual(create.call_args.kwargs["options"].source_language, "zh")
        self.assertEqual(create.call_args.kwargs["options"].api_key, "fixture-api-key")

    @patch("src.api_secrets.protect", return_value="encrypted-fixture")
    def test_transcription_invalid_options_and_save_failure_do_not_replace_settings_or_key(self, protect):
        original = deepcopy(self.dashboard.settings)
        for values in ({"transcribe_model": "invalid"}, {"transcribe_source_language": "zh"},
                       {"transcribe_context_sentences": -1}, {"transcribe_api_base": "not a URL"},
                       {"transcribe_api_model": ""}, {"tts_volume": 40}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.dashboard.action({"action": "transcription_settings", "values": values})
        with patch.object(self.dashboard, "save", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.dashboard.action({"action": "transcription_settings", "api_key": "fixture-api-key",
                                   "values": {"transcribe_model": "base"}})
        self.assertEqual(self.dashboard.settings, original)
        self.assertEqual(self.dashboard.transcription_api_key, "")
        self.assertEqual(self.dashboard.transcription_api_key_dpapi, "")

    @patch("src.api_secrets.protect", return_value="encrypted-fixture")
    def test_unreadable_saved_key_is_visible_and_can_be_replaced(self, protect):
        self.dashboard.save()
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        saved["transcription_api_key_dpapi"] = "not valid encrypted data"
        self.path.write_text(json.dumps(saved), encoding="utf-8")
        other = Dashboard(self.path, start=False)
        try:
            self.assertIn("Re-enter", other.snapshot()["transcription_api"]["error"])
            with self.assertRaisesRegex(ValueError, "Re-enter"):
                other.action({"action": "transcription_settings"})
            other.action({"action": "transcription_settings", "api_key": "fixture-new-key"})
            self.assertFalse(other.snapshot()["transcription_api"]["error"])
        finally:
            other.close()

    def test_model_discovery_and_translation_test_use_unsaved_form_without_mutating_settings(self):
        data = {"values": {"transcribe_api_base": "http://localhost:1234/v1",
                           "transcribe_api_model": "fixture-model"}, "api_key": "fixture-key"}
        with patch("src.openai_compatible_translate.list_models", return_value=["fixture-model"]) as models:
            job = self.wait_job(self.dashboard.action({"action": "transcription_models", **data}))
        self.assertEqual(job["result"]["models"], ["fixture-model"])
        models.assert_called_once_with("http://localhost:1234/v1", "fixture-key")
        with patch("src.openai_compatible_translate.translate_batch", return_value=[("こんにちは", "")]) as translate:
            job = self.wait_job(self.dashboard.action({"action": "transcription_test", **data}))
        self.assertEqual(job["result"]["text"], "こんにちは")
        self.assertEqual(translate.call_args.kwargs["api_key"], "fixture-key")
        self.assertEqual(self.dashboard.transcription_api_key, "")
        self.assertEqual(self.dashboard.settings["transcribe_api_model"], "gpt-4o-mini")
        self.assertNotIn("fixture-key", json.dumps(self.dashboard.snapshot()))

    @patch("src.api_secrets.protect", return_value="encrypted-fixture")
    def test_shared_api_translates_chat_gifts_speech_and_running_transcription(self, protect):
        room = self.add_room()
        self.dashboard.action({"action": "transcription_settings", "values": {
            "transcribe_provider": "openai_compatible", "transcribe_api_model": "shared-model",
            "transcribe_api_base": "http://localhost:1234/v1",
        }, "api_key": "fixture-key"})
        self.dashboard.settings.update(translate_enabled=True, translate_target="ja",
                                       tts_translate=True, tts_language="ja", tts_skip_name=True)
        messages = [
            {"_monitor_id": room, "platform": "bilibili", "type": "danmaku", "author": "A", "text": "hello"},
            {"_monitor_id": room, "platform": "bilibili", "type": "gift", "author": "B", "text": "Sent a gift"},
        ]
        from src.caption_engine import Recognition, StreamingTranscriber
        session = StreamingTranscriber("bilibili", "123", lambda: "", "ja",
                                      translation_function=self.dashboard.translate_text)
        recognizer = Mock()
        recognizer.recognize.return_value = Recognition("spoken words", "en")
        with patch("src.openai_compatible_translate.translate_batch", return_value=[("訳文", "")]) as api, \
             patch("src.translate.translate") as environment:
            self.dashboard.receive_messages(messages)
            self.dashboard.translations().prefetch(["hello", "Sent a gift"], "ja", wait=2)
            state = self.dashboard.snapshot()
            self.assertEqual(state["messages"][0]["translation"], "訳文")
            self.assertEqual(state["paid"][0]["translation"], "訳文")
            self.dashboard.compose_speech(messages[0], "hello", self.dashboard.settings, False, False)
            self.dashboard.compose_speech(messages[1], "Sent a gift", self.dashboard.settings, True, False)
            session._recognize_segment(recognizer, 0, [])
            self.assertEqual(session.snapshot()["segments"][0]["translated"], "訳文")
            for call in api.call_args_list:
                self.assertEqual(call.kwargs["model"], "shared-model")
                self.assertEqual(call.kwargs["api_base"], "http://localhost:1234/v1")
                self.assertEqual(call.kwargs["api_key"], "fixture-key")
            self.dashboard.action({"action": "transcription_settings",
                                   "values": {"transcribe_api_model": "replacement-model"}})
            self.dashboard.translations().prefetch(["hello", "Sent a gift"], "ja", wait=2)
            session._recognize_segment(recognizer, 1, [])
            self.assertEqual(api.call_args.kwargs["model"], "replacement-model")
            self.assertEqual(self.dashboard.translations().get_translation("hello", "ja"), "訳文")
            environment.assert_not_called()
        self.assertIn("訳文", self.dashboard.speech[-1]["text"])
        self.assertNotIn("fixture-key", json.dumps(self.dashboard.snapshot()))

    def test_shared_translation_error_is_visible_without_environment_fallback(self):
        self.dashboard.settings["transcribe_provider"] = "openai_compatible"
        with patch("src.openai_compatible_translate.translate_batch", side_effect=ValueError("private-key")), \
             patch("src.translate.translate") as fallback:
            self.dashboard.translations().prefetch(["hello"], "ja", wait=2)
        fallback.assert_not_called()
        self.assertIn("Translation API request failed", self.dashboard.errors[-1]["message"])
        self.assertNotIn("private-key", str(self.dashboard.errors))

    def test_background_failure_is_visible_and_jobs_do_not_block_status(self):
        room = self.add_room()
        release = threading.Event()
        def blocked():
            if not release.wait(10):
                raise TimeoutError("Test request not released")
            raise RuntimeError("network failure")
        job = self.dashboard.submit("network", "test", blocked)
        try:
            self.dashboard.receive_statuses({room: {"live": True}})
            self.assertTrue(self.dashboard.snapshot()["statuses"][room]["live"])
            with self.assertRaisesRegex(ValueError, "already running"):
                self.dashboard.submit("network", "test", blocked)
        finally:
            release.set()
        result = self.wait_job(job)
        self.assertEqual(result["status"], "failed")
        self.assertIn("network failure", self.dashboard.errors[-1]["message"])

    def test_one_cookie_import_signs_in_every_verified_site(self):
        header = "SESSDATA=bili; bili_jct=csrf; SAPISID=yt; SID=sid; token=me"
        with patch("src.browser_cookies.verify_bilibili_login",
                   return_value={"is_login": True, "uname": "BiliUser"}), \
             patch("src.youtube_web.verify_login",
                   return_value={"is_login": True, "name": "YouTubeUser"}), \
             patch("src.missevan.verify_login", return_value={"is_login": False}):
            job = self.wait_job(self.dashboard.action({"action": "import_cookies", "text": header}))
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(set(job["result"]["signed_in"]), {"bilibili", "youtube"})
        self.assertIn("rejected", job["result"]["failed"]["missevan"])
        self.assertNotIn("cookies", json.dumps(job["result"]["signed_in"]))
        # Bilibili keeps only its login cookies, as on the desktop.
        self.assertEqual(self.dashboard.logins["bilibili"], {"SESSDATA": "bili", "bili_jct": "csrf"})
        self.assertEqual(self.dashboard.logins["youtube"]["SAPISID"], "yt")
        self.assertNotIn("missevan", self.dashboard.logins)
        logins = self.dashboard.snapshot()["logins"]
        self.assertEqual(logins["bilibili"], {"signed_in": True, "name": "BiliUser"})
        self.assertEqual(logins["missevan"], {"signed_in": False, "name": ""})
        self.assertNotIn("bili", self.path.read_text(encoding="utf-8") if self.path.exists() else "")
        self.dashboard.action({"action": "clear_login", "site": "all"})
        self.assertEqual(self.dashboard.logins, {})

    def test_empty_cookie_import_reads_all_installed_browsers(self):
        from src import browser_cookies as bc

        def read(browser, domain):
            if browser == "chrome":
                raise bc.CookieReadError("Chrome requires administrator rights.")
            if browser == "firefox" and domain == "missevan.com":
                return {"token": "me"}
            if browser == "edge" and domain == "bilibili.com":
                return {"SESSDATA": "edge"}
            return {}

        with patch("src.browser_cookies.read_cookies", side_effect=read), \
             patch("src.browser_cookies.verify_bilibili_login",
                   return_value={"is_login": True, "uname": "B"}), \
             patch("src.missevan.verify_login", return_value={"is_login": True, "username": "M"}), \
             patch("src.youtube_web.verify_login") as youtube:
            job = self.wait_job(self.dashboard.action({"action": "import_cookies", "text": ""}))
        result = job["result"]
        self.assertEqual(result["signed_in"]["missevan"], {"name": "M", "source": "Firefox"})
        self.assertEqual(result["signed_in"]["bilibili"]["source"], "Edge")
        self.assertEqual(result["failed"]["youtube"], "No login cookies found.")
        self.assertEqual(result["browser_errors"], {"Chrome": "Chrome requires administrator rights."})
        youtube.assert_not_called()

    def test_interface_language_is_validated_and_html_strings_are_translated(self):
        self.dashboard.action({"action": "settings", "values": {"ui_language": "ja"}})
        other = Dashboard(self.path, start=False)
        try:
            self.assertEqual(other.settings["ui_language"], "ja")
        finally:
            other.close()
        with self.assertRaisesRegex(ValueError, "interface language"):
            self.dashboard.action({"action": "settings", "values": {"ui_language": "fr"}})
        import re
        from html.parser import HTMLParser

        assets = Path(__file__).resolve().parent.parent / "assets" / "html_dashboard"
        keys = set()

        class Collector(HTMLParser):
            def handle_starttag(self, tag, attrs):
                keys.update(value for name, value in attrs
                            if name in ("placeholder", "aria-label", "title") and value)

            def handle_data(self, data):
                if data.strip():
                    keys.add(data.strip())

        Collector().feed((assets / "index.html").read_text(encoding="utf-8"))
        keys |= set(re.findall(r'\bt\("((?:[^"\\]|\\.)*)"',
                               (assets / "dashboard.js").read_text(encoding="utf-8")))
        untranslatable = {"YouTube", "Bilibili", "MissEvan", "OBS", "tiny", "base", "small", "English",
                          "CPU", "RAM", "FPS"}
        for lang in ("zh", "ja"):
            missing = keys - untranslatable - set(html_app.catalog(lang))
            self.assertEqual(missing, set(), lang)

    def test_local_http_api_authentication_assets_and_actions(self):
        server, token = make_server(self.dashboard, 0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(url) as response:
                self.assertIn(b"Monitoring / Cookies", response.read())
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            with self.assertRaises(HTTPError) as error:
                urlopen(url + "/api/state")
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            headers = {"X-Dashboard-Token": token, "Content-Type": "application/json"}
            request = Request(url + "/api/action", data=json.dumps({
                "action": "add_room", "platform": "bilibili", "target": "123",
            }).encode(), headers=headers)
            with urlopen(request) as response:
                self.assertTrue(json.load(response)["ok"])
            with urlopen(Request(url + "/api/state", headers=headers)) as response:
                state = json.load(response)
                self.assertEqual(state["targets"][0]["target"], "123")
                self.assertNotIn("token", state)
            room = "bilibili:123"
            self.dashboard.receive_messages([{
                "_monitor_id": room, "platform": "bilibili", "text": "export me",
            }])
            with self.assertRaises(HTTPError) as error:
                urlopen(url + "/api/room-events?room=" + room)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            with urlopen(Request(url + "/api/room-events?room=" + room, headers=headers)) as response:
                events = [json.loads(line) for line in response.read().decode().splitlines()]
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["payload"]["text"], "export me")
                self.assertEqual(events[0]["room"], room)
            for changed in ({"Origin": "https://evil.test"}, {"Host": "evil.test"}):
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(url + "/api/state", headers={**headers, **changed}))
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url + "/api/action", data=b'{"action":"unknown"}', headers=headers))
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url + "/api/action",
                                data=b'{"action":"moderation","pattern":"["}', headers=headers))
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
            with urlopen(url + "/i18n.json") as response:
                catalog = json.load(response)
            self.assertEqual(set(catalog["languages"]), {"en", "zh", "ja"})
            self.assertEqual(catalog["strings"]["zh"]["Import cookies for all sites"], "为所有网站导入 Cookie")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
