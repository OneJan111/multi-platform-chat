import unittest
import threading
from unittest.mock import Mock, patch

from src.server_chat_history import ServerChatHistory, ServerChatPoller


class ServerChatHistoryTests(unittest.TestCase):
    def test_retains_all_messages_and_separates_chat_from_gifts(self):
        history = ServerChatHistory()
        for index in range(75):
            history.append({"id": str(index), "text": f"chat {index}"}, is_gift=False)
        history.append(
            {"id": "gift-1", "currency": "USD", "value": "4.5"},
            is_gift=True,
        )

        self.assertEqual(len(history.chat()), 75)
        self.assertEqual(len(history.gifts()), 1)
        self.assertEqual(history.profit_totals(), {"USD": 4.5})

    def test_duplicate_message_ids_do_not_duplicate_messages_or_totals(self):
        history = ServerChatHistory()
        gift = {"id": "42", "platform": "youtube", "currency": "USD", "value": "5"}

        self.assertTrue(history.append(gift, is_gift=True))
        self.assertFalse(history.append(gift, is_gift=True))

        self.assertEqual(len(history.gifts()), 1)
        self.assertEqual(history.profit_totals(), {"USD": 5.0})

    def test_background_poller_runs_without_a_browser_session(self):
        polled = threading.Event()
        with patch.object(ServerChatPoller, "poll_once", side_effect=polled.set):
            poller = ServerChatPoller(ServerChatHistory(), {})
            try:
                self.assertTrue(polled.wait(timeout=2))
            finally:
                poller.stop()

    def test_status_polling_stops_after_live_but_chat_polling_continues(self):
        poller = object.__new__(ServerChatPoller)
        poller._history = ServerChatHistory()
        poller._status_polling_paused = threading.Event()
        poller._last_status = 0.0
        poller._chat_id = "chat-id"
        poller._video_id = "video-id"
        poller._page_token = ""
        poller._youtube_backlog_loaded = True
        poller._bili_listener = None
        poller._me_listener = None
        poller._listener_lock = threading.Lock()
        poller._refresh_youtube = Mock(return_value=True)
        poller._refresh_room_status = Mock(return_value=False)

        with patch("src.server_chat_history.yt.get_chat_messages", return_value=([], "next", 5000)) as chat_poll:
            poller.poll_once()
            poller.poll_once()

        self.assertTrue(poller.status_polling_paused)
        self.assertEqual(poller._refresh_youtube.call_count, 1)
        self.assertEqual(poller._refresh_room_status.call_count, 1)
        self.assertEqual(chat_poll.call_count, 2)


if __name__ == "__main__":
    unittest.main()
