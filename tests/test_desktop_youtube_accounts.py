import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import desktop_app
from src import user_login


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
