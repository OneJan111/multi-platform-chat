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
                "widget": Mock(),
                "unload_stream": Mock(),
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
                "widget": Mock(), "title": Mock(), "stream_title": Mock(),
                "detail": Mock(),
                "unload_stream": Mock(),
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
        statuses = {monitor_id: {
            "live": True,
            "parent_area_name": "手游",
            "area_name": "原神",
        }}

        desktop_app._DesktopWindow._update_statuses(window, statuses)
        desktop_app._DesktopWindow._update_statuses(window, statuses)

        window._begin_transcription.assert_called_once_with(target)
        for key in ("widget", "title", "stream_title", "detail"):
            window._monitor_cards[monitor_id][key].setToolTip.assert_called_with(
                "ID 123\nRoom audience: waiting for live data\nZone: 手游 / 原神"
            )
        desktop_app._DesktopWindow._update_statuses(
            window, {monitor_id: {"live": False}}
        )
        window._transcriber.stop.assert_called_once_with()
        self.assertEqual(window._transcription_armed_id, monitor_id)
        self.assertEqual(window._viewer_samples, [])

    def test_missevan_room_statistics_are_shown_in_monitor_tooltip(self):
        monitor_id = "missevan:869215180"
        card = {
            "widget": Mock(),
            "title": Mock(),
            "stream_title": Mock(),
            "detail": Mock(),
            "connection": Mock(),
            "unload_stream": Mock(),
        }
        window = SimpleNamespace(
            _combined_monitor_ids={},
            _monitor_cards={monitor_id: card},
            _monitor_targets=[{
                "id": monitor_id,
                "platform": "missevan",
                "target": "869215180",
                "enabled": True,
            }],
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

        desktop_app._DesktopWindow._update_statuses(window, {
            monitor_id: {
                "live": True,
                "room_name": "Ya",
                "viewers": 0,
                "attention_count": 5128,
                "vip": 21,
                "score": 2574,
                "revenue": 34195,
            },
        })

        expected_tooltip = (
            "ID 869215180 · 0 viewers\n"
            "Attention count: 5128\n"
            "VIP: 21\n"
            "Score / popularity: 2574\n"
            "Revenue: 34195"
        )
        for key in ("widget", "title", "stream_title", "detail"):
            card[key].setToolTip.assert_called_once_with(expected_tooltip)

    def test_bilibili_actual_audience_and_guard_count_are_in_monitor_tooltip(self):
        monitor_id = "bilibili:123"
        card = {
            "widget": Mock(),
            "title": Mock(),
            "stream_title": Mock(),
            "detail": Mock(),
            "connection": Mock(),
            "unload_stream": Mock(),
        }
        window = SimpleNamespace(
            _combined_monitor_ids={},
            _monitor_cards={monitor_id: card},
            _monitor_targets=[{
                "id": monitor_id,
                "platform": "bilibili",
                "target": "123",
                "enabled": True,
            }],
            _room_names={},
            _room_titles={},
            _live_states={monitor_id: True},
            _transcription_armed_id=None,
            _record_enabled_ids=set(),
            _recorders={},
            _worker=None,
            _viewer_samples=[],
            _bilibili_gift_revenue={monitor_id: 12.5},
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

        desktop_app._DesktopWindow._update_statuses(window, {
            monitor_id: {
                "live": True,
                "viewers": 3395,
                "room_audience": 3395,
                "guard_count": 205,
                "popularity": 146417,
                "connection": "Connected",
            },
        })

        expected_tooltip = (
            "ID 123 · 3395 room audience\n"
            "Room audience: 3395\n"
            "Great Fleet: 205\n"
            "Popularity: 146417\n"
            "Captured gift revenue (session): ¥12.5"
        )
        for key in ("widget", "title", "stream_title", "detail"):
            card[key].setToolTip.assert_called_once_with(expected_tooltip)
        self.assertIn("3395 room audience", card["detail"].setFullText.call_args.args[0])

    def test_unload_stream_removes_stream_target_but_keeps_channel(self):
        channel_id = "youtube:channel"
        stream_id = "youtube:AbCdEf12345"
        channel = {
            "id": channel_id, "platform": "youtube",
            "target": "https://www.youtube.com/@channel", "enabled": True,
        }
        stream = {
            "id": stream_id, "platform": "youtube",
            "target": "https://www.youtube.com/watch?v=AbCdEf12345", "enabled": True,
        }
        worker = Mock()
        window = SimpleNamespace(
            _combined_monitor_ids={stream_id: (channel_id,)},
            _monitor_targets=[channel, stream],
            _recorders={stream_id: Mock()},
            _record_enabled_ids={channel_id, stream_id},
            _worker=worker,
            _stop_recording=Mock(),
            _save_record_enabled_ids=Mock(),
            _save_monitor_targets=Mock(),
            _refresh_monitor_cards=Mock(),
            _refresh_chat_room_selectors=Mock(),
            _refresh_transcription_rooms=Mock(),
            _refresh_feeds=Mock(),
        )

        desktop_app._DesktopWindow._unload_youtube_stream(window, channel_id)

        self.assertEqual(window._monitor_targets, [channel])
        self.assertEqual(window._record_enabled_ids, {channel_id})
        self.assertNotIn(stream_id, window._recorders)
        window._stop_recording.assert_called_once_with(stream_id)
        worker.update_targets.assert_called_once_with([channel])
        window._save_monitor_targets.assert_called_once_with()

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
