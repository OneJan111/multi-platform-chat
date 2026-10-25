import unittest
from types import SimpleNamespace

import desktop_app
from desktop_app import _live_notification_details


class DesktopLiveNotificationTests(unittest.TestCase):
    def test_youtube_notification_has_live_link_and_safe_thumbnail(self):
        details = _live_notification_details(
            {
                "platform": "youtube",
                "target": "https://www.youtube.com/@channel",
            },
            {
                "room_name": "Channel",
                "title": "Tonight's stream",
                "thumbnail": "https://i.ytimg.com/vi/liveid/hqdefault.jpg",
            },
            video_id="liveid",
        )

        self.assertEqual(details["channel"], "Channel")
        self.assertEqual(details["platform"], "YouTube")
        self.assertEqual(
            details["url"], "https://www.youtube.com/watch?v=liveid"
        )
        self.assertEqual(
            details["thumbnail"],
            "https://i.ytimg.com/vi/liveid/hqdefault.jpg",
        )
        self.assertEqual(details["detail"], "Tonight's stream")

    def test_bilibili_and_missevan_use_their_room_urls(self):
        bilibili = _live_notification_details(
            {"platform": "bilibili", "target": "12345"},
            {"room_name": "Bili host", "title": "Live title", "cover": "https://i0.hdslb.com/cover.jpg"},
        )
        missevan = _live_notification_details(
            {"platform": "missevan", "target": "https://fm.missevan.com/live/67890"},
            {"room_name": "Me host", "title": "Audio live"},
        )

        self.assertEqual(bilibili["url"], "https://live.bilibili.com/12345")
        self.assertEqual(bilibili["thumbnail"], "https://i0.hdslb.com/cover.jpg")
        self.assertEqual(missevan["url"], "https://fm.missevan.com/live/67890")
        self.assertEqual(missevan["thumbnail"], "")

    def test_untrusted_preview_image_is_omitted(self):
        details = _live_notification_details(
            {"platform": "youtube", "target": "abcdefghijk"},
            {"title": "Live", "thumbnail": "https://example.com/image.jpg"},
        )

        self.assertEqual(details["thumbnail"], "")
        self.assertEqual(
            details["url"], "https://www.youtube.com/watch?v=abcdefghijk"
        )

    def test_youtube_channel_link_is_preserved_when_video_id_is_unavailable(self):
        details = _live_notification_details(
            {
                "platform": "youtube",
                "target": "https://www.youtube.com/@channel",
            },
            {"room_name": "Channel"},
        )

        self.assertEqual(details["url"], "https://www.youtube.com/@channel")

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_notification_height_fits_wrapped_text_and_preview(self):
        app, window = self._notification_window()
        try:
            desktop_app._DesktopWindow._notify_live_stream(
                window,
                {"platform": "bilibili", "target": "12345"},
                {
                    "room_name": "A channel with a long name " * 4,
                    "title": "A long stream title that wraps onto multiple lines " * 4,
                },
            )
            app.processEvents()
            notification = window._live_notifications[0]
            title = ("A long stream title that wraps onto multiple lines " * 4).strip()
            title_label = next(
                label for label in notification.findChildren(
                    desktop_app._ElidedLabel
                )
                if label.toolTip() == title
            )
            self.assertFalse(title_label.wordWrap())
            self.assertEqual(title_label.toolTip(), title)
            self.assertNotEqual(title_label.text(), title)
            layout = notification.layout()
            self.assertGreaterEqual(
                notification.height(),
                layout.totalHeightForWidth(notification.width()),
            )
            original_height = notification.height()
            image_label = next(
                label for label in notification.findChildren(
                    desktop_app.QtWidgets.QLabel
                )
                if label.size() == desktop_app.QtCore.QSize(346, 170)
            )
            image = desktop_app.QtGui.QImage(
                346, 170, desktop_app.QtGui.QImage.Format.Format_RGB32
            )
            image.fill(desktop_app.QtCore.Qt.GlobalColor.blue)
            data = desktop_app.QtCore.QByteArray()
            buffer = desktop_app.QtCore.QBuffer(data)
            buffer.open(desktop_app.QtCore.QIODevice.OpenModeFlag.WriteOnly)
            self.assertTrue(image.save(buffer, "PNG"))
            desktop_app._DesktopWindow._set_live_notification_image(
                window, notification, image_label, bytes(data)
            )
            app.processEvents()
            self.assertTrue(image_label.isVisible())
            self.assertGreater(notification.height(), original_height)
            self.assertGreaterEqual(
                notification.height(),
                layout.totalHeightForWidth(notification.width()),
            )
        finally:
            for notification in list(window._live_notifications):
                window._close_live_notification(notification)

    def _notification_window(self):
        app = desktop_app.QtWidgets.QApplication.instance()
        if app is None:
            app = desktop_app.QtWidgets.QApplication([])
        window = SimpleNamespace(
            _live_notifications=[],
            i18n=SimpleNamespace(
                translate=lambda text, language, **kwargs: text.format(**kwargs)
            ),
            _ui_language="en",
            style=app.style,
            screen=lambda: None,
        )
        window._position_live_notifications = lambda: (
            desktop_app._DesktopWindow._position_live_notifications(window)
        )
        window._close_live_notification = lambda notification: (
            desktop_app._DesktopWindow._close_live_notification(
                window, notification
            )
        )
        return app, window

    @unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
    def test_multiple_live_notifications_remain_visible_together(self):
        app, window = self._notification_window()
        targets = [
            {
                "platform": "youtube",
                "target": "https://www.youtube.com/@channel-one",
            },
            {
                "platform": "youtube",
                "target": "https://www.youtube.com/@channel-two",
            },
        ]
        try:
            for target in targets:
                desktop_app._DesktopWindow._notify_live_stream(
                    window, target, {"room_name": target["target"]}
                )
            app.processEvents()

            self.assertEqual(len(window._live_notifications), 2)
            self.assertTrue(
                all(item.isVisible() for item in window._live_notifications)
            )
            self.assertNotEqual(
                window._live_notifications[0].pos().y(),
                window._live_notifications[1].pos().y(),
            )
        finally:
            for notification in list(window._live_notifications):
                desktop_app._DesktopWindow._close_live_notification(
                    window, notification
                )


if __name__ == "__main__":
    unittest.main()
