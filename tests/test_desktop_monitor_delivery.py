import queue
import threading
import time
import unittest
from unittest.mock import Mock, patch

import desktop_app


class _Listener:
    def __init__(self, room_id):
        self.room_id = room_id
        self.running = True
        self.connected = True
        self.connected_uid = 0
        self.online_count = None
        self.online = None
        self.error = ""
        self.pending = queue.Queue()

    def pop_messages(self):
        messages = []
        while True:
            try:
                messages.append(self.pending.get_nowait())
            except queue.Empty:
                return messages

    def start(self):
        self.running = True
        return True

    def stop(self):
        self.running = False


@unittest.skipIf(desktop_app.QtCore is None, "PySide6 is not installed")
class DesktopMonitorDeliveryTests(unittest.TestCase):
    def test_status_interval_is_15_seconds_between_request_starts(self):
        worker = desktop_app._MonitorWorker({}, [])
        polls = {}
        fetch = Mock(return_value={"live": True})
        with patch("src.background_poll.time.monotonic", return_value=100) as clock:
            ready, _ = worker._poll_network(polls, "room", "key", 15, fetch, {})
            self.assertFalse(ready)
            polls["room"]._future.result(timeout=2)
            clock.return_value = 102
            ready, info = worker._poll_network(polls, "room", "key", 15, fetch, {})
            self.assertTrue(ready)
            self.assertTrue(info["live"])
            clock.return_value = 114.99
            worker._poll_network(polls, "room", "key", 15, fetch, {})
            self.assertEqual(fetch.call_count, 1)
            clock.return_value = 115
            worker._poll_network(polls, "room", "key", 15, fetch, {})
            polls["room"]._future.result(timeout=2)
            self.assertEqual(fetch.call_count, 2)

    def test_youtube_status_switches_ended_video_to_channel_without_mutating_state(self):
        state = {
            "video_id": "old", "chat_id": "old-chat", "page_token": "token",
            "backlog_loaded": True, "mode": "video", "fallback_channel": "",
        }
        status = {"live": True, "room_name": "Channel"}
        with (
            patch("src.youtube.get_video_live_status", return_value={
                "ended": True, "channel_id": "UC" + "a" * 22,
            }),
            patch("src.youtube_web.find_live_video", return_value={
                "live": True, "video_id": "new", "title": "New stream",
            }) as find,
            patch("src.youtube.resolve_live_chat_id") as resolve,
        ):
            updated_state, updated_status = desktop_app._MonitorWorker._fetch_youtube_status(
                state, status, "old", ""
            )
        self.assertEqual(updated_state["video_id"], "new")
        self.assertEqual(updated_state["mode"], "channel")
        self.assertEqual(updated_state["chat_id"], "")
        self.assertEqual(updated_state["page_token"], "")
        self.assertFalse(updated_state["backlog_loaded"])
        self.assertTrue(updated_status["live"])
        self.assertEqual(updated_status["title"], "New stream")
        self.assertEqual(state["video_id"], "old")
        self.assertEqual(state["page_token"], "token")
        self.assertEqual(status, {"live": True, "room_name": "Channel"})
        find.assert_called_once()
        resolve.assert_not_called()

    def test_room_status_and_live_detection_do_not_wait_for_other_rooms(self):
        from src import config

        targets = [
            {"id": "bilibili:123", "platform": "bilibili", "target": "123"},
            {"id": "missevan:456", "platform": "missevan", "target": "456"},
            {"id": "youtube:video", "platform": "youtube", "target": "abcdefghijk"},
        ]
        worker = desktop_app._MonitorWorker({}, targets)
        blocked = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        snapshots = queue.Queue()
        errors = queue.Queue()
        calls = []
        worker.statuses.connect(
            snapshots.put, desktop_app.QtCore.Qt.ConnectionType.DirectConnection
        )
        worker.failed.connect(
            errors.put, desktop_app.QtCore.Qt.ConnectionType.DirectConnection
        )

        def slow_status(_):
            calls.append(time.monotonic())
            blocked.set()
            try:
                if not release.wait(5):
                    raise TimeoutError("Test did not release status request")
                return {"live_status": 1}
            finally:
                finished.set()

        with (
            patch.object(config, "ROOM_STATUS_POLL_INTERVAL", 1),
            patch("src.bilibili.get_room_info", side_effect=slow_status),
            patch("src.missevan.get_room_info", return_value={"live": True}),
            patch("src.youtube.get_video_live_status", return_value={"broadcast": "live"}),
            patch("src.youtube.resolve_live_chat_id", return_value=("", "")),
            patch.object(worker, "_sync_room_listener", return_value=None),
        ):
            worker.start()
            try:
                self.assertTrue(blocked.wait(2))
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    snapshot = snapshots.get(timeout=1.5)
                    if all(
                        snapshot.get(target["id"], {}).get("live")
                        for target in targets[1:]
                    ):
                        break
                else:
                    self.fail("Healthy rooms did not report live promptly")
                self.assertFalse(release.is_set())
                self.assertFalse(snapshot["bilibili:123"]["live"])
                # Even after its interval expires, the blocked room stays single-flight.
                time.sleep(1.1)
                self.assertEqual(len(calls), 1)
                self.assertTrue(errors.empty(), list(errors.queue))
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
                worker.stop()
        self.assertFalse(worker.isRunning())

    def test_youtube_chat_request_does_not_block_room_status(self):
        from src import config

        worker = desktop_app._MonitorWorker({}, [
            {"id": "youtube:video", "platform": "youtube", "target": "abcdefghijk"},
            {"id": "missevan:456", "platform": "missevan", "target": "456"},
        ])
        blocked = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        snapshots = queue.Queue()
        room_live = threading.Event()
        worker.statuses.connect(
            snapshots.put, desktop_app.QtCore.Qt.ConnectionType.DirectConnection
        )

        def slow_chat(*_):
            blocked.set()
            try:
                if not release.wait(5):
                    raise TimeoutError("Test did not release chat request")
                return [], "", 0
            finally:
                finished.set()

        with (
            patch.object(config, "ROOM_STATUS_POLL_INTERVAL", 0.1),
            patch("src.youtube.get_video_live_status", return_value={"broadcast": "live"}),
            patch("src.youtube.resolve_live_chat_id", return_value=("chat", "")),
            patch("src.youtube.get_chat_messages", side_effect=slow_chat),
            patch("src.missevan.get_room_info", side_effect=lambda _: {"live": room_live.is_set()}),
            patch.object(worker, "_sync_room_listener", return_value=None),
        ):
            worker.start()
            try:
                self.assertTrue(blocked.wait(3))
                room_live.set()
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    snapshot = snapshots.get(timeout=1.5)
                    if snapshot.get("missevan:456", {}).get("live"):
                        break
                else:
                    self.fail("Room status waited for YouTube chat")
                self.assertFalse(release.is_set())
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
                worker.stop()

    def test_chat_keeps_arriving_while_room_status_is_blocked(self):
        from src import bilibili, config

        targets = [
            {"id": "bilibili:123", "platform": "bilibili", "target": "123"},
            {"id": "missevan:456", "platform": "missevan", "target": "456"},
        ]
        worker = desktop_app._MonitorWorker({}, targets)
        listeners = {
            target["id"]: _Listener(target["target"]) for target in targets
        }
        worker._listeners["missevan:456"] = listeners["missevan:456"]
        status_started = threading.Event()
        release_status = threading.Event()
        received = queue.Queue()
        errors = queue.Queue()
        worker.messages.connect(
            received.put, desktop_app.QtCore.Qt.ConnectionType.DirectConnection
        )
        worker.failed.connect(
            errors.put, desktop_app.QtCore.Qt.ConnectionType.DirectConnection
        )

        def blocked_status(room_id):
            status_started.set()
            if not release_status.wait(5):
                raise TimeoutError("Test did not release room status")
            return {"live_status": 1}

        with (
            patch.object(config, "CHAT_POLL_INTERVAL", 1),
            patch.object(bilibili, "DanmakuListener", return_value=listeners["bilibili:123"]),
            patch.object(bilibili, "get_room_info", side_effect=blocked_status),
            patch("src.missevan.get_room_info", return_value={"live": True}),
        ):
            worker.start()
            try:
                self.assertTrue(status_started.wait(2))
                for sequence in range(2):
                    for monitor_id, listener in listeners.items():
                        listener.pending.put({"id": f"{monitor_id}:{sequence}"})
                    delivered = []
                    while len(delivered) < 2:
                        delivered.extend(received.get(timeout=1.5))
                    self.assertEqual(
                        {message["_monitor_id"] for message in delivered},
                        set(listeners),
                    )
                    self.assertEqual(
                        {message["room_id"] for message in delivered},
                        {"123", "456"},
                    )
                    self.assertFalse(release_status.is_set())
                self.assertTrue(errors.empty(), list(errors.queue))
            finally:
                release_status.set()
                worker.stop()
        self.assertFalse(worker.isRunning())
        self.assertTrue(worker._chat_delivery_stop.is_set())
        self.assertTrue(all(not listener.running for listener in listeners.values()))
        self.assertTrue(received.empty())

    def test_removed_or_retargeted_rooms_are_not_delivered(self):
        worker = desktop_app._MonitorWorker({}, [
            {"id": "bilibili:123", "platform": "bilibili", "target": "999"},
        ])
        for monitor_id, room_id in (("bilibili:123", "123"), ("missevan:456", "456")):
            listener = _Listener(room_id)
            listener.pending.put({"id": monitor_id})
            worker._listeners[monitor_id] = listener
        delivered = queue.Queue()
        worker.messages.connect(
            delivered.put, desktop_app.QtCore.Qt.ConnectionType.DirectConnection
        )
        with patch.object(
            worker._chat_delivery_stop,
            "wait",
            side_effect=lambda _: worker._chat_delivery_stop.set(),
        ):
            worker._deliver_room_messages(0.05)
        self.assertTrue(delivered.empty())
        self.assertTrue(all(
            not listener.pending.empty()
            for listener in worker._listeners.values()
        ))

    def test_delivery_error_is_reported_without_blocking_other_rooms(self):
        targets = [
            {"id": "bilibili:123", "platform": "bilibili", "target": "123"},
            {"id": "missevan:456", "platform": "missevan", "target": "456"},
        ]
        worker = desktop_app._MonitorWorker({}, targets)
        broken = _Listener("123")
        healthy = _Listener("456")
        healthy.pending.put({"id": "healthy"})
        worker._listeners.update({
            "bilibili:123": broken,
            "missevan:456": healthy,
        })
        received = queue.Queue()
        errors = queue.Queue()
        worker.messages.connect(
            received.put, desktop_app.QtCore.Qt.ConnectionType.DirectConnection
        )
        worker.failed.connect(
            errors.put, desktop_app.QtCore.Qt.ConnectionType.DirectConnection
        )
        with (
            patch.object(broken, "pop_messages", side_effect=ValueError("broken")),
            patch.object(
                worker._chat_delivery_stop,
                "wait",
                side_effect=lambda _: worker._chat_delivery_stop.set(),
            ),
        ):
            worker._deliver_room_messages(0.05)
        self.assertIn("bilibili (123) chat delivery error: ValueError: broken", errors.get_nowait())
        self.assertEqual(received.get_nowait()[0]["id"], "healthy")


if __name__ == "__main__":
    unittest.main()
