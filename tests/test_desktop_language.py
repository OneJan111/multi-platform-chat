import unittest

import desktop_app
from src import i18n


class _Widget:
    def __init__(self):
        self.text = ""
        self.properties = {}

    def setText(self, text):
        self.text = text

    def setProperty(self, name, value):
        self.properties[name] = value

    def property(self, name):
        return self.properties.get(name)


class _GroupBox:
    def __init__(self):
        self.title = ""
        self.properties = {}

    def setTitle(self, title):
        self.title = title

    def setProperty(self, name, value):
        self.properties[name] = value

    def property(self, name):
        return self.properties.get(name)


class DesktopLanguageTests(unittest.TestCase):
    def test_armed_recording_starts_on_offline_to_live_transition(self):
        self.assertEqual(
            desktop_app._recording_status_action(False, True, True),
            "start",
        )

    def test_armed_recording_starts_when_first_status_is_live(self):
        self.assertEqual(
            desktop_app._recording_status_action(None, True, True),
            "start",
        )

    def test_unarmed_recording_does_not_start_when_room_goes_live(self):
        self.assertIsNone(
            desktop_app._recording_status_action(False, True, False)
        )

    def test_recording_stops_when_room_goes_offline_without_disarming(self):
        self.assertEqual(
            desktop_app._recording_status_action(True, False, True),
            "stop",
        )

    def test_ongoing_live_status_does_not_restart_recording(self):
        self.assertIsNone(
            desktop_app._recording_status_action(True, True, True)
        )

    def test_localized_widget_retains_english_source_for_language_switch(self):
        widget = _Widget()
        translator = desktop_app._DesktopI18n(i18n)

        desktop_app._set_desktop_widget_text(widget, "Monitor", "zh", translator)
        self.assertEqual(widget.text, "监控")
        self.assertEqual(widget.property("_desktop_source_text"), "Monitor")

        source = widget.property("_desktop_source_text")
        desktop_app._set_desktop_widget_text(widget, source, "en", translator)
        self.assertEqual(widget.text, "Monitor")

    def test_localized_group_box_uses_title_setter(self):
        group = _GroupBox()
        translator = desktop_app._DesktopI18n(i18n)

        desktop_app._set_desktop_widget_text(group, "Live recording", "zh", translator)

        self.assertEqual(group.title, "直播录制")
        self.assertEqual(group.property("_desktop_source_text"), "Live recording")

    def test_reading_tooltip_formats_message_without_translate_argument_collision(self):
        translator = desktop_app._DesktopI18n(i18n)

        tooltip = translator.translate(
            "Username: {name}\nMessage: {message}",
            "zh",
            name="用户名读音",
            message="消息读音",
        )

        self.assertEqual(tooltip, "用户名：用户名读音\n消息：消息读音")

    def test_bilibili_gift_price_descriptors_follow_interface_language(self):
        translator = desktop_app._DesktopI18n(i18n)
        gift_text = "🎁 棉花糖 ×1 (¥15 via 心动盲盒, worth ¥9)"

        self.assertEqual(
            desktop_app._localize_bilibili_gift_text(
                gift_text, "zh", translator
            ),
            "🎁 棉花糖 ×1 (¥15 来自 心动盲盒, 价值 ¥9)",
        )
        self.assertEqual(
            desktop_app._localize_bilibili_gift_text(
                gift_text, "ja", translator
            ),
            "🎁 棉花糖 ×1 (¥15 経由 心动盲盒、相当額 ¥9)",
        )

    def test_message_popup_actions_follow_interface_language(self):
        translator = desktop_app._DesktopI18n(i18n)

        self.assertEqual(translator.translate("Read", "zh"), "朗读")
        self.assertEqual(translator.translate("Thank", "zh"), "感谢")
        self.assertEqual(translator.translate("Copy", "zh"), "复制")
        self.assertEqual(translator.translate("Read", "ja"), "読み上げ")
        self.assertEqual(translator.translate("Thank", "ja"), "お礼する")
        self.assertEqual(translator.translate("Copy", "ja"), "コピー")


if __name__ == "__main__":
    unittest.main()
