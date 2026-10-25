import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

import desktop_app


@unittest.skipIf(desktop_app.QtWidgets is None, "PySide6 is not installed")
class TranscriptionLifecycleTests(unittest.TestCase):
    def test_startup_notifies_once_for_room_already_live(self):
        monitor_id = "youtube:channel"
        target = {
            "id": monitor_id,
            "platform": "youtube",
            "target": "https://www.youtube.com/@channel",
            "enabled": True,
        }
        live_info = {
            "live": True,
            "room_name": "Channel",
            "title": "Already live",
        }
        window = SimpleNamespace(
            _monitor_cards={monitor_id: {
                "title": Mock(), "stream_title": Mock(), "detail": Mock(),
                "connection": Mock(),
            }},
            _monitor_targets=[target],
            _room_names={},
            _room_titles={},
            _live_states={},
            _transcription_armed_id=None,
            _record_enabled_ids=set(),
            _recorders={},
            _worker=None,
            _viewer_samples=[],
            _ui_language="en",
            _refresh_chat_room_selectors=Mock(),
            _refresh_transcription_rooms=Mock(),
            _refresh_archive_session_labels=Mock(),
            config=SimpleNamespace(ANALYTICS_ENABLED=False),
            notify_live_check=Mock(),
            _notify_live_stream=Mock(),
            live_status=Mock(),
            i18n=SimpleNamespace(
                translate=lambda text, language, **kwargs: text.format(**kwargs)
            ),
        )

        desktop_app._DesktopWindow._update_statuses(
            window, {monitor_id: live_info}
        )
        desktop_app._DesktopWindow._update_statuses(
            window, {monitor_id: live_info}
        )

        window._notify_live_stream.assert_called_once_with(
            target, live_info, ""
        )

    def test_live_status_starts_armed_room_only_on_transition(self):
        monitor_id = "bilibili:123"
        target = {"id": monitor_id, "platform": "bilibili",
                  "target": "123", "enabled": False}
        window = SimpleNamespace(
            _monitor_cards={monitor_id: {
                "title": Mock(), "stream_title": Mock(), "detail": Mock(),
                "connection": Mock(),
            }},
            _monitor_targets=[target], _room_names={}, _room_titles={},
            _live_states={monitor_id: False}, _transcription_armed_id=monitor_id,
            _begin_transcription=Mock(), _transcriber=Mock(),
            _record_enabled_ids=set(), _stop_recording=Mock(),
            notify_live_check=Mock(), _notify_live_stream=Mock(), live_status=Mock(),
            _viewer_samples=[], _ui_language="en",
            config=SimpleNamespace(ANALYTICS_ENABLED=False),
            i18n=SimpleNamespace(translate=lambda text, language, **kwargs: text),
        )
        statuses = {monitor_id: {"live": True}}

        desktop_app._DesktopWindow._update_statuses(window, statuses)
        desktop_app._DesktopWindow._update_statuses(window, statuses)

        window._begin_transcription.assert_called_once_with(target)
        desktop_app._DesktopWindow._update_statuses(
            window, {monitor_id: {"live": False}}
        )
        window._transcriber.stop.assert_called_once_with()
        self.assertEqual(window._transcription_armed_id, monitor_id)
        self.assertEqual(window._viewer_samples, [])

    def test_poll_keeps_previous_sessions_and_appends_new_text_after_clear(self):
        old_worker = Mock()
        old_worker.snapshot.return_value = {
            "segments": [{"original": "previous"}],
        }
        worker = Mock()
        worker.snapshot.return_value = {
            "status": "listening", "error": "",
            "segments": [{"original": "current"}],
        }
        with tempfile.TemporaryDirectory() as folder:
            window = SimpleNamespace(
                _transcriber=worker, _transcription_armed_id=None, _live_states={},
                _transcription_sessions=[
                    {
                        "worker": old_worker, "skip": 0,
                        "path": Path(folder) / "old.txt", "appended": 0,
                    },
                    {
                        "worker": worker, "skip": 0,
                        "path": Path(folder) / "current.txt", "appended": 0,
                    },
                ],
                _segments=[], transcription_output=Mock(), transcription_status=Mock(),
                _transcription_lrc_offsets={},
            )
            desktop_app._DesktopWindow._poll_transcription(window)
            self.assertEqual(
                [segment["original"] for segment in window._segments],
                ["previous", "current"],
            )
            desktop_app._DesktopWindow._clear_transcriptions(window)
            worker.snapshot.return_value["segments"].append({"original": "new"})
            desktop_app._DesktopWindow._poll_transcription(window)
            self.assertEqual(window._segments, [{"original": "new"}])

    def test_start_arms_offline_room_without_enabling_chat_saving(self):
        target = {"id": "bilibili:123", "platform": "bilibili",
                  "target": "123", "enabled": False}
        window = SimpleNamespace(
            transcribe_site=Mock(), transcribe_room=Mock(),
            _monitor_targets=[target], _live_states={},
            _stop_transcription=Mock(), _begin_transcription=Mock(),
            transcription_status=Mock(), _ui_language="en",
            _transcription_lrc_offsets={},
            i18n=SimpleNamespace(translate=lambda text, language: text),
        )
        window.transcribe_site.currentData.return_value = "bilibili"
        window.transcribe_room.currentData.return_value = "bilibili:123"

        with tempfile.TemporaryDirectory() as folder, patch.object(
            desktop_app.QtWidgets.QFileDialog,
            "getSaveFileName",
            return_value=(str(Path(folder) / "transcript"), "Text files (*.txt)"),
        ):
            desktop_app._DesktopWindow._start_transcription(window)

        self.assertEqual(window._transcription_armed_id, "bilibili:123")
        self.assertEqual(window._transcription_destination.suffix, ".txt")
        self.assertFalse(target["enabled"])
        window._begin_transcription.assert_not_called()

    def test_clear_skips_old_segments_without_stopping_worker(self):
        worker = Mock()
        worker.snapshot.return_value = {"segments": [{"original": "old"}]}
        window = SimpleNamespace(
            _transcription_sessions=[{"worker": worker, "skip": 0}],
            _segments=[{"original": "old"}], transcription_output=Mock(),
            _transcriber=worker,
        )

        desktop_app._DesktopWindow._clear_transcriptions(window)

        self.assertEqual(window._segments, [])
        self.assertEqual(window._transcription_sessions[0]["skip"], 1)
        worker.stop.assert_not_called()
        window.transcription_output.clear.assert_called_once_with()
        self.assertEqual(len(window._transcription_sessions), 1)

    def test_stop_disarms_waiting_and_stops_active_worker(self):
        window = SimpleNamespace(_transcription_armed_id="room", _transcriber=Mock())
        desktop_app._DesktopWindow._stop_transcription(window)
        self.assertIsNone(window._transcription_armed_id)
        window._transcriber.stop.assert_called_once_with()
