import queue
import threading
import unittest
from unittest.mock import patch

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
