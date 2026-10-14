import unittest
from unittest.mock import Mock, patch

from src import missevan
from src.missevan import MissEvanListener


class MissEvanGiftTests(unittest.TestCase):
    def test_gift_message_records_quantity_and_total_diamond_value(self):
        listener = MissEvanListener.__new__(MissEvanListener)
        listener.room_id = "123"
        listener.messages = []
        listener._admins = set()
        listener._creator_id = 0

        listener._handle({
            "room_id": 123,
            "type": "gift",
            "event": "send",
            "gift": {"name": "花", "num": 3, "price": 2},
            "user": {"user_id": 5, "username": "viewer"},
            "oid": "gift-1",
        })

        self.assertEqual(len(listener.messages), 1)
        message = listener.messages[0]
        self.assertEqual(message["gift_count"], 3)
        self.assertEqual((message["currency"], message["value"]), ("💎", 6.0))


class MissEvanSendTests(unittest.TestCase):
    def test_native_preset_kaomoji_are_available(self):
        kaomoji = missevan.preset_kaomoji()

        self.assertEqual(len(kaomoji), 161)
        self.assertIn("(´・ω・`)", kaomoji)
        self.assertIn("(╯‵□′)╯︵┻━┻", kaomoji)

    def test_message_uuid_matches_official_web_client_sample(self):
        source = missevan.uuid.UUID("ce821e10-c7e8-11f1-9dea-ed6700000000")

        self.assertEqual(
            missevan._missevan_message_uuid(source),
            "ce821e10-c7e8-11f1-9dea-ed6710acb00d",
        )

    @patch("src.missevan._session")
    @patch("src.missevan.login_cookies", return_value={"token": "test"})
    def test_send_uses_web_json_payload_and_csrf_cookie(self, _login_cookies, session):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "code": 0,
            "info": {
                "ok": 1,
                "msg_id": "server-message-id",
                "user": {"user_id": 37622123},
            },
        }
        session.return_value.cookies.get.return_value = "test-csrf-token"
        session.return_value.post.return_value = response

        ok, error = missevan.send_message("123", "hello")

        self.assertTrue(ok)
        self.assertEqual(error, "server-message-id (UID 37622123)")
        session.return_value.get.assert_not_called()
        request = session.return_value.post.call_args.kwargs
        body = request["json"]
        self.assertEqual(body["room_id"], 123)
        self.assertIsInstance(body["room_id"], int)
        self.assertEqual(body["message"], "hello")
        self.assertEqual(body["csrf"], "test-csrf-token")
        message_id = missevan.uuid.UUID(body["uuid"])
        self.assertEqual(message_id.version, 1)
        self.assertEqual(message_id.variant, missevan.uuid.RFC_4122)
        self.assertEqual(
            missevan._missevan_message_uuid(
                missevan.uuid.UUID(bytes=message_id.bytes[:12] + b"\x00" * 4)
            ),
            body["uuid"],
        )
        self.assertNotIn("data", request)
        self.assertEqual(request["headers"]["Content-Type"], "application/json; charset=UTF-8")
        self.assertEqual(request["headers"]["X-Requested-With"], "XMLHttpRequest")
        self.assertEqual(request["headers"]["Accept"], "application/json, text/plain, */*")

    @patch("src.missevan._session")
    @patch("src.missevan.login_cookies", return_value={"token": "test"})
    def test_send_returns_api_error(self, _login_cookies, session):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"code": 500150022, "info": "聊天内容含有违规信息"}
        session.return_value.cookies.get.return_value = "test-csrf-token"
        session.return_value.post.return_value = response

        ok, error = missevan.send_message("123", "blocked")

        self.assertFalse(ok)
        self.assertEqual(error, "聊天内容含有违规信息")

    @patch("src.missevan._session")
    @patch("src.missevan.login_cookies", return_value={"token": "test"})
    def test_send_does_not_accept_code_zero_without_info_ok(self, _login_cookies, session):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"code": 0, "info": {"ok": 0}}
        session.return_value.cookies.get.return_value = "test-csrf-token"
        session.return_value.post.return_value = response

        ok, error = missevan.send_message("123", "hello")

        self.assertFalse(ok)
        self.assertEqual(error, "HTTP 200")

    @patch("src.missevan._session")
    @patch("src.missevan.login_cookies", return_value={"token": "test"})
    def test_send_rejects_success_response_without_server_message_id(self, _login_cookies, session):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"code": 0, "info": {"ok": 1}}
        session.return_value.cookies.get.return_value = None
        session.return_value.post.return_value = response

        ok, error = missevan.send_message("123", "hello")

        self.assertFalse(ok)
        self.assertIn("without a message ID", error)

    @patch("src.missevan._session")
    @patch("src.missevan.login_cookies", return_value={"token": "test"})
    def test_send_accepts_api_success_without_querying_history(
        self, _login_cookies, session
    ):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"code": 0, "info": {"ok": 1, "msg_id": "server-message-id"}}
        session.return_value.cookies.get.return_value = "test-csrf-token"
        session.return_value.post.return_value = response

        ok, error = missevan.send_message("123", "hello")

        self.assertTrue(ok)
        self.assertEqual(error, "server-message-id")
        session.return_value.get.assert_not_called()

    @patch("src.missevan._session")
    @patch("src.missevan.login_cookies", return_value={"token": "test"})
    def test_get_sticker_tabs_uses_room_id_and_returns_tabs(self, _login_cookies, session):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "code": 0,
            "info": {"tabs": [{"package_id": 45770, "name": "Room stickers"}]},
        }
        session.return_value.get.return_value = response

        tabs, error = missevan.get_sticker_tabs("869215180")

        self.assertEqual(error, "")
        self.assertEqual(tabs, [{"package_id": 45770, "name": "Room stickers"}])
        self.assertEqual(
            session.return_value.get.call_args.kwargs["params"], {"room_id": 869215180}
        )

    @patch("src.missevan.requests.get")
    def test_room_info_returns_cover_url(self, get):
        response = Mock()
        response.json.return_value = {
            "code": 0,
            "info": {"room": {
                "room_id": 869215180,
                "cover_url": "https://static.maoercdn.com/fmcovers/room.jpg",
                "status": {},
                "statistics": {},
            }},
        }
        get.return_value = response

        info = missevan.get_room_info("869215180")

        self.assertEqual(info["cover"], "https://static.maoercdn.com/fmcovers/room.jpg")

    @patch("src.missevan._session")
    @patch("src.missevan.login_cookies", return_value={"token": "test"})
    def test_get_stickers_uses_room_and_package_ids(self, _login_cookies, session):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "code": 0,
            "info": {"stickers": [{"sticker_id": 222, "image_url": "https://static.maoercdn.com/s.png"}]},
        }
        session.return_value.get.return_value = response

        stickers, error = missevan.get_stickers("869215180", 45770)

        self.assertEqual(error, "")
        self.assertEqual(stickers[0]["sticker_id"], 222)
        self.assertEqual(
            session.return_value.get.call_args.kwargs["params"],
            {"room_id": 869215180, "package_id": 45770},
        )

    @patch("src.missevan._session")
    @patch("src.missevan.login_cookies", return_value={"token": "test"})
    def test_send_sticker_uses_confirmed_json_payload(self, _login_cookies, session):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"code": 0, "info": {"ok": 1}}
        session.return_value.post.return_value = response

        ok, error = missevan.send_sticker("869215180", 45770, 222)

        self.assertTrue(ok)
        self.assertEqual(error, "")
        request = session.return_value.post.call_args.kwargs
        self.assertEqual(
            request["json"],
            {"room_id": 869215180, "sticker_id": 222, "package_id": 45770},
        )
        self.assertEqual(request["headers"]["Content-Type"], "application/json; charset=UTF-8")

    def test_incoming_room_sticker_becomes_safe_chat_image(self):
        listener = MissEvanListener.__new__(MissEvanListener)
        listener.room_id = "869215180"
        listener.messages = []
        listener._seen = set()
        listener._admins = set()
        listener._creator_id = 0

        listener._handle({
            "room_id": 869215180,
            "type": "message",
            "event": "sticker",
            "msg_id": "sticker-message",
            "message": "",
            "sticker": {"image_url": "https://static.maoercdn.com/sticker.png"},
            "user": {"user_id": 5, "username": "viewer"},
        })

        self.assertEqual(len(listener.messages), 1)
        self.assertEqual(
            listener.messages[0]["sticker_url"], "https://static.maoercdn.com/sticker.png"
        )

    def test_incoming_sticker_rejects_untrusted_image_url(self):
        listener = MissEvanListener.__new__(MissEvanListener)
        listener.room_id = "123"
        listener.messages = []
        listener._seen = set()
        listener._admins = set()
        listener._creator_id = 0

        listener._handle({
            "room_id": 123,
            "type": "message",
            "event": "new",
            "msg_id": "bad-sticker",
            "message": "",
            "sticker": {"image_url": "https://evil.example/sticker.png"},
            "user": {"user_id": 5, "username": "viewer"},
        })

        self.assertNotIn("sticker_url", listener.messages[0])


if __name__ == "__main__":
    unittest.main()
