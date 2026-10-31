import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import desktop_app
from src import i18n


@unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
class MonitorLiveIndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (
            desktop_app.QtWidgets.QApplication.instance()
            or desktop_app.QtWidgets.QApplication([])
        )

    def test_indicator_colors_and_localized_status(self):
        indicator = desktop_app.QtWidgets.QLabel()
        for live, color, status in (
            (True, "#16803c", "Live"),
            (False, "#b42318", "Offline"),
            (None, "#666666", "Connecting"),
        ):
            with self.subTest(live=live):
                desktop_app._set_monitor_live_indicator(
                    indicator, live, "zh", i18n
                )
                self.assertIn(color, indicator.styleSheet())
                self.assertEqual(indicator.toolTip(), i18n.translate(status, "zh"))
                self.assertEqual(indicator.accessibleName(), indicator.toolTip())

    def test_zone_label_is_localized_without_changing_category_names(self):
        self.assertEqual(
            i18n.translate("Zone: {zone}", "zh", zone="虚拟主播 / 虚拟PK"),
            "分区：虚拟主播 / 虚拟PK",
        )
        self.assertEqual(
            i18n.translate("Zone: {zone}", "ja", zone="虚拟主播 / 虚拟PK"),
            "カテゴリ: 虚拟主播 / 虚拟PK",
        )

    def test_status_updates_change_indicator_for_each_site(self):
        for platform in ("youtube", "bilibili", "missevan"):
            with self.subTest(platform=platform):
                monitor_id = f"{platform}:123"
                indicator = desktop_app.QtWidgets.QLabel()
                card = {
                    key: Mock()
                    for key in (
                        "widget", "title", "stream_title", "detail",
                        "connection", "unload_stream",
                    )
                }
                card["live_indicator"] = indicator
                window = SimpleNamespace(
                    _monitor_cards={monitor_id: card},
                    _monitor_targets=[{
                        "id": monitor_id, "platform": platform,
                        "target": "123", "enabled": True,
                    }],
                    _room_names={}, _room_titles={}, _live_states={},
                    _transcription_armed_id=None, _record_enabled_ids=set(),
                    _recorders={}, _worker=None, _viewer_samples=[],
                    _ui_language="en", i18n=i18n,
                    config=SimpleNamespace(ANALYTICS_ENABLED=False),
                    notify_live_check=Mock(), _notify_live_stream=Mock(),
                    live_status=Mock(), _stop_recording=Mock(),
                )
                for info, status in (
                    ({"live": True}, "Live"),
                    ({"live": False}, "Offline"),
                    ({}, "Connecting"),
                ):
                    desktop_app._DesktopWindow._update_statuses(
                        window, {monitor_id: info}
                    )
                    self.assertEqual(indicator.toolTip(), status)

    def test_rebuilt_card_retains_known_live_state_beside_id(self):
        widget = desktop_app.QtWidgets.QWidget()
        grid = desktop_app.QtWidgets.QGridLayout(widget)
        window = SimpleNamespace(
            channel_grid=grid,
            _monitor_targets=[{
                "id": "missevan:123", "platform": "missevan",
                "target": "123", "enabled": True,
            }],
            _live_states={"missevan:123": True},
            _record_enabled_ids=set(), _ui_language="en", i18n=i18n,
            _monitor_target_changed=Mock(), _set_recording=Mock(),
            _unload_youtube_stream=Mock(), _remove_monitor_target=Mock(),
            _layout_channel_cards=Mock(), _apply_theme=Mock(),
            _refresh_recording_status=Mock(),
        )
        desktop_app._DesktopWindow._refresh_monitor_cards(window)
        card = window._monitor_cards["missevan:123"]
        indicator = card["live_indicator"]
        self.assertEqual(indicator.toolTip(), "Live")
        self.assertEqual(indicator.width(), 10)
        row = card["widget"].layout().itemAt(2).layout()
        self.assertIs(row.itemAt(0).widget(), indicator)
        self.assertIs(row.itemAt(1).widget(), card["detail"])


if __name__ == "__main__":
    unittest.main()
