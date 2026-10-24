import unittest

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


if __name__ == "__main__":
    unittest.main()
