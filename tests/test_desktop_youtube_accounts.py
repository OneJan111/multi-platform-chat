import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import desktop_app
from src import user_login
from src import browser_cookies


class _ComboBox:
    def __init__(self):
        self.items = []
        self.index = -1
        self.signals_blocked = False

    def blockSignals(self, blocked):
        previous = self.signals_blocked
        self.signals_blocked = blocked
        return previous

    def clear(self):
        self.items.clear()
        self.index = -1

    def addItem(self, label, value):
        self.items.append((label, value))
        if self.index < 0:
            self.index = 0

    def findData(self, value):
        return next((i for i, (_, item_data) in enumerate(self.items) if item_data == value), -1)

    def setCurrentIndex(self, index):
        self.index = index

    def itemData(self, index):
        return self.items[index][1]


class DesktopYouTubeAccountTests(unittest.TestCase):
    def _cookie_window(self, logins=None):
        window = SimpleNamespace(
            cookie_browser=Mock(), cookie_site=Mock(), cookie_input=Mock(),
            cookie_status=Mock(), _login_data=logins if logins is not None else {},
            _ui_language="en",
            i18n=SimpleNamespace(translate=lambda text, language, **kwargs: text.format(**kwargs)),
            _persist_logins=Mock(return_value=True),
            _reset_youtube_account_combo=Mock(),
            _run_task=lambda function, callback: callback(function()),
        )
        window.cookie_browser.currentText.return_value = "Firefox"
        window.cookie_site.currentText.return_value = "Bilibili"
        return window

    def test_firefox_import_verifies_and_saves_all_sites_without_displaying_cookie_values(self):
        window = self._cookie_window({"youtube_page_id": "old-channel"})
        with patch("src.browser_cookies.read_cookies", side_effect=[
            {"SESSDATA": "bili-cookie", "unrelated": "discard"},
            {"SAPISID": "youtube-cookie"}, {"session": "missevan-cookie"},
        ]) as read, \
                patch("src.browser_cookies.verify_bilibili_login", return_value={"is_login": True, "uname": "Bili"}), \
                patch("src.youtube_web.verify_login", return_value={"is_login": True, "name": "YouTube"}), \
                patch("src.missevan.verify_login", return_value={"is_login": True, "username": "MissEvan"}):
            desktop_app._DesktopWindow._read_browser_cookies(window)

        self.assertEqual(read.call_args_list, [
            call("firefox", domain) for domain in browser_cookies.SITES.values()
        ])
        self.assertEqual(window._login_data, {
            "bilibili": {"SESSDATA": "bili-cookie"},
            "youtube": {"SAPISID": "youtube-cookie"},
            "missevan": {"session": "missevan-cookie"},
        })
        window._persist_logins.assert_called_once()
        window._reset_youtube_account_combo.assert_called_once()
        window.cookie_input.setText.assert_not_called()
        message = window.cookie_status.setText.call_args.args[0]
        for site in browser_cookies.SITES:
            self.assertIn(site + ": signed in as", message)
        self.assertNotIn("-cookie", message)

    def test_partial_firefox_import_keeps_failed_site_login_and_manual_input(self):
        window = self._cookie_window({
            "bilibili": {"SESSDATA": "old-bili"},
            "youtube": {"SAPISID": "old-youtube"}, "youtube_page_id": "keep-channel",
        })
        with patch("src.browser_cookies.read_cookies", side_effect=[
            browser_cookies.CookieReadError("profile locked"),
            {"SAPISID": "expired"}, {"session": "new-missevan"},
        ]), \
                patch("src.youtube_web.verify_login", return_value={"is_login": False, "error": "expired"}), \
                patch("src.missevan.verify_login", return_value={"is_login": True, "username": "MissEvan"}):
            desktop_app._DesktopWindow._read_browser_cookies(window)

        self.assertEqual(window._login_data["bilibili"], {"SESSDATA": "old-bili"})
        self.assertEqual(window._login_data["youtube"], {"SAPISID": "old-youtube"})
        self.assertEqual(window._login_data["youtube_page_id"], "keep-channel")
        self.assertEqual(window._login_data["missevan"], {"session": "new-missevan"})
        window._persist_logins.assert_called_once()
        window._reset_youtube_account_combo.assert_not_called()
        window.cookie_input.clear.assert_not_called()
        message = window.cookie_status.setText.call_args.args[0]
        self.assertIn("profile locked", message)
        self.assertIn("expired", message)

    def test_empty_browser_cookies_do_not_save_or_remove_existing_logins(self):
        window = self._cookie_window({"youtube": {"SAPISID": "existing"}})
        with patch("src.browser_cookies.read_cookies", return_value={}):
            desktop_app._DesktopWindow._read_browser_cookies(window)
        self.assertEqual(window._login_data, {"youtube": {"SAPISID": "existing"}})
        window._persist_logins.assert_not_called()
        message = window.cookie_status.setText.call_args.args[0]
        for site in browser_cookies.SITES:
            self.assertIn(f"No {site} cookies found in Firefox.", message)

    def test_import_reports_persistence_failure_and_keeps_pasted_import_site_specific(self):
        window = self._cookie_window()
        window._persist_logins.return_value = False
        window._login_context = lambda: user_login.using(window._login_data)
        window.cookie_input.text.return_value = "SESSDATA=new-bili"
        with patch("src.browser_cookies.verify_bilibili_login", return_value={"is_login": True, "uname": "Bili"}), \
                patch("src.youtube_web.verify_login") as youtube, \
                patch("src.missevan.verify_login") as missevan:
            desktop_app._DesktopWindow._import_cookies(window)
        youtube.assert_not_called()
        missevan.assert_not_called()
        self.assertIn("Unable to save login cookies", window.cookie_status.setText.call_args.args[0])

    def test_discovery_populates_youtube_channels_and_preserves_current_selection(self):
        combo = _ComboBox()
        combo.addItem("stale account", 5)
        status = Mock()
        window = SimpleNamespace(
            _login_data={"youtube": {"SAPISID": "cookie"}, "youtube_page_id": "UC-second"},
            youtube_account_combo=combo,
            cookie_status=status,
            _run_task=lambda function, callback: callback(function()),
        )
        result = {
            "channels": [
                {"page_id": "UC-primary", "name": "Primary", "handle": "@primary"},
                {"page_id": "UC-second", "name": "Creator", "handle": "@creator"},
            ],
        }

        with patch("src.youtube_web.list_channels", return_value=result) as discover:
            desktop_app._DesktopWindow._discover_youtube_channels(window)

        discover.assert_called_once_with({"SAPISID": "cookie"})
        self.assertEqual(
            combo.items,
            [("Primary (@primary)", "UC-primary"), ("Creator (@creator)", "UC-second")],
        )
        self.assertEqual(combo.index, 1)
        self.assertFalse(combo.signals_blocked)
        status.setText.assert_called_with(
            "Found 2 YouTube account(s)/channel(s). Choose one to use for chat."
        )

    def test_selection_persists_youtube_page_id(self):
        combo = _ComboBox()
        combo.addItem("Creator", "UC-second")
        login_data = {
            "youtube": {"SAPISID": "cookie"},
            "youtube_page_id": "UC-first",
        }
        status = Mock()
        window = SimpleNamespace(
            user_login=user_login,
            _login_data=login_data,
            youtube_account_combo=combo,
            cookie_status=status,
            _ui_language="en",
            i18n=SimpleNamespace(translate=lambda text, language: text),
            _persist_logins=Mock(return_value=True),
            _login_context=lambda: user_login.using(login_data),
        )

        desktop_app._DesktopWindow._select_youtube_channel(window, 0)

        self.assertEqual(login_data["youtube_page_id"], "UC-second")
        window._persist_logins.assert_called_once_with()
        status.setText.assert_called_with("YouTube chat account/channel selection saved.")

    def test_discovery_error_is_reported_without_clearing_channel_choices(self):
        combo = _ComboBox()
        combo.addItem("Account 2", 1)
        status = Mock()
        window = SimpleNamespace(
            _login_data={"youtube": {"SAPISID": "cookie"}},
            youtube_account_combo=combo,
            cookie_status=status,
            _run_task=lambda function, callback: callback(function()),
        )
        with patch(
            "src.youtube_web.list_channels",
            return_value={"channels": [], "error": "temporary network error"},
        ):
            desktop_app._DesktopWindow._discover_youtube_channels(window)

        self.assertEqual(combo.items, [("Account 2", 1)])
        status.setText.assert_called_with(
            "Could not list YouTube accounts: temporary network error"
        )


if __name__ == "__main__":
    unittest.main()
