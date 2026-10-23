"""Native PySide6 desktop UI for the Streaming Dashboard.

Install PySide6 with ``python -m pip install PySide6``, then run:
    python desktop_app.py
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import html
import json
import logging
import math
import os
import re
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlencode

try:
    from PySide6 import QtCore, QtGui, QtWidgets, QtMultimedia
except ImportError:
    QtCore = QtGui = QtWidgets = QtMultimedia = None

_ROOT = Path(__file__).resolve().parent
_MAX_ARCHIVE_SESSIONS = 200
_MAX_SESSION_MESSAGES = 5000


_CHAT_LAYOUT_BREAKPOINT = 1000


def _chat_splitter_layout(width: int) -> tuple[str, tuple[str, str]]:
    if width < _CHAT_LAYOUT_BREAKPOINT:
        return "vertical", ("paid", "chat")
    return "horizontal", ("chat", "paid")


def _youtube_channel_video_id(info: dict) -> str:
    if info.get("live") or info.get("upcoming"):
        return str(info.get("video_id", ""))
    return ""


def _saved_splitter_sizes(settings, key: str, defaults: list[int]) -> list[int]:
    sizes = settings.value(key, [], type=list)
    if (
        not isinstance(sizes, list)
        or len(sizes) != len(defaults)
        or any(type(size) is not int or size <= 0 for size in sizes)
    ):
        return defaults
    return sizes


def _memory_log_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "StreamingDashboard" / "logs" / "memory.log"
    return Path.home() / ".streaming-dashboard" / "logs" / "memory.log"


def _memory_collection_metrics(window) -> dict[str, int]:
    image_bytes = sum(
        len(value[1])
        for value in getattr(window, "_chat_image_cache", {}).values()
        if isinstance(value, tuple)
        and len(value) > 1
        and isinstance(value[1], bytes)
    )
    audio_queue = getattr(window, "_audio_queue", [])
    audio_bytes = sum(
        len(item) for item in audio_queue if isinstance(item, (bytes, bytearray))
    )
    sessions = getattr(window, "_transcription_sessions", [])
    transcription_worker_segments = 0
    for session in sessions:
        worker_session = session.get("worker")
        if worker_session is None:
            continue
        segments = getattr(worker_session, "_segments", ())
        lock = getattr(worker_session, "_lock", None)
        if lock is None:
            transcription_worker_segments += len(segments)
        else:
            with lock:
                transcription_worker_segments += len(segments)
    worker = getattr(window, "_worker", None)
    recorders = getattr(window, "_recorders", {})
    return {
        "chat_messages": len(getattr(window, "_messages", [])),
        "paid_messages": len(getattr(window, "_paid", [])),
        "join_messages": len(getattr(window, "_joins", [])),
        "activity_entries": len(getattr(window, "_activity", [])),
        "hotspot_events": len(getattr(window, "_hotspot_events", [])),
        "chat_image_cache_entries": len(
            getattr(window, "_chat_image_cache", {})
        ),
        "chat_image_cache_bytes": image_bytes,
        "chat_images_pending": len(getattr(window, "_chat_images_pending", set())),
        "tts_queue_items": len(audio_queue),
        "tts_queue_bytes": audio_bytes,
        "transcription_sessions": len(sessions),
        "transcription_display_segments": len(
            getattr(window, "_segments", [])
        ),
        "transcription_worker_segments": transcription_worker_segments,
        "monitored_rooms": len(getattr(window, "_monitor_targets", [])),
        "chat_listener_count": len(getattr(worker, "_listeners", {})),
        "recording_count": sum(
            bool(getattr(recorder, "is_running", False))
            for recorder in recorders.values()
        ),
    }


def _memory_process_metrics(process, psutil_module) -> dict[str, int]:
    parent_rss = process.memory_info().rss
    children = process.children(recursive=True)
    child_rss = 0
    unreadable_children = 0
    for child in children:
        try:
            child_rss += child.memory_info().rss
        except psutil_module.Error:
            unreadable_children += 1
    return {
        "process_rss_bytes": parent_rss,
        "child_process_count": len(children),
        "child_process_rss_bytes": child_rss,
        "unreadable_child_processes": unreadable_children,
        "process_tree_rss_bytes": parent_rss + child_rss,
        "thread_count": process.num_threads(),
    }


def _archive_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "StreamingDashboard" / "chat_archive.json"
    return Path.home() / ".streaming-dashboard" / "chat_archive.json"


def _emote_cache_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "StreamingDashboard" / "emote_cache.json"
    return Path.home() / ".streaming-dashboard" / "emote_cache.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_key(message: dict[str, str]) -> str:
    return json.dumps(
        [
            message["timestamp"],
            message.get("platform", ""),
            message["author"],
            message["text"],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _message_matches_selected_chat_room(
    message: dict,
    selected_ids: dict[str, str],
    room_ids: set[str],
    visible_platforms: set[str] | None = None,
) -> bool:
    platform = str(message.get("platform", "")).lower()
    monitor_id = str(message.get("_monitor_id", ""))
    return bool(
        monitor_id
        and monitor_id in room_ids
        and selected_ids.get(platform) == monitor_id
        and (visible_platforms is None or platform in visible_platforms)
    )


def _chat_speech_is_current(
    message: dict,
    selected_ids: dict[str, str],
    room_ids: set[str],
    visible_platforms: set[str],
    queued_generation: int,
    current_generation: int,
) -> bool:
    return (
        queued_generation == current_generation
        and _message_matches_selected_chat_room(
            message, selected_ids, room_ids, visible_platforms
        )
    )


def _format_chat_timestamp(timestamp) -> str:
    try:
        return datetime.fromtimestamp(int(timestamp)).strftime("%H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            return parsed.astimezone().strftime("%H:%M:%S")
        except (TypeError, ValueError, OSError, OverflowError):
            return str(timestamp)


_DESKTOP_STRINGS: dict[str, tuple[str, str]] = {
    "Theme": ("主题", "テーマ"),
    "Light": ("浅色", "ライト"),
    "Dark": ("深色", "ダーク"),
    "Add translations to overlay": ("在叠加层中添加翻译", "オーバーレイに翻訳を追加"),
    "Record": ("录制", "録画"),
    "Bilibili recording": ("B站录制", "Bilibili 録画"),
    "Live recording": ("直播录制", "ライブ録画"),
    "Turn on Record on a YouTube, Bilibili, or MissEvan room card to record its live stream. "
    "YouTube and MissEvan recordings are MKV; Bilibili recordings are FLV. "
    "Recording stops when the room goes offline. FFmpeg is required.": (
        "在 YouTube、Bilibili 或 MissEvan 房间卡片上开启“录制”即可录制直播。"
        "YouTube 和 MissEvan 录制为 MKV，Bilibili 录制为 FLV；下播后自动停止。需要 FFmpeg。",
        "YouTube、Bilibili、または MissEvan のルームカードで「録画」をオンにするとライブを録画します。"
        "YouTube と MissEvan は MKV、Bilibili は FLV で保存され、配信終了時に録画も停止します。FFmpeg が必要です。",
    ),
    "Interface language": ("界面语言", "インターフェース言語"),
    "Clear all transcripts": ("清空全部转录文本", "文字起こしをすべて消去"),
    "Waiting for room to go live": ("等待房间开播", "配信開始を待機中"),
    "Choose transcript file": ("选择转录文件", "文字起こしファイルを選択"),
    " via ": (" 来自 ", " 経由 "),
    ", worth ¥": (", 价值 ¥", "、相当額 ¥"),
    ", list ¥": (", 原价 ¥", "、定価 ¥"),
    "Username: {name}\nMessage: {message}": (
        "用户名：{name}\n消息：{message}",
        "ユーザー名：{name}\nメッセージ：{message}",
    ),
    "Preferred Bilibili quality": ("Bilibili 首选画质", "Bilibili の優先画質"),
    "Save Bilibili danmaku, Super Chats and gifts to an XML file next to each video": (
        "将 Bilibili 弹幕、醒目留言和礼物保存到视频旁的 XML 文件",
        "Bilibili のコメント・Super Chat・ギフトを動画と同じ場所の XML ファイルに保存",
    ),
    "Browse…": ("浏览…", "参照…"),
    "Chat messages": ("聊天消息", "チャットメッセージ"),
    "Paid messages": ("付费消息", "有料メッセージ"),
    "Export DaVinci EDL": ("导出 DaVinci EDL", "DaVinci EDL をエクスポート"),
    "Export hotspots CSV": ("导出热点 CSV", "ホットスポット CSV をエクスポート"),
    "Open folder": ("打开文件夹", "フォルダーを開く"),
    "Optional custom overlay message": ("可选：叠加层自定义消息", "任意：オーバーレイのカスタムメッセージ"),
    "Preferred quality": ("首选画质", "優先画質"),
    "Remove selected allow pattern": ("删除所选允许规则", "選択した許可パターンを削除"),
    "Remove selected block pattern": ("删除所选屏蔽规则", "選択したブロックパターンを削除"),
    "Room to transcribe": ("要转录的直播间", "文字起こしするルーム"),
    " s window": (" 秒窗口", " 秒ウィンドウ"),
    "Save danmaku, Super Chats and gifts to an XML file next to each video": (
        "将弹幕、醒目留言和礼物保存为视频旁的 XML 文件",
        "コメント・スーパーチャット・ギフトを動画と同じ場所の XML ファイルに保存",
    ),
    "Save recordings to": ("录像保存位置", "録画の保存先"),
    "Show usernames": ("显示用户名", "ユーザー名を表示"),
    "Start server and copy Browser Source URL": (
        "启动服务器并复制浏览器源 URL", "サーバーを起動してブラウザソース URL をコピー"
    ),
    "Start the local overlay server for an OBS Browser Source.": (
        "启动本地叠加层服务器，用于 OBS 浏览器源。",
        "OBS ブラウザソース用のローカルオーバーレイサーバーを起動します。",
    ),
    "Starting monitor…": ("正在启动监控…", "モニターを起動中…"),
    "Translate transcription": ("翻译转录内容", "文字起こしを翻訳"),
    "Use the overlay URL in OBS as a Browser Source to show a transparent chat on stream.": (
        "在 OBS 中将叠加层 URL 添加为浏览器源，即可在直播画面上显示透明聊天。",
        "オーバーレイ URL を OBS のブラウザソースとして使うと、配信画面に透過チャットを表示できます。",
    ),
    "Select a room": ("选择直播间", "ルームを選択"),
    "Paste / import": ("粘贴 / 导入", "貼り付け / インポート"),
    "No room configured": ("未配置直播间", "ルーム未設定"),
    "Allow saving": ("允许保存", "保存を許可"),
    "Live chat is received either way. This controls whether messages from this room can be saved.": (
        "无论此项是否开启，都会实时接收弹幕。此项仅控制是否允许保存该直播间的弹幕。",
        "この設定に関係なくチャットはリアルタイムで受信されます。このルームのチャットを保存できるかどうかだけを設定します。",
    ),
    "Monitored {site} room shown in the overlay": (
        "叠加层显示的 {site} 监控直播间", "オーバーレイに表示する {site} のモニタールーム"
    ),
    "Last recording: {size}": ("上次录制：{size}", "前回の録画：{size}"),
    "Saved room files: {path}": ("已保存的直播间文件：{path}", "保存済みルームファイル：{path}"),
    "Select at least one monitored room for the overlay.": (
        "请为叠加层至少选择一个监控直播间。", "オーバーレイ用のモニタールームを 1 つ以上選択してください。"
    ),
    "Starting": ("正在开始", "開始中"),
    "Retrying": ("正在重试", "再試行中"),
    "Stream ended": ("直播流已结束", "ストリーム終了"),
    "Stopped": ("已停止", "停止"),
}


class _DesktopI18n:
    """`src.i18n` plus strings that only the desktop app uses."""

    def __init__(self, base):
        self._base = base
        self.UI_LANGUAGES = base.UI_LANGUAGES

    def __getattr__(self, name):
        return getattr(self._base, name)

    def translate(self, text: str, lang: str, **kwargs) -> str:
        index = {"zh": 0, "ja": 1}.get(lang)
        if index is not None and text in _DESKTOP_STRINGS:
            out = _DESKTOP_STRINGS[text][index]
            return out.format(**kwargs) if kwargs else out
        return self._base.translate(text, lang, **kwargs)


_OBS_SETUP_MD = """1. Open OBS → **Tools → WebSocket Server Settings**
2. Enable the WebSocket server
3. Set a password and note the port (default 4455)
4. Add to your `.env`:

   ```
   OBS_HOST=localhost
   OBS_PORT=4455
   OBS_PASSWORD=your_password
   ```
"""


def _obs_connection_message(error: tuple[str, str], host: str, port: int, translate) -> tuple[str, str]:
    """Describe why OBS isn't connected, matching the web dashboard's wording."""
    code, detail = error
    address = f"{host}:{port}"
    if code == "no_lib":
        return translate(
            "⚠️ OBS is not connected: obsws-python is not installed. Run `pip install obsws-python`."
        ), ""
    if code == "no_password":
        return translate("⚠️ OBS is not connected: OBS_PASSWORD is not set in .env."), ""
    if code == "auth":
        return translate(
            "⚠️ OBS at {addr} refused the login — check OBS_PASSWORD. ({detail})",
            addr=address,
            detail=detail,
        ), ""
    return translate(
        "⚠️ OBS is not connected: nothing answered at {addr}.", addr=address
    ), translate(
        "Is OBS running with its WebSocket server enabled? OBS_HOST is resolved on the computer "
        "running this dashboard — if that's a server, `localhost` means the server itself. Set "
        "OBS_HOST to the address of the PC running OBS, reachable from the server (same network, "
        "VPN such as Tailscale, or a port forward), and allow port {port} in that PC's firewall.",
        port=port,
    )


def _obs_chat_update_due(
    last: tuple[str, str] | None, last_at: float, source: str, text: str, now: float
) -> bool:
    """Skip identical OBS text pushes, but refresh them every 30 seconds."""
    return last != (source, text) or now - last_at >= 30


def _format_record_size(size: int) -> str:
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _format_record_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def _saved_session_room_label(session: dict) -> str:
    identity = session.get("channel_id") or session.get("room_id") or session.get(
        "session_id", ""
    )
    return str(session.get("room_name") or identity)


def _format_message_for_copy(message: dict) -> str:
    timestamp = _format_chat_timestamp(message.get("timestamp", ""))
    platform = str(message.get("platform", "")).upper()
    author = str(message.get("author", "?"))
    text = str(message.get("text", ""))
    line = f"{timestamp} [{platform}] {author}: {text}"
    translation = str(message.get("translation", "")).strip()
    if translation:
        line += f"\n  Translation: {translation}"
    return line


def _message_action_names(platform: str, paid: bool = False) -> tuple[str, ...]:
    actions = ["Block", "Read"]
    if paid:
        actions.append("Thank")
    if platform == "bilibili":
        actions.append("Mute")
    actions.append("Copy")
    return tuple(actions)


def _monitored_target_for_message(
    message: dict, monitor_targets: list[dict]
) -> dict | None:
    platform = str(message.get("platform", "")).lower()
    enabled_targets = [
        entry for entry in monitor_targets
        if entry.get("platform") == platform and entry.get("enabled")
    ]
    monitor_id = str(message.get("_monitor_id", ""))
    if monitor_id:
        return next(
            (entry for entry in enabled_targets if entry.get("id") == monitor_id),
            None,
        )
    return enabled_targets[0] if len(enabled_targets) == 1 else None


def _selected_monitor_target(
    platform: str, selected_id: str, monitor_targets: list[dict]
) -> str:
    selected = next(
        (
            entry for entry in monitor_targets
            if entry.get("platform") == platform
            and entry.get("id") == selected_id
        ),
        None,
    )
    if selected:
        return str(selected.get("target", ""))
    return next(
        (
            str(entry.get("target", ""))
            for entry in monitor_targets
            if entry.get("platform") == platform and entry.get("enabled")
        ),
        "",
    )


def _transcription_room_entries(platform: str, monitor_targets: list[dict]) -> list[dict]:
    return [
        entry for entry in monitor_targets
        if entry.get("platform") == platform
    ]


def _selected_transcription_room(
    platform: str, monitor_id: str, monitor_targets: list[dict]
) -> dict | None:
    return next(
        (
            entry for entry in _transcription_room_entries(platform, monitor_targets)
            if entry.get("id") == monitor_id
        ),
        None,
    )


def _format_transcription(segments: list[dict]) -> str:
    return "\n\n".join(
        f"[{item.get('time', '')}] {item.get('original', '')}"
        + (f"\n🌐 {item.get('translated')}" if item.get("translated") else "")
        for item in segments
    )


def _format_transcription_lrc(segments: list[dict]) -> str:
    lines = []
    for item in segments:
        original = " ".join(str(item.get("original", "")).splitlines()).strip()
        if not original:
            continue
        seconds = item.get("start_seconds")
        if (
            not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError(
                "LRC export requires audio-relative timestamps. Start a new transcription session."
            )
        centiseconds = round(seconds * 100)
        minutes, remainder = divmod(centiseconds, 6000)
        whole_seconds, fraction = divmod(remainder, 100)
        timestamp = f"[{minutes:02d}:{whole_seconds:02d}.{fraction:02d}]"
        lines.append(timestamp + original)
        translated = " ".join(str(item.get("translated", "")).splitlines()).strip()
        if translated:
            lines.append(timestamp + translated)
    return "\n".join(lines)


def _write_transcription(path: Path | str, text: str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def _append_transcription_segment(
    path: Path | str, segment: dict, lrc_offset: float = 0
) -> Path:
    destination = Path(path)
    if not str(segment.get("original", "")).strip():
        return destination
    is_lrc = destination.suffix.lower() == ".lrc"
    if is_lrc and lrc_offset:
        segment = dict(segment)
        segment["start_seconds"] = segment.get("start_seconds", 0) + lrc_offset
    text = (
        _format_transcription_lrc([segment])
        if is_lrc
        else _format_transcription([segment])
    )
    if not text:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    separator = "\n" if is_lrc else "\n\n"
    with destination.open("a", encoding="utf-8", newline="") as output:
        if destination.exists() and destination.stat().st_size > 0:
            output.write(separator)
        output.write(text)
    return destination


def _existing_lrc_offset(path: Path | str) -> float:
    source = Path(path)
    if not source.exists() or source.suffix.lower() != ".lrc":
        return 0
    contents = source.read_text(encoding="utf-8")
    timestamps = [
        int(minutes) * 60 + int(seconds) + int(centiseconds) / 100
        for minutes, seconds, centiseconds in re.findall(
            r"\[(\d+):(\d{2})\.(\d{2})\]", contents
        )
    ]
    return max(timestamps, default=-8) + 8


def _recording_status_action(previous_live: bool | None, live: bool, armed: bool) -> str | None:
    if live and previous_live is not True and armed:
        return "start"
    if not live and previous_live is True:
        return "stop"
    return None


def _plain_chat_html(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def _reading_tooltip_allowed(widget) -> bool:
    return widget.isVisible() and widget.window().isActiveWindow()


def _limit_messages_per_room(messages: list[dict], limit: int) -> list[dict]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    retained = []
    for message in reversed(messages):
        room = (
            str(message.get("platform", "")),
            str(
                message.get("_monitor_id")
                or message.get("room_id")
                or message.get("channel_id")
                or ""
            ),
        )
        if counts[room] < limit:
            retained.append(message)
            counts[room] += 1
    retained.reverse()
    return retained


def _retain_selected_room_messages(
    messages: list[dict], selected_ids: dict[str, str], room_ids: set[str], limit: int
) -> list[dict]:
    return _limit_messages_per_room(
        [
            message for message in messages
            if _message_matches_selected_chat_room(message, selected_ids, room_ids)
        ],
        limit,
    )


def _localize_bilibili_gift_text(text: str, language: str, i18n) -> str:
    for label in (" via ", ", worth ¥", ", list ¥"):
        text = text.replace(label, i18n.translate(label, language))
    return text


def _selected_feed_indices(messages: list[dict], selected_messages: list[dict]) -> list[int]:
    selected_ids = {
        message.get("_desktop_feed_id")
        for message in selected_messages
        if message.get("_desktop_feed_id") is not None
    }
    return [
        index
        for index, message in enumerate(messages)
        if message.get("_desktop_feed_id") in selected_ids
    ]


def _feed_scroll_click_state(paused: bool, paused_message_id, clicked_message_id) -> tuple[bool, str | None]:
    if paused and paused_message_id == clicked_message_id:
        return False, None
    return True, clicked_message_id


def _set_desktop_widget_text(widget, text: str, language: str, i18n) -> None:
    translated = i18n.translate(text, language)
    set_title = getattr(widget, "setTitle", None)
    if callable(set_title):
        set_title(translated)
    else:
        widget.setText(translated)
    widget.setProperty("_desktop_source_text", text)
    widget.setProperty("_desktop_source_text_rendered", translated)


def _selected_send_destinations(
    platforms: list[str], selected_ids: dict[str, str], monitor_targets: list[dict]
) -> list[dict]:
    destinations = []
    for platform in platforms:
        selected_id = selected_ids.get(platform, "")
        if not selected_id:
            continue
        target = next(
            (
                entry for entry in monitor_targets
                if entry.get("platform") == platform
                and entry.get("id") == selected_id
                and entry.get("enabled")
            ),
            None,
        )
        if target:
            destinations.append(target)
    return destinations


class DesktopChatArchive:
    """Store each room's rendered chat in a separate file."""

    def __init__(self, path: Path | None = None):
        self.path = path or _archive_path()
        self.sessions_path = self.path.parent / "chat_archive"
        self._lock = threading.Lock()

    @staticmethod
    def _validate_archive(archive: dict) -> dict:
        if (
            not isinstance(archive, dict)
            or archive.get("version") != 1
            or not isinstance(archive.get("sessions"), list)
        ):
            raise ValueError("The chat archive has an unsupported or invalid format.")
        for session in archive["sessions"]:
            if (
                not isinstance(session, dict)
                or not isinstance(session.get("session_id"), str)
                or not isinstance(session.get("started_at"), str)
                or not isinstance(session.get("updated_at"), str)
                or not isinstance(session.get("messages"), list)
                or len(session["messages"]) > _MAX_SESSION_MESSAGES
            ):
                raise ValueError("The chat archive contains an invalid session.")
            for message in session["messages"]:
                if not isinstance(message, dict) or any(
                    not isinstance(message.get(key), str)
                    for key in ("timestamp", "author", "text")
                ) or any(
                    not isinstance(message.get(key, ""), str)
                    for key in ("platform", "type", "translation")
                ):
                    raise ValueError("The chat archive contains an invalid message.")
            for key in ("platform", "room_id", "channel_id"):
                if not isinstance(session.get(key, ""), str):
                    raise ValueError("The chat archive contains an invalid room or channel ID.")
            if not isinstance(session.get("room_name", ""), str):
                raise ValueError("The chat archive contains an invalid room name.")
        return archive

    @classmethod
    def _read_path(cls, path: Path) -> dict:
        if not path.exists():
            return {"version": 1, "sessions": []}
        return cls._validate_archive(json.loads(path.read_text(encoding="utf-8")))

    def _session_path(self, session_id: str) -> Path:
        platform, separator, identity = session_id.partition(":")
        if not separator or not platform or not identity:
            raise ValueError("Invalid chat session ID.")
        platform = re.sub(r"[^A-Za-z0-9._-]+", "_", platform).strip("._-")
        safe_identity = re.sub(r"[^A-Za-z0-9._-]+", "_", identity).strip("._-")
        safe_identity = safe_identity[:80] or "room"
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
        return self.sessions_path / f"{platform}_{safe_identity}_{digest}.json"

    def _read(self) -> dict:
        archive = self._read_path(self.path)
        sessions = {
            session["session_id"]: session
            for session in archive["sessions"]
        }
        if self.sessions_path.exists():
            for path in sorted(self.sessions_path.glob("*.json")):
                separate_archive = self._read_path(path)
                if len(separate_archive["sessions"]) != 1:
                    raise ValueError(
                        f"Chat archive file {path.name} must contain exactly one room."
                    )
                separate_session = separate_archive["sessions"][0]
                session_id = separate_session["session_id"]
                previous = sessions.get(session_id)
                if previous is None:
                    sessions[session_id] = separate_session
                    continue
                merged_messages = {
                    _message_key(message): message
                    for message in previous["messages"]
                }
                for message in separate_session["messages"]:
                    merged_messages.setdefault(_message_key(message), message)
                separate_session["messages"] = list(merged_messages.values())[
                    -_MAX_SESSION_MESSAGES:
                ]
                sessions[session_id] = separate_session
        if len(sessions) > _MAX_ARCHIVE_SESSIONS:
            raise ValueError("The chat archive contains too many sessions.")
        return {"version": 1, "sessions": list(sessions.values())}

    def _write_path(self, path: Path, archive: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(archive, temporary, ensure_ascii=False, indent=2)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def _write_sessions(self, sessions: list[dict]) -> None:
        self.sessions_path.mkdir(parents=True, exist_ok=True)
        expected_paths = set()
        for session in sessions:
            session_path = self._session_path(session["session_id"])
            self._write_path(
                session_path,
                {"version": 1, "sessions": [session]},
            )
            expected_paths.add(session_path)
        for session_path in self.sessions_path.glob("*.json"):
            if session_path not in expected_paths:
                session_path.unlink()
        if self.path.exists():
            self.path.unlink()

    def load_archive(self) -> dict:
        try:
            with self._lock:
                archive = self._read()
                if self.path.exists():
                    self._write_sessions(archive["sessions"])
            return {"ok": True, "archive": archive, "path": str(self.path)}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"Could not load chat archive: {exc}"}

    def save_snapshot(
        self,
        session_id: str,
        messages: list[dict],
        *,
        platform: str = "",
        room_id: str = "",
        channel_id: str = "",
        room_name: str = "",
    ) -> dict:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 600:
            return {"ok": False, "error": "Invalid chat session ID."}
        if not isinstance(messages, list):
            return {"ok": False, "error": "Chat snapshot must be a list of messages."}
        if any(
            not isinstance(value, str) or len(value) > 500
            for value in (platform, room_id, channel_id, room_name)
        ):
            return {"ok": False, "error": "Invalid room or channel ID."}

        normalized = []
        for item in messages[-_MAX_SESSION_MESSAGES:]:
            if not isinstance(item, dict):
                return {"ok": False, "error": "Chat snapshot contains an invalid message."}
            record = {}
            for key in ("timestamp", "author", "text"):
                value = item.get(key, "")
                if not isinstance(value, str) or len(value) > 20000:
                    return {"ok": False, "error": f"Chat message has an invalid {key} field."}
                record[key] = value
            message_platform = platform or item.get("platform", "")
            if not isinstance(message_platform, str) or len(message_platform) > 100:
                return {"ok": False, "error": "Chat message has an invalid platform field."}
            record["platform"] = message_platform
            if record["author"] or record["text"]:
                normalized.append(record)

        try:
            with self._lock:
                archive = self._read()
                sessions = archive["sessions"]
                session = next(
                    (item for item in sessions if item.get("session_id") == session_id),
                    None,
                )
                if session is None:
                    session = {
                        "session_id": session_id,
                        "platform": platform,
                        "room_id": room_id,
                        "channel_id": channel_id,
                        "room_name": room_name,
                        "started_at": _utc_now(),
                        "updated_at": "",
                        "messages": [],
                    }
                    sessions.append(session)
                else:
                    session["platform"] = platform or session.get("platform", "")
                    session["room_id"] = room_id or session.get("room_id", "")
                    session["channel_id"] = channel_id or session.get("channel_id", "")
                    session["room_name"] = room_name or session.get("room_name", "")

                saved_messages = session.get("messages")
                if not isinstance(saved_messages, list):
                    raise ValueError("The chat archive contains an invalid session.")
                existing = {
                    _message_key(message): message
                    for message in saved_messages
                }
                for message in normalized:
                    existing.setdefault(_message_key(message), message)
                session["messages"] = list(existing.values())[-_MAX_SESSION_MESSAGES:]
                session["updated_at"] = _utc_now()
                archive["sessions"] = sessions[-_MAX_ARCHIVE_SESSIONS:]
                if self.path.exists():
                    self._write_sessions(archive["sessions"])
                else:
                    self._write_path(
                        self._session_path(session_id),
                        {"version": 1, "sessions": [session]},
                    )
            return {
                "ok": True,
                "archive": archive,
                "path": str(self.path),
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"Could not save chat archive: {exc}"}

    def append_messages(
        self,
        session_id: str,
        messages: list[dict],
        *,
        platform: str = "",
        room_id: str = "",
        channel_id: str = "",
        room_name: str = "",
    ) -> dict:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 600:
            return {"ok": False, "error": "Invalid chat session ID."}
        if not isinstance(messages, list):
            return {"ok": False, "error": "Chat messages must be a list."}
        if any(
            not isinstance(value, str) or len(value) > 500
            for value in (platform, room_id, channel_id, room_name)
        ):
            return {"ok": False, "error": "Invalid room or channel ID."}

        normalized = []
        for item in messages:
            if not isinstance(item, dict):
                return {"ok": False, "error": "Chat messages contain an invalid entry."}
            record = {}
            for key in ("timestamp", "author", "text"):
                value = item.get(key, "")
                if not isinstance(value, str) or len(value) > 20000:
                    return {"ok": False, "error": f"Chat message has an invalid {key} field."}
                record[key] = value
            message_platform = platform or item.get("platform", "")
            if not isinstance(message_platform, str) or len(message_platform) > 100:
                return {"ok": False, "error": "Chat message has an invalid platform field."}
            record["platform"] = message_platform
            if record["author"] or record["text"]:
                normalized.append(record)
        if not normalized:
            return {"ok": True, "path": str(self._session_path(session_id))}

        try:
            with self._lock:
                if self.path.exists():
                    archive = self._read()
                    self._write_sessions(archive["sessions"])

                session_path = self._session_path(session_id)
                session_archive = self._read_path(session_path)
                if len(session_archive["sessions"]) > 1:
                    raise ValueError(
                        f"Chat archive file {session_path.name} must contain exactly one room."
                    )
                session = (
                    session_archive["sessions"][0]
                    if session_archive["sessions"]
                    else None
                )
                if session is None:
                    if (
                        not session_path.exists()
                        and len(list(self.sessions_path.glob("*.json")))
                        >= _MAX_ARCHIVE_SESSIONS
                    ):
                        raise ValueError("The chat archive contains too many sessions.")
                    session = {
                        "session_id": session_id,
                        "platform": platform,
                        "room_id": room_id,
                        "channel_id": channel_id,
                        "room_name": room_name,
                        "started_at": _utc_now(),
                        "updated_at": "",
                        "messages": [],
                    }
                else:
                    session["platform"] = platform or session.get("platform", "")
                    session["room_id"] = room_id or session.get("room_id", "")
                    session["channel_id"] = channel_id or session.get("channel_id", "")
                    session["room_name"] = room_name or session.get("room_name", "")

                saved_messages = session.get("messages")
                if not isinstance(saved_messages, list):
                    raise ValueError("The chat archive contains an invalid session.")
                existing = {
                    _message_key(message): message
                    for message in saved_messages
                }
                for message in normalized:
                    existing.setdefault(_message_key(message), message)
                session["messages"] = list(existing.values())[-_MAX_SESSION_MESSAGES:]
                session["updated_at"] = _utc_now()
                self._write_path(
                    session_path,
                    {"version": 1, "sessions": [session]},
                )
            return {"ok": True, "path": str(session_path)}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"Could not append chat archive: {exc}"}

    def delete_session(self, session_id: str) -> dict:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 600:
            return {"ok": False, "error": "Invalid chat session ID."}
        try:
            with self._lock:
                archive = self._read()
                sessions = archive["sessions"]
                remaining = [
                    session for session in sessions
                    if session.get("session_id") != session_id
                ]
                if len(remaining) == len(sessions):
                    return {"ok": False, "error": "The selected saved chat session no longer exists."}
                archive["sessions"] = remaining
                if self.path.exists():
                    self._write_sessions(remaining)
                else:
                    session_path = self._session_path(session_id)
                    if session_path.exists():
                        session_path.unlink()
            return {"ok": True, "archive": archive, "path": str(self.path)}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"Could not delete saved chat: {exc}"}


class DesktopEmoteCache:
    """Persist room emote metadata and image previews for faster picker loads."""

    _MAX_ENTRIES = 30
    _MAX_IMAGE_BYTES = 4 * 1024 * 1024
    _MAX_IMAGES = 4000
    _MAX_IMAGE_TOTAL = 256 * 1024 * 1024
    _PRUNE_INTERVAL = 100

    def __init__(self, path: Path | None = None):
        self.path = path or _emote_cache_path()
        self.image_dir = self.path.with_name(f"{self.path.stem}_images")
        self._lock = threading.Lock()
        self._writes_since_prune = 0

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "entries": {}}
        if self.path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("The emote cache file exceeds the size limit.")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("version") != 1
            or not isinstance(value.get("entries"), dict)
        ):
            raise ValueError("The emote cache has an unsupported or invalid format.")
        return value

    def get(self, key: str, *, max_age: int = 86400) -> tuple[object | None, str]:
        try:
            with self._lock:
                entries = self._read()["entries"]
                entry = entries.get(key)
                if not isinstance(entry, dict):
                    return None, ""
                if time.time() - float(entry.get("saved_at", 0)) > max_age:
                    return None, ""
                return entry.get("data"), ""
        except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
            return None, f"Could not read emote cache: {exc}"

    def set(self, key: str, data: object) -> str:
        try:
            encoded = json.dumps(data, ensure_ascii=False)
            if len(encoded.encode("utf-8")) > 4 * 1024 * 1024:
                return "Emote data is too large to cache."
            with self._lock:
                cache = self._read()
                entries = cache["entries"]
                entries[key] = {"saved_at": time.time(), "data": data}
                entries = dict(
                    sorted(
                        entries.items(),
                        key=lambda item: float(item[1].get("saved_at", 0)),
                    )[-self._MAX_ENTRIES:]
                )
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._write_json(self.path, {"version": 1, "entries": entries})
            return ""
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return f"Could not write emote cache: {exc}"

    def get_image(self, url: str) -> bytes | None:
        path = self.image_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.img"
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            return None
        return data if 0 < len(data) <= self._MAX_IMAGE_BYTES else None

    def set_image(self, url: str, data: bytes) -> str:
        if not data or len(data) > self._MAX_IMAGE_BYTES:
            return ""
        path = self.image_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.img"
        try:
            self.image_dir.mkdir(parents=True, exist_ok=True)
            self._write_bytes(path, data, durable=False)
            with self._lock:
                self._writes_since_prune += 1
                if self._writes_since_prune < self._PRUNE_INTERVAL:
                    return ""
                self._writes_since_prune = 0
            return self.prune_images()
        except OSError as exc:
            return f"Could not cache emote image: {exc}"

    def prune_images(self) -> str:
        try:
            with self._lock:
                if not self.image_dir.exists():
                    return ""
                images = []
                for image in self.image_dir.glob("*.img"):
                    try:
                        stat = image.stat()
                    except FileNotFoundError:
                        continue
                    images.append((stat.st_mtime, stat.st_size, image))
                images.sort(key=lambda item: item[0])
                total = sum(size for _, size, _ in images)
                while images and (
                    len(images) > self._MAX_IMAGES
                    or total > self._MAX_IMAGE_TOTAL
                ):
                    _, size, oldest = images.pop(0)
                    oldest.unlink(missing_ok=True)
                    total -= size
            return ""
        except OSError as exc:
            return f"Could not prune emote image cache: {exc}"

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(value, temporary, ensure_ascii=False)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _write_bytes(path: Path, data: bytes, *, durable: bool = True) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(data)
                temporary.flush()
                if durable:
                    os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


_emote_http = threading.local()


def _download_emote_image(url: str) -> bytes | None:
    import requests

    session = getattr(_emote_http, "session", None)
    if session is None:
        session = requests.Session()
        _emote_http.session = session
    try:
        with session.get(url, timeout=(5, 10), stream=True) as response:
            response.raise_for_status()
            if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                return None
            image = bytearray()
            for chunk in response.iter_content(64 * 1024):
                image.extend(chunk)
                if len(image) > DesktopEmoteCache._MAX_IMAGE_BYTES:
                    return None
            return bytes(image) or None
    except requests.RequestException:
        return None


def _submit_emote_image_loads(
    pool,
    requests_for_images,
    cache,
    on_result,
    on_finished,
    cancelled,
    download=_download_emote_image,
):
    """Load each image independently and report it as soon as it is ready."""
    requests_for_images = list(requests_for_images)
    remaining = len(requests_for_images)
    lock = threading.Lock()

    def notify(callback, *args):
        try:
            callback(*args)
        except RuntimeError:
            # The picker was closed and its Qt signal bridge was deleted.
            pass

    if not remaining:
        notify(on_finished)
        return []

    def load(url):
        if cancelled():
            return None, "", True
        cached = cache.get_image(url)
        if cached:
            return cached, "", False
        data = download(url)
        if not data:
            return None, "", False
        return data, cache.set_image(url, data), False

    def done(future, index):
        nonlocal remaining
        result = None
        if not future.cancelled():
            error = future.exception()
            if error is None:
                data, cache_error, skipped = future.result()
                if not skipped:
                    result = (index, data, cache_error)
            else:
                result = (index, None, "")
        if result is not None and not cancelled():
            notify(on_result, result)
        with lock:
            remaining -= 1
            finished = remaining == 0
        if finished:
            notify(on_finished)

    futures = []
    for index, url in requests_for_images:
        future = pool.submit(load, url)
        future.add_done_callback(lambda item, index=index: done(item, index))
        futures.append(future)
    return futures


if QtCore is not None:
    class _TaskBridge(QtCore.QObject):
        finished = QtCore.Signal(object, object)


    class _EmoteImageBridge(QtCore.QObject):
        loaded = QtCore.Signal(object)
        finished = QtCore.Signal()


    class _HoverMessageWidget(QtWidgets.QFrame):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMouseTracking(True)
            self.installEventFilter(self)

        def watch_hover(self, widget):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

        def eventFilter(self, watched, event):
            if (
                event.type() == QtCore.QEvent.Type.ToolTip
                and not _reading_tooltip_allowed(watched)
            ):
                event.ignore()
                return True
            return super().eventFilter(watched, event)

    class _MonitorWorker(QtCore.QThread):
        messages = QtCore.Signal(list)
        statuses = QtCore.Signal(dict)
        failed = QtCore.Signal(str)

        def __init__(self, login_data: dict, targets: list[dict]):
            super().__init__()
            self.login_data = login_data
            self._targets_lock = threading.Lock()
            self.targets = [dict(target) for target in targets]
            self._running = True
            self._listeners = {}
            self._listener_errors = {}
            self._youtube = {}
            self._login_fingerprint = json.dumps(login_data, sort_keys=True)

        def update_targets(self, targets: list[dict]) -> None:
            with self._targets_lock:
                self.targets = [dict(target) for target in targets]

        def update_logins(self, login_data: dict) -> None:
            with self._targets_lock:
                self.login_data = dict(login_data)

        def stop(self) -> None:
            self._running = False
            for listener in self._listeners.values():
                listener.stop()
            self.wait(10000)

        def _targets_snapshot(self):
            with self._targets_lock:
                return [dict(target) for target in self.targets]

        def _sync_room_listener(self, monitor_id: str, platform: str, room_id: str, module):
            from src import user_login

            listener = self._listeners.get(monitor_id)
            if listener and str(listener.room_id) == str(room_id) and listener.running:
                return listener
            if listener:
                error = getattr(listener, "error", "")
                if error:
                    self._listener_errors[monitor_id] = error
                listener.stop()
            if not room_id:
                self._listeners.pop(monitor_id, None)
                self._listener_errors.pop(monitor_id, None)
                return None
            with user_login.using(self.login_data):
                listener = module.DanmakuListener(room_id) if platform == "bilibili" else module.MissEvanListener(room_id)
            if not listener.start():
                error = getattr(listener, "error", "")
                if not error and platform == "bilibili":
                    error = "Bilibili chat listener could not start."
                if error:
                    self._listener_errors[monitor_id] = error
                self._listeners.pop(monitor_id, None)
                self.failed.emit(f"{platform} ({room_id}): {error or 'listener failed to start'}")
                return None
            previous_error = self._listener_errors.get(monitor_id, "")
            if previous_error and hasattr(listener, "error") and not listener.error:
                listener.error = previous_error
            self._listeners[monitor_id] = listener
            return listener

        def run(self):
            from src import bilibili, missevan, user_login, youtube, youtube_web
            from src.config import CHAT_POLL_INTERVAL, ROOM_STATUS_POLL_INTERVAL

            statuses = {}
            status_poll_at = {}
            chat_poll_at = {}
            listener_attempt_at = {}
            while self._running:
                targets = {
                    str(target.get("id", "")): target
                    for target in self._targets_snapshot()
                    if target.get("id")
                }
                try:
                    now = time.monotonic()
                    with self._targets_lock:
                        login_data = dict(self.login_data)
                    login_fingerprint = json.dumps(login_data, sort_keys=True)
                    if login_fingerprint != self._login_fingerprint:
                        for listener in self._listeners.values():
                            listener.stop()
                        self._listeners.clear()
                        self._listener_errors.clear()
                        listener_attempt_at.clear()
                        self._login_fingerprint = login_fingerprint
                    for monitor_id in list(self._listeners):
                        if monitor_id not in targets:
                            self._listeners.pop(monitor_id).stop()
                            self._listener_errors.pop(monitor_id, None)
                            listener_attempt_at.pop(monitor_id, None)
                    for monitor_id in list(self._youtube):
                        if monitor_id not in targets:
                            self._youtube.pop(monitor_id, None)
                    for monitor_id in list(statuses):
                        if monitor_id not in targets:
                            statuses.pop(monitor_id, None)
                            status_poll_at.pop(monitor_id, None)
                            chat_poll_at.pop(monitor_id, None)

                    new_messages = []
                    for monitor_id, target in targets.items():
                        platform = str(target.get("platform", "")).lower()
                        value = str(target.get("target", "")).strip()
                        status = statuses.setdefault(monitor_id, {
                            "platform": platform,
                            "target": value,
                            "room_name": "",
                            "live": False,
                            "title": "",
                            "viewers": "",
                            "connection": "Connecting",
                            "error": "",
                        })
                        status["platform"] = platform
                        status["target"] = value
                        if platform == "youtube":
                            state = self._youtube.setdefault(monitor_id, {
                                "video_id": "",
                                "chat_id": "",
                                "page_token": "",
                                "backlog_loaded": False,
                            })
                            video_id = youtube.extract_video_id(value)
                            channel = youtube_web.channel_url(value)
                            if not video_id and not channel:
                                status["connection"] = "Invalid target"
                                status["error"] = "Enter a YouTube channel, live URL, or 11-character video ID."
                                continue
                            if now - status_poll_at.get(monitor_id, 0) >= ROOM_STATUS_POLL_INTERVAL:
                                status_poll_at[monitor_id] = now
                                if channel and not video_id:
                                    info = youtube_web.find_live_video(channel)
                                    new_video_id = _youtube_channel_video_id(info)
                                    status.update({
                                        "live": bool(info.get("live")),
                                        "room_name": info.get("channel", "") or status.get("room_name", ""),
                                        "title": info.get("title", ""),
                                        "viewers": info.get("viewers", ""),
                                        "error": info.get("error", ""),
                                    })
                                    if new_video_id != state["video_id"]:
                                        state.update(video_id=new_video_id, chat_id="", page_token="", backlog_loaded=False)
                                else:
                                    with user_login.using(login_data):
                                        info = youtube.get_video_live_status(video_id)
                                    status.update({
                                        "live": info.get("broadcast") == "live",
                                        "room_name": info.get("channel", "") or status.get("room_name", ""),
                                        "title": info.get("title", ""),
                                        "viewers": info.get("viewers", ""),
                                        "error": info.get("error", ""),
                                    })
                                    if video_id != state["video_id"]:
                                        state.update(video_id=video_id, chat_id="", page_token="", backlog_loaded=False)
                                if status.get("live") and state["video_id"] and not state["chat_id"]:
                                    with user_login.using(login_data):
                                        state["chat_id"], error = youtube.resolve_live_chat_id(state["video_id"])
                                    status["error"] = error
                                if not status.get("live"):
                                    state.update(chat_id="", page_token="", backlog_loaded=False)
                                status["connection"] = (
                                    "Connected" if state["chat_id"]
                                    else status["error"] or ("Waiting for chat" if status["live"] else "Waiting for stream")
                                )
                            if (
                                state["chat_id"]
                                and now - chat_poll_at.get(monitor_id, 0) >= CHAT_POLL_INTERVAL
                            ):
                                chat_poll_at[monitor_id] = now
                                with user_login.using(login_data):
                                    messages, state["page_token"], _ = youtube.get_chat_messages(
                                        state["chat_id"], state["page_token"]
                                    )
                                if not state["backlog_loaded"]:
                                    for message in messages:
                                        message["history"] = True
                                    state["backlog_loaded"] = True
                                for message in messages:
                                    message["_monitor_id"] = monitor_id
                                    message["channel_id"] = value
                                new_messages.extend(messages)
                        elif platform in ("bilibili", "missevan"):
                            room_id = (
                                bilibili.parse_room_id(value)
                                if platform == "bilibili"
                                else missevan.parse_room_id(value)
                            )
                            if not room_id:
                                status["connection"] = "Invalid target"
                                status["error"] = f"Invalid {platform.title()} room URL or ID."
                                self._sync_room_listener(monitor_id, platform, "", bilibili if platform == "bilibili" else missevan)
                                listener_attempt_at.pop(monitor_id, None)
                                continue
                            if now - status_poll_at.get(monitor_id, 0) >= ROOM_STATUS_POLL_INTERVAL:
                                status_poll_at[monitor_id] = now
                                with user_login.using(login_data):
                                    info = (
                                        bilibili.get_room_info(room_id)
                                        if platform == "bilibili"
                                        else missevan.get_room_info(room_id)
                                    )
                                status.update({
                                    "live": info.get("live_status") == 1 if platform == "bilibili" else bool(info.get("live")),
                                    "room_name": info.get("uname", "") or status.get("room_name", ""),
                                    "title": info.get("title", ""),
                                    "viewers": info.get("online", info.get("viewers", "")),
                                    "error": info.get("error", ""),
                                })
                            module = bilibili if platform == "bilibili" else missevan
                            listener = self._listeners.get(monitor_id)
                            if (
                                listener is None or not listener.running
                            ) and now - listener_attempt_at.get(monitor_id, 0) >= CHAT_POLL_INTERVAL:
                                listener_attempt_at[monitor_id] = now
                                listener = self._sync_room_listener(
                                    monitor_id, platform, room_id, module
                                )
                            if listener:
                                if platform == "bilibili":
                                    if listener.connected_uid is not None:
                                        self._listener_errors.pop(monitor_id, None)
                                    elif listener.error:
                                        self._listener_errors[monitor_id] = listener.error
                                elif listener.connected:
                                    self._listener_errors.pop(monitor_id, None)
                                elif listener.error:
                                    self._listener_errors[monitor_id] = listener.error
                                if platform == "bilibili" and listener.connected_uid is not None:
                                    status["connection"] = (
                                        "Connected (anonymous)"
                                        if listener.connected_uid == 0 else "Connected"
                                    )
                                elif getattr(listener, "connected", False):
                                    status["connection"] = "Connected"
                                elif listener.error:
                                    status["connection"] = "Reconnecting"
                                else:
                                    status["connection"] = (
                                        "Connecting" if listener.running else "Disconnected"
                                    )
                                status["error"] = getattr(listener, "error", "") or self._listener_errors.get(monitor_id, "")
                                if now - chat_poll_at.get(monitor_id, 0) >= CHAT_POLL_INTERVAL:
                                    chat_poll_at[monitor_id] = now
                                    for message in listener.pop_messages():
                                        message["_monitor_id"] = monitor_id
                                        message["room_id"] = room_id
                                        new_messages.append(message)
                            else:
                                status["connection"] = self._listener_errors.get(monitor_id, "") or "Disconnected"
                                status["error"] = self._listener_errors.get(monitor_id, "")
                        else:
                            status["connection"] = "Invalid target"
                            status["error"] = "Unsupported streaming platform."

                    if new_messages:
                        self.messages.emit(new_messages)
                    self.statuses.emit(dict(statuses))
                except Exception as exc:
                    self.failed.emit(f"Chat monitor error: {type(exc).__name__}: {exc}")
                self.msleep(250)
            for listener in self._listeners.values():
                listener.stop()


    class _ChannelTargetProxy:
        def __init__(self, window, platform: str):
            self.window = window
            self.platform = platform

        def text(self) -> str:
            entries = self.window._channels_for_platform(self.platform, enabled_only=True)
            if not entries:
                entries = self.window._channels_for_platform(self.platform)
            return entries[0]["target"] if entries else ""


    class _DesktopWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            from src import config, filters, i18n, user_login
            from src.user_login import decode, encode

            self.config = config
            self.filters = filters
            self.i18n = _DesktopI18n(i18n)
            self.user_login = user_login
            self._encode_logins = encode
            self._login_data = {}
            self._settings = QtCore.QSettings("OneJan111", "StreamingDashboard")
            self._theme = self._settings.value("theme", "light", type=str)
            if self._theme not in ("light", "dark"):
                self._theme = "light"
            self._monitor_targets = self._load_monitor_targets()
            self._monitor_cards = {}
            self._room_names = {}
            self._ui_language = self._settings.value("ui_language", "en", type=str)
            if self._ui_language not in self.i18n.UI_LANGUAGES:
                self._ui_language = "en"
            self._font_size = self._settings.value("desktop_font_size", 13, type=int)
            self._font_size = min(24, max(8, self._font_size))
            self._base_font = QtWidgets.QApplication.font()
            self._base_font.setPointSize(13)
            QtWidgets.QApplication.setFont(self._base_font)
            token = self._settings.value("login_token", "", type=str)
            if token:
                self._login_data.update(decode(token))
            self._filter = filters.make_default_filter()
            self._archive = DesktopChatArchive()
            self._emote_cache = DesktopEmoteCache()
            self._messages = []
            self._paid = []
            self._joins = []
            self._chat_image_cache = {}
            self._chat_images_pending = set()
            self._segments = []
            self._transcription_sessions = []
            self._transcription_armed_id = None
            self._transcription_lrc_offsets = {}
            self._worker = None
            self._transcriber = None
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
            self._emote_image_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=16, thread_name_prefix="emote-images"
            )
            self._activity = []
            self._hotspot_events = []
            self._hotspots = []
            self._thanked_ids = set(self._settings.value("thanked_ids", [], type=list))
            self._active_feed = "chat"
            self._feed_scroll_paused = {"chat": False, "paid": False}
            self._feed_paused_messages = {"chat": None, "paid": None}
            self._feed_message_sequence = 0
            self._tts_selection_generation = 0
            self._audio_queue = []
            self._audio_buffer = None
            self._translate_enabled = self._settings.value("translate_enabled", False, type=bool)
            self._translate_target = self._settings.value("translate_target", "en", type=str)
            self._tts_enabled = self._settings.value("tts_enabled", False, type=bool)
            self._tts_language = self._settings.value("tts_language", "auto", type=str)
            self._notify_live = self._settings.value("notify_live", True, type=bool)
            self._live_states = {}
            self._recorders = {}
            self._record_enabled_ids = set()
            self._room_titles = {}
            self._viewer_samples = []
            self._restoring_splitter_sizes = False
            self._memory_logger = None
            self._memory_process = None
            self._memory_timer = None
            self._memory_start_rss = None
            self._memory_peak_rss = 0

            self.setWindowTitle("Streaming Dashboard — PySide6")
            self.resize(1450, 920)
            self.setMinimumSize(720, 600)
            geometry = self._settings.value("window_geometry")
            if isinstance(geometry, QtCore.QByteArray) and not geometry.isEmpty():
                self.restoreGeometry(geometry)
            self._build_ui()
            self._apply_font_size()
            self._apply_ui_language()
            if self.config.TTS_USE_GTTS:
                self._audio_player = QtMultimedia.QMediaPlayer(self)
                self._audio_output = QtMultimedia.QAudioOutput(self)
                self._audio_player.setAudioOutput(self._audio_output)
                self._audio_player.mediaStatusChanged.connect(self._audio_status_changed)
            self._load_archive_view()
            self._start_monitor()
            self._start_memory_monitor()

        def _login_context(self):
            return self.user_login.using(self._login_data)

        def _load_monitor_targets(self):
            saved = self._settings.value("monitor_targets", None)
            if isinstance(saved, list):
                targets = []
                for entry in saved:
                    if not isinstance(entry, dict):
                        continue
                    platform = str(entry.get("platform", "")).lower()
                    target = str(entry.get("target", "")).strip()
                    if platform not in ("youtube", "bilibili", "missevan") or not target:
                        continue
                    monitor_id = str(entry.get("id") or f"{platform}:{target}")
                    if any(existing["id"] == monitor_id for existing in targets):
                        continue
                    targets.append({
                        "id": monitor_id,
                        "platform": platform,
                        "target": target,
                        "enabled": bool(entry.get("enabled", True)),
                    })
                return targets
            targets = []
            for platform, target in (
                ("youtube", self.config.YOUTUBE_CHANNEL),
                ("bilibili", self.config.BILIBILI_ROOM_ID),
                ("missevan", self.config.MISSEVAN_ROOM_ID),
            ):
                target = str(target or "").strip()
                if target:
                    targets.append({
                        "id": f"{platform}:{target}",
                        "platform": platform,
                        "target": target,
                        "enabled": True,
                    })
            return targets

        def _channels_for_platform(self, platform: str, enabled_only: bool = False):
            return [
                entry for entry in self._monitor_targets
                if entry["platform"] == platform
                and (entry["enabled"] or not enabled_only)
            ]

        def _save_monitor_targets(self):
            self._settings.setValue(
                "monitor_targets",
                [dict(entry) for entry in self._monitor_targets],
            )
            self._settings.sync()
            if self._settings.status() != QtCore.QSettings.Status.NoError:
                self._show_error("Unable to save monitoring channels to application settings.")

        def _monitor_target_changed(self, monitor_id: str, enabled: bool):
            for entry in self._monitor_targets:
                if entry["id"] == monitor_id:
                    entry["enabled"] = enabled
                    break
            self._save_monitor_targets()
            if self._worker:
                self._worker.update_targets(self._monitor_targets)
            self._refresh_transcription_rooms()
            self._refresh_overlay_room_selectors()
            self._refresh_feeds()

        def _persist_widget(self, widget, key):
            """Restore `widget` from QSettings `key` and save it whenever it changes."""
            save = lambda value: self._settings.setValue(key, value)
            if isinstance(widget, QtWidgets.QCheckBox):
                widget.setChecked(self._settings.value(key, widget.isChecked(), type=bool))
                widget.toggled.connect(lambda checked: save(bool(checked)))
            elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QSlider)):
                widget.setValue(self._settings.value(key, widget.value(), type=int))
                widget.valueChanged.connect(lambda value: save(int(value)))
            elif isinstance(widget, QtWidgets.QComboBox):
                saved = self._settings.value(key, "", type=str)
                index = widget.findData(saved) if saved else -1
                if index < 0 and saved:
                    index = widget.findText(saved)
                if index >= 0:
                    widget.setCurrentIndex(index)
                widget.currentIndexChanged.connect(
                    lambda _index: save(
                        str(widget.currentData())
                        if widget.currentData() is not None
                        else widget.currentText()
                    )
                )
            elif isinstance(widget, QtWidgets.QLineEdit):
                widget.setText(self._settings.value(key, widget.text(), type=str))
                widget.textChanged.connect(save)

        def _build_ui(self):
            theme_menu = self.menuBar().addMenu("Theme")
            self._theme_menu = theme_menu
            theme_group = QtGui.QActionGroup(self)
            theme_group.setExclusive(True)
            for theme, label in (("light", "Light"), ("dark", "Dark")):
                action = theme_menu.addAction(label)
                action.setProperty("_desktop_source_text", label)
                action.setCheckable(True)
                action.setChecked(theme == self._theme)
                action.triggered.connect(
                    lambda checked=False, selected_theme=theme:
                    self._set_theme(selected_theme)
                )
                theme_group.addAction(action)

            self._language_menu = self.menuBar().addMenu("Interface language")
            self._language_actions = {}
            language_group = QtGui.QActionGroup(self)
            language_group.setExclusive(True)
            for code, label in (("en", "English"), ("zh", "简体中文"), ("ja", "日本語")):
                action = self._language_menu.addAction(label)
                action.setCheckable(True)
                action.setChecked(code == self._ui_language)
                action.triggered.connect(
                    lambda checked=False, selected_language=code:
                    self._set_ui_language(selected_language)
                )
                language_group.addAction(action)
                self._language_actions[code] = action

            tabs = QtWidgets.QTabWidget()
            tabs.addTab(self._make_chat_tab(), "Chat")
            tabs.addTab(self._make_monitor_cookies_tab(), "Monitoring / Cookies")
            tabs.addTab(self._make_settings_tab(), "Settings / TTS")
            tabs.addTab(self._make_filters_tab(), "Moderation")
            tabs.addTab(self._make_obs_tab(), "OBS")
            tabs.addTab(self._make_transcription_tab(), "Transcription")
            analytics_index = tabs.addTab(self._make_analytics_tab(), "Analytics")
            tabs.setTabVisible(analytics_index, self.config.ANALYTICS_ENABLED)
            tabs.addTab(self._make_archive_tab(), "Saved Chat")
            tabs.setCurrentIndex(
                min(max(0, self._settings.value("main_tab", 0, type=int)), tabs.count() - 1)
            )
            tabs.currentChanged.connect(
                lambda index: self._settings.setValue("main_tab", int(index))
            )
            tabs.currentChanged.connect(
                lambda _index: QtWidgets.QToolTip.hideText()
            )
            self.setCentralWidget(tabs)
            self.statusBar().showMessage("Ready")
            self._memory_status = QtWidgets.QLabel("RAM: starting")
            self._memory_status.setToolTip(
                "Live process memory and app-owned collection metrics."
            )
            self.statusBar().addPermanentWidget(self._memory_status)
            self._memory_log_button = QtWidgets.QToolButton()
            _set_desktop_widget_text(
                self._memory_log_button,
                "Memory log",
                self._ui_language,
                self.i18n,
            )
            self._memory_log_button.clicked.connect(
                self._open_memory_log_folder
            )
            self.statusBar().addPermanentWidget(self._memory_log_button)

        def _start_memory_monitor(self):
            try:
                import psutil

                log_path = _memory_log_path()
                log_path.parent.mkdir(parents=True, exist_ok=True)
                logger = logging.getLogger("streaming.desktop.memory")
                logger.setLevel(logging.INFO)
                logger.propagate = False
                resolved_path = str(log_path.resolve())
                handler = next(
                    (
                        item for item in logger.handlers
                        if getattr(item, "baseFilename", "") == resolved_path
                    ),
                    None,
                )
                if handler is None:
                    handler = RotatingFileHandler(
                        log_path,
                        maxBytes=5 * 1024 * 1024,
                        backupCount=3,
                        encoding="utf-8",
                    )
                    handler.setFormatter(
                        logging.Formatter("%(asctime)s %(message)s")
                    )
                    logger.addHandler(handler)
                self._memory_logger = logger
                self._memory_process = psutil.Process(os.getpid())
                self._memory_logger.info(
                    json.dumps({
                        "event": "monitor_started",
                        "sample_interval_seconds": 10,
                        "log_path": str(log_path),
                    })
                )
                self._memory_timer = QtCore.QTimer(self)
                self._memory_timer.setInterval(10_000)
                self._memory_timer.timeout.connect(self._sample_memory_usage)
                self._memory_timer.start()
                self._sample_memory_usage()
            except (ImportError, OSError, RuntimeError) as exc:
                self._memory_status.setText("RAM monitor unavailable")
                self._memory_status.setToolTip(str(exc))
                self._show_error(
                    f"Could not start the memory monitor: {type(exc).__name__}: {exc}"
                )

        def _sample_memory_usage(self):
            import psutil

            if self._memory_logger is None or self._memory_process is None:
                return
            try:
                process_metrics = _memory_process_metrics(
                    self._memory_process, psutil
                )
                collection_metrics = _memory_collection_metrics(self)
                snapshot = {
                    "event": "memory_sample",
                    "timestamp": _utc_now(),
                    **process_metrics,
                    **collection_metrics,
                }
                app_mb = process_metrics["process_rss_bytes"] / (1024 * 1024)
                tree_mb = process_metrics["process_tree_rss_bytes"] / (
                    1024 * 1024
                )
                if self._memory_start_rss is None:
                    self._memory_start_rss = process_metrics["process_rss_bytes"]
                self._memory_peak_rss = max(
                    self._memory_peak_rss,
                    process_metrics["process_rss_bytes"],
                )
                snapshot["process_rss_delta_bytes"] = (
                    process_metrics["process_rss_bytes"] - self._memory_start_rss
                )
                snapshot["process_rss_peak_bytes"] = self._memory_peak_rss
                self._memory_status.setText(
                    f"RAM {app_mb:.0f} / {tree_mb:.0f} MiB"
                )
                metrics = ", ".join(
                    f"{key}={value}" for key, value in collection_metrics.items()
                )
                self._memory_status.setToolTip(
                    f"App RSS: {app_mb:.1f} MiB\n"
                    f"App + child processes: {tree_mb:.1f} MiB\n"
                    f"Since monitor start: "
                    f"{snapshot['process_rss_delta_bytes'] / (1024 * 1024):+.1f} MiB\n"
                    f"{metrics}\n"
                    f"Log: {_memory_log_path()}"
                )
                self._memory_logger.info(json.dumps(snapshot, sort_keys=True))
            except (OSError, psutil.Error, RuntimeError, TypeError, ValueError) as exc:
                self._memory_status.setText("RAM monitor error")
                self._memory_status.setToolTip(str(exc))
                self._memory_logger.exception(
                    "Memory sampling failed: %s", type(exc).__name__
                )

        def _open_memory_log_folder(self):
            folder = _memory_log_path().parent
            if not folder.is_dir():
                self._show_error(f"Memory log folder does not exist: {folder}")
                return
            if not QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(str(folder))
            ):
                self._show_error(f"Could not open memory log folder: {folder}")

        def _set_theme(self, theme):
            if theme not in ("light", "dark"):
                self._show_error("Select a valid application theme.")
                return
            self._theme = theme
            self._settings.setValue("theme", theme)
            self._settings.sync()
            self._apply_theme()
            if self._settings.status() != QtCore.QSettings.Status.NoError:
                self._show_error("Unable to save the application theme setting.")

        def _apply_theme(self):
            dark = self._theme == "dark"
            colors = {
                "window": "#232629" if dark else "#f4f5f7",
                "window_text": "#eff0f1" if dark else "#202124",
                "base": "#17191c" if dark else "#ffffff",
                "alternate": "#292c30" if dark else "#eef0f3",
                "text": "#eff0f1" if dark else "#202124",
                "button": "#303338" if dark else "#e8eaed",
                "button_text": "#eff0f1" if dark else "#202124",
                "highlight": "#168bd2",
                "highlighted_text": "#ffffff",
                "tooltip": "#303338" if dark else "#fffbe6",
                "tooltip_text": "#eff0f1" if dark else "#202124",
                "link": "#66baff" if dark else "#0969da",
                "placeholder": "#a0a4aa" if dark else "#70757a",
            }
            palette = QtGui.QPalette()
            palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(colors["window"]))
            palette.setColor(
                QtGui.QPalette.ColorRole.WindowText,
                QtGui.QColor(colors["window_text"]),
            )
            palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(colors["base"]))
            palette.setColor(
                QtGui.QPalette.ColorRole.AlternateBase,
                QtGui.QColor(colors["alternate"]),
            )
            palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(colors["text"]))
            palette.setColor(
                QtGui.QPalette.ColorRole.Button,
                QtGui.QColor(colors["button"]),
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.ButtonText,
                QtGui.QColor(colors["button_text"]),
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.BrightText,
                QtGui.QColor("#ff6b6b" if dark else "#d1242f"),
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.Highlight,
                QtGui.QColor(colors["highlight"]),
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.HighlightedText,
                QtGui.QColor(colors["highlighted_text"]),
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.ToolTipBase,
                QtGui.QColor(colors["tooltip"]),
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.ToolTipText,
                QtGui.QColor(colors["tooltip_text"]),
            )
            palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(colors["link"]))
            palette.setColor(
                QtGui.QPalette.ColorRole.PlaceholderText,
                QtGui.QColor(colors["placeholder"]),
            )
            QtWidgets.QApplication.instance().setPalette(palette)
            for card in self.findChildren(QtWidgets.QFrame, "monitorChannelCard"):
                card.setStyleSheet(
                    "#monitorChannelCard { "
                    f"background: {colors['base']}; "
                    "border: 1px solid #168bd2; border-radius: 6px; }"
                    "#monitorChannelCard QLabel, "
                    "#monitorChannelCard QCheckBox { "
                    f"color: {colors['text']}; border: 0; }}"
                )

        def _make_monitor_cookies_tab(self):
            content = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(content)
            monitor_tab = self._make_monitor_tab()
            cookies_tab = self._make_cookies_tab()
            layout.addWidget(monitor_tab, 1)
            layout.addWidget(self._make_recording_settings())
            layout.addWidget(self.login_status_group)
            layout.addWidget(cookies_tab)
            scroll_area = QtWidgets.QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(content)
            return scroll_area

        def _make_chat_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            self._feed_splitter = QtWidgets.QSplitter(
                QtCore.Qt.Orientation.Vertical
            )
            self._feed_splitter.setChildrenCollapsible(False)
            self._chat_splitter = QtWidgets.QSplitter(
                QtCore.Qt.Orientation.Horizontal
            )
            self._chat_splitter.setChildrenCollapsible(False)
            self.chat_list = QtWidgets.QListWidget()
            self.paid_list = QtWidgets.QListWidget()
            self.chat_list.setAlternatingRowColors(True)
            self.paid_list.setAlternatingRowColors(True)
            for view in (self.chat_list, self.paid_list):
                view.setWordWrap(True)
                view.setUniformItemSizes(False)
                view.setSelectionMode(
                    QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
                )
            self.chat_list.itemSelectionChanged.connect(lambda: setattr(self, "_active_feed", "chat"))
            self.paid_list.itemSelectionChanged.connect(lambda: setattr(self, "_active_feed", "paid"))
            self.chat_list.itemClicked.connect(
                lambda item: self._feed_message_clicked("chat", item)
            )
            self.paid_list.itemClicked.connect(
                lambda item: self._feed_message_clicked("paid", item)
            )
            self._chat_feed_group = self._feed_group("Chat", self.chat_list)
            self._paid_feed_group = self._feed_group(
                "Gifts / Super Chats", self.paid_list
            )
            self._chat_splitter.addWidget(self._chat_feed_group)
            self._chat_splitter.addWidget(self._paid_feed_group)
            self._restore_splitter_sizes(
                self._chat_splitter,
                "chat_splitter_horizontal_sizes",
                [3, 2],
            )
            self._chat_splitter.splitterMoved.connect(
                lambda *_: self._refresh_feeds()
            )
            self._chat_splitter.splitterMoved.connect(
                lambda *_: self._save_chat_splitter_sizes()
            )
            self._feed_splitter.addWidget(self._chat_splitter)
            self._update_chat_splitter_layout(self.width())
            self.joins_list = QtWidgets.QListWidget()
            self._joins_feed_group = self._feed_group(
                "Joins", self.joins_list
            )
            self._feed_splitter.addWidget(self._joins_feed_group)
            self._feed_splitter.setStretchFactor(0, 5)
            self._feed_splitter.setStretchFactor(1, 1)
            self._restore_splitter_sizes(
                self._feed_splitter, "feed_splitter_sizes", [7, 1]
            )
            self._feed_splitter.splitterMoved.connect(
                lambda *_: self._save_splitter_sizes(
                    "feed_splitter_sizes", self._feed_splitter
                )
            )
            layout.addWidget(self._feed_splitter, 1)
            filters_row = QtWidgets.QHBoxLayout()
            filters_row.addWidget(QtWidgets.QLabel("Chat rooms (one per site):"))
            self.site_visible = {}
            self.chat_room_selectors = {}
            for site in ("youtube", "bilibili", "missevan"):
                check = QtWidgets.QCheckBox(site.title())
                check.setChecked(True)
                self._persist_widget(check, f"chat_site_visible_{site}")
                check.toggled.connect(
                    lambda visible, platform=site:
                    self._chat_site_visibility_changed(platform, visible)
                )
                self.site_visible[site] = check
                filters_row.addWidget(check)
                selector = QtWidgets.QComboBox()
                selector.setMinimumWidth(150)
                selector.setToolTip(
                    self.i18n.translate(
                        "Choose the {site} room shown in chat",
                        self._ui_language,
                        site=site.title(),
                    )
                )
                selector.currentIndexChanged.connect(
                    lambda _, platform=site: self._chat_room_changed(platform)
                )
                self.chat_room_selectors[site] = selector
                filters_row.addWidget(selector)
            self._refresh_chat_room_selectors()
            filters_row.addStretch(1)
            layout.addLayout(filters_row)

            send_row = QtWidgets.QHBoxLayout()
            self.send_input = QtWidgets.QLineEdit()
            self.send_input.setPlaceholderText("Message to send to selected live rooms")
            self.send_input.returnPressed.connect(self._send_message)
            self.send_targets = {}
            for site in ("youtube", "bilibili", "missevan"):
                check = QtWidgets.QCheckBox(site.title())
                check.setChecked(site != "youtube")
                self._persist_widget(check, f"send_target_{site}")
                self.send_targets[site] = check
                send_row.addWidget(check)
            send_row.addWidget(self.send_input, 1)
            emote_button = QtWidgets.QPushButton("Emotes / stickers")
            emote_button.clicked.connect(self._show_emotes)
            send_row.addWidget(emote_button)
            send_button = QtWidgets.QPushButton("Send")
            send_button.clicked.connect(self._send_message)
            send_row.addWidget(send_button)
            layout.addLayout(send_row)
            self._chat_copy_shortcut = QtGui.QShortcut(
                QtGui.QKeySequence.StandardKey.Copy, widget
            )
            self._chat_copy_shortcut.setContext(
                QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            self._chat_copy_shortcut.activated.connect(self._copy_selected_chat)
            controls = QtWidgets.QHBoxLayout()
            self.live_status = QtWidgets.QLabel("Starting monitor…")
            controls.addWidget(self.live_status, 1)
            clear_button = QtWidgets.QPushButton("Clear Chat window")
            clear_button.clicked.connect(self._clear_chat_window)
            controls.addWidget(clear_button)
            skip_speech = QtWidgets.QPushButton("Skip speech")
            skip_speech.clicked.connect(lambda: self._stop_speech(clear=False))
            controls.addWidget(skip_speech)
            stop_speech = QtWidgets.QPushButton("Clear all speech")
            stop_speech.clicked.connect(lambda: self._stop_speech(clear=True))
            controls.addWidget(stop_speech)
            layout.addLayout(controls)
            return widget

        def _refresh_chat_room_selectors(self):
            selectors = getattr(self, "chat_room_selectors", {})
            previous_selections = {
                platform: selector.currentData() or ""
                for platform, selector in selectors.items()
            }
            for platform, selector in selectors.items():
                selected_id = selector.currentData()
                selector.blockSignals(True)
                selector.clear()
                selector.addItem(
                    self.i18n.translate(
                        "No room selected", self._ui_language
                    ),
                    "",
                )
                entries = self._channels_for_platform(platform)
                for entry in entries:
                    selector.addItem(
                        self._room_names.get(entry["id"]) or entry["target"],
                        entry["id"],
                    )
                has_saved_selection = self._settings.contains(
                    f"chat_room_{platform}"
                )
                if selected_id is None:
                    selected_id = (
                        self._settings.value(
                            f"chat_room_{platform}", "", type=str
                        )
                        if has_saved_selection
                        else None
                    )
                index = selector.findData(selected_id) if selected_id is not None else -1
                if index < 0 and not has_saved_selection:
                    index = next(
                        (
                            i + 1 for i, entry in enumerate(entries)
                            if entry["enabled"]
                        ),
                        0,
                    )
                elif index < 0 and selected_id:
                    index = next(
                        (
                            i + 1 for i, entry in enumerate(entries)
                            if entry["enabled"]
                        ),
                        0,
                    )
                selector.setCurrentIndex(max(0, index))
                selector.blockSignals(False)
                current_id = selector.currentData() or ""
                self._settings.setValue(f"chat_room_{platform}", current_id)
            if any(
                (selector.currentData() or "") != previous_selections.get(platform, "")
                for platform, selector in selectors.items()
            ):
                self._invalidate_chat_speech()
            self._settings.sync()
            if self._settings.status() != QtCore.QSettings.Status.NoError:
                self._show_error(
                    "Unable to save chat room selections to application settings."
                )
            self._retain_selected_feed_messages()
            self._refresh_overlay_room_selectors()
            self._refresh_feeds()

        def _refresh_overlay_room_selectors(self):
            for platform, selector in getattr(self, "overlay_rooms", {}).items():
                selected_id = selector.currentData()
                if selected_id is None:
                    selected_id = self._settings.value(
                        f"overlay_room_{platform}", "", type=str
                    )
                selector.blockSignals(True)
                selector.clear()
                entries = self._channels_for_platform(platform)
                if not entries:
                    selector.addItem(
                        self.i18n.translate("No room configured", self._ui_language), ""
                    )
                for entry in entries:
                    name = self._room_names.get(entry["id"], "").strip()
                    target = entry["target"]
                    label = f"{name} · {target}" if name and name != target else target
                    selector.addItem(label, entry["id"])
                index = selector.findData(selected_id) if selected_id else -1
                selector.setCurrentIndex(max(0, index))
                selector.setEnabled(bool(entries))
                selector.blockSignals(False)

        def _overlay_room_changed(self, platform):
            selector = self.overlay_rooms[platform]
            self._settings.setValue(
                f"overlay_room_{platform}", str(selector.currentData() or "")
            )
            self._settings.sync()

        def _chat_room_changed(self, platform):
            selector = self.chat_room_selectors[platform]
            self._invalidate_chat_speech()
            self._settings.setValue(
                f"chat_room_{platform}", selector.currentData() or ""
            )
            self._settings.sync()
            if self._settings.status() != QtCore.QSettings.Status.NoError:
                self._show_error(
                    "Unable to save chat room selections to application settings."
                )
            self._retain_selected_feed_messages()
            self._refresh_feeds()

        def _selected_chat_room_ids(self):
            return {
                platform: str(selector.currentData() or "")
                for platform, selector in getattr(
                    self, "chat_room_selectors", {}
                ).items()
            }

        def _retain_selected_feed_messages(self):
            selected_ids = self._selected_chat_room_ids()
            room_ids = {entry["id"] for entry in self._monitor_targets}
            limit = (
                self.max_messages.value()
                if hasattr(self, "max_messages")
                else self.config.MAX_CHAT_DISPLAY
            )
            self._messages = _retain_selected_room_messages(
                self._messages, selected_ids, room_ids, limit
            )
            self._paid = _retain_selected_room_messages(
                self._paid, selected_ids, room_ids, limit
            )
            self._joins = _retain_selected_room_messages(
                self._joins, selected_ids, room_ids, limit
            )

        def _chat_site_visibility_changed(self, platform, visible):
            if not visible:
                self._invalidate_chat_speech()
            self._refresh_feeds()

        def _invalidate_chat_speech(self):
            self._tts_selection_generation += 1
            from src.tts import stop_speaking

            stop_speaking(clear=True)
            self._audio_queue.clear()
            player = getattr(self, "_audio_player", None)
            if player is not None:
                player.stop()
            buffer = getattr(self, "_audio_buffer", None)
            if buffer is not None:
                buffer.close()
                buffer.deleteLater()
                self._audio_buffer = None

        def _is_selected_chat_message(self, message, queued_generation=None):
            selected_ids = {
                platform: str(selector.currentData() or "")
                for platform, selector in self.chat_room_selectors.items()
            }
            room_ids = {entry["id"] for entry in self._monitor_targets}
            visible_platforms = {
                platform
                for platform, checkbox in self.site_visible.items()
                if checkbox.isChecked()
            }
            if queued_generation is None:
                queued_generation = self._tts_selection_generation
            return _chat_speech_is_current(
                message,
                selected_ids,
                room_ids,
                visible_platforms,
                queued_generation,
                self._tts_selection_generation,
            )

        def _clear_chat_window(self):
            self._invalidate_chat_speech()
            self._messages.clear()
            self._paid.clear()
            self._joins.clear()
            self._refresh_feeds()

        def _feed_group(self, title, view):
            group = QtWidgets.QGroupBox(title)
            layout = QtWidgets.QVBoxLayout(group)
            layout.addWidget(view)
            return group

        def _make_monitor_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            self.target_inputs = {
                platform: _ChannelTargetProxy(self, platform)
                for platform in ("youtube", "bilibili", "missevan")
            }
            add_row = QtWidgets.QHBoxLayout()
            self.channel_platform = QtWidgets.QComboBox()
            self.channel_platform.addItem("YouTube", "youtube")
            self.channel_platform.addItem("Bilibili", "bilibili")
            self.channel_platform.addItem("MissEvan", "missevan")
            self.channel_input = QtWidgets.QLineEdit()
            self.channel_input.setPlaceholderText("Channel ID, room ID, or link")
            self.channel_input.returnPressed.connect(self._add_monitor_target)
            add_button = QtWidgets.QPushButton("Add Channel")
            add_button.clicked.connect(self._add_monitor_target)
            add_row.addWidget(self.channel_platform)
            add_row.addWidget(self.channel_input, 1)
            add_row.addWidget(add_button)
            layout.addLayout(add_row)

            self.channel_cards = QtWidgets.QWidget()
            self.channel_grid = QtWidgets.QGridLayout(self.channel_cards)
            self.channel_grid.setContentsMargins(0, 0, 0, 0)
            self.channel_grid.setHorizontalSpacing(12)
            self.channel_grid.setVerticalSpacing(12)
            layout.addWidget(self.channel_cards, 1)
            self._refresh_monitor_cards()

            self.notify_live_check = QtWidgets.QCheckBox("Notify me when a monitored stream goes live")
            self.notify_live_check.setChecked(self._notify_live)
            self.notify_live_check.toggled.connect(self._set_notify_live)
            layout.addWidget(self.notify_live_check)
            return widget

        def _add_monitor_target(self):
            platform = self.channel_platform.currentData()
            target = self.channel_input.text().strip()
            if not target:
                self._show_error("Enter a channel ID, room ID, or link first.")
                return
            if platform == "youtube":
                from src import youtube, youtube_web
                normalized = youtube.extract_video_id(target) or youtube_web.channel_url(target)
                if not normalized:
                    self._show_error("Enter a valid YouTube channel, live URL, or video ID.")
                    return
                target = normalized
            elif platform == "bilibili":
                from src import bilibili
                target = bilibili.parse_room_id(target)
                if not target:
                    self._show_error("Enter a valid Bilibili room URL or ID.")
                    return
            else:
                from src import missevan
                target = missevan.parse_room_id(target)
                if not target:
                    self._show_error("Enter a valid MissEvan room URL or ID.")
                    return
            if any(
                entry["platform"] == platform and entry["target"] == target
                for entry in self._monitor_targets
            ):
                self._show_error("That channel or room is already in the monitor list.")
                return
            entry = {
                "id": f"{platform}:{target}",
                "platform": platform,
                "target": target,
                "enabled": True,
            }
            self._monitor_targets.append(entry)
            self._save_monitor_targets()
            self._refresh_monitor_cards()
            self._refresh_chat_room_selectors()
            self._refresh_transcription_rooms()
            if self._worker:
                self._worker.update_targets(self._monitor_targets)
            self.channel_input.clear()

        def _remove_monitor_target(self, monitor_id: str):
            if monitor_id == self._transcription_armed_id:
                self._stop_transcription()
            self._stop_recording(monitor_id)
            self._recorders.pop(monitor_id, None)
            self._record_enabled_ids.discard(monitor_id)
            self._monitor_targets = [
                entry for entry in self._monitor_targets if entry["id"] != monitor_id
            ]
            self._save_monitor_targets()
            self._refresh_monitor_cards()
            self._refresh_chat_room_selectors()
            self._refresh_transcription_rooms()
            if self._worker:
                self._worker.update_targets(self._monitor_targets)
            self._refresh_feeds()

        def _refresh_monitor_cards(self):
            while self.channel_grid.count():
                item = self.channel_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._monitor_cards = {}
            for index, entry in enumerate(self._monitor_targets):
                card = QtWidgets.QFrame()
                card.setObjectName("monitorChannelCard")
                card.setMinimumHeight(145)
                card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
                card_layout = QtWidgets.QVBoxLayout(card)
                title = QtWidgets.QLabel(
                    f"{entry['platform'].title()} · {entry['target']}"
                )
                title.setWordWrap(True)
                title.setStyleSheet("font-size: 13pt; font-weight: 600; border: 0;")
                card_layout.addWidget(title)
                detail = QtWidgets.QLabel("")
                detail.setWordWrap(True)
                detail.setStyleSheet("border: 0;")
                card_layout.addWidget(detail)
                connection = QtWidgets.QLabel()
                connection_source = "Connecting"
                _set_desktop_widget_text(
                    connection, connection_source, self._ui_language, self.i18n
                )
                connection.setStyleSheet("border: 0;")
                card_layout.addWidget(connection)
                controls = QtWidgets.QHBoxLayout()
                monitor = QtWidgets.QCheckBox()
                _set_desktop_widget_text(
                    monitor, "Allow saving", self._ui_language, self.i18n
                )
                monitor.setToolTip(
                    self.i18n.translate(
                        "Live chat is received either way. This controls whether "
                        "messages from this room can be saved.",
                        self._ui_language,
                    )
                )
                monitor.setChecked(entry["enabled"])
                monitor.toggled.connect(
                    lambda enabled, monitor_id=entry["id"]:
                    self._monitor_target_changed(monitor_id, enabled)
                )
                controls.addWidget(monitor)
                record_toggle = None
                recording = None
                if entry["platform"] in ("youtube", "bilibili", "missevan"):
                    record_toggle = QtWidgets.QCheckBox()
                    _set_desktop_widget_text(
                        record_toggle, "Record", self._ui_language, self.i18n
                    )
                    record_toggle.setChecked(entry["id"] in self._record_enabled_ids)
                    record_toggle.toggled.connect(
                        lambda enabled, monitor_id=entry["id"]:
                        self._set_recording(monitor_id, enabled)
                    )
                    controls.addWidget(record_toggle)
                    recording = QtWidgets.QLabel("")
                    recording.setStyleSheet("color: #b42318; border: 0;")
                    recording.setVisible(False)
                    card_layout.addWidget(recording)
                controls.addStretch(1)
                remove = QtWidgets.QPushButton()
                _set_desktop_widget_text(
                    remove, "Remove", self._ui_language, self.i18n
                )
                remove.clicked.connect(
                    lambda _, monitor_id=entry["id"]:
                    self._remove_monitor_target(monitor_id)
                )
                controls.addWidget(remove)
                card_layout.addLayout(controls)
                self._monitor_cards[entry["id"]] = {
                    "widget": card,
                    "title": title,
                    "detail": detail,
                    "connection": connection,
                    "monitor": monitor,
                    "record_toggle": record_toggle,
                    "recording": recording,
                }
            self._layout_channel_cards()
            self._apply_theme()
            self._refresh_recording_status()

        def _layout_channel_cards(self):
            if not hasattr(self, "channel_grid"):
                return
            while self.channel_grid.count():
                self.channel_grid.takeAt(0)
            columns = 3
            for column in range(columns):
                self.channel_grid.setColumnStretch(column, 1)
            for row in range(len(self._monitor_cards) + 2):
                self.channel_grid.setRowStretch(row, 0)
            for index, card in enumerate(self._monitor_cards.values()):
                self.channel_grid.addWidget(
                    card["widget"], index // columns, index % columns
                )
            self.channel_grid.setRowStretch(
                (len(self._monitor_cards) // columns) + 1, 1
            )

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if hasattr(self, "channel_cards") and self.channel_grid.count():
                self._layout_channel_cards()
            if hasattr(self, "chat_list"):
                self._update_chat_splitter_layout(self.width())
                QtCore.QTimer.singleShot(80, self._refresh_feeds)

        def _update_chat_splitter_layout(self, width):
            if not hasattr(self, "_chat_splitter"):
                return
            layout_name, order = _chat_splitter_layout(width)
            if getattr(self, "_chat_splitter_layout_name", None) == layout_name:
                return
            self._chat_splitter_layout_name = layout_name
            orientation = (
                QtCore.Qt.Orientation.Vertical
                if layout_name == "vertical"
                else QtCore.Qt.Orientation.Horizontal
            )
            self._restoring_splitter_sizes = True
            self._chat_splitter.setOrientation(orientation)
            widgets = {
                "chat": self._chat_feed_group,
                "paid": self._paid_feed_group,
            }
            for index, name in enumerate(order):
                self._chat_splitter.insertWidget(index, widgets[name])
            key = (
                "chat_splitter_vertical_sizes"
                if layout_name == "vertical"
                else "chat_splitter_horizontal_sizes"
            )
            defaults = [2, 3] if layout_name == "vertical" else [3, 2]
            self._restore_splitter_sizes(self._chat_splitter, key, defaults)
            self._restoring_splitter_sizes = False

        def _restore_splitter_sizes(self, splitter, key, defaults):
            splitter.setSizes(
                _saved_splitter_sizes(self._settings, key, defaults)
            )

        def _save_splitter_sizes(self, key, splitter):
            if self._restoring_splitter_sizes:
                return
            sizes = splitter.sizes()
            if len(sizes) == 2 and sum(sizes) > 0:
                self._settings.setValue(key, sizes)

        def _save_chat_splitter_sizes(self):
            layout_name = self._chat_splitter_layout_name
            key = (
                "chat_splitter_vertical_sizes"
                if layout_name == "vertical"
                else "chat_splitter_horizontal_sizes"
            )
            self._save_splitter_sizes(key, self._chat_splitter)

        def _make_settings_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            language_form = QtWidgets.QFormLayout()
            self.font_size = QtWidgets.QSpinBox()
            self.font_size.setRange(8, 24)
            self.font_size.setValue(self._font_size)
            self.font_size.setKeyboardTracking(False)
            self.font_size_value = QtWidgets.QLabel()
            decrease_font = QtWidgets.QPushButton("−")
            decrease_font.setAccessibleName("Decrease chat font size")
            decrease_font.setToolTip("Decrease chat font size")
            decrease_font.setFixedSize(40, 34)
            decrease_font.clicked.connect(self.font_size.stepDown)
            increase_font = QtWidgets.QPushButton("+")
            increase_font.setAccessibleName("Increase chat font size")
            increase_font.setToolTip("Increase chat font size")
            increase_font.setFixedSize(40, 34)
            increase_font.clicked.connect(self.font_size.stepUp)
            font_control = QtWidgets.QWidget()
            font_layout = QtWidgets.QHBoxLayout(font_control)
            font_layout.setContentsMargins(0, 0, 0, 0)
            font_layout.addWidget(decrease_font)
            font_layout.addWidget(self.font_size)
            font_layout.addWidget(increase_font)
            font_layout.addWidget(self.font_size_value)
            self.font_size.valueChanged.connect(self._set_font_size)
            language_form.addRow("Chat font size", font_control)
            self.translation_toggle = QtWidgets.QCheckBox("Translate chat messages")
            self.translation_toggle.setChecked(self._translate_enabled)
            language_form.addRow("Translation", self.translation_toggle)
            self.translation_target = QtWidgets.QComboBox()
            for code, label in (("en", "English"), ("zh-CN", "简体中文"), ("zh-TW", "繁體中文"), ("ja", "日本語"), ("ko", "한국어")):
                self.translation_target.addItem(label, code)
            target_index = self.translation_target.findData(self._translate_target)
            self.translation_target.setCurrentIndex(target_index if target_index >= 0 else 0)
            language_form.addRow("Translate to", self.translation_target)
            layout.addLayout(language_form)
            tts_group = QtWidgets.QGroupBox("Text to speech")
            tts_form = QtWidgets.QFormLayout(tts_group)
            self.tts_toggle = QtWidgets.QCheckBox("Read new messages aloud")
            self.tts_toggle.setChecked(self._tts_enabled)
            tts_form.addRow(self.tts_toggle)
            self.tts_lang = QtWidgets.QComboBox()
            for code, entry in __import__("src.tts", fromlist=["LANGUAGES"]).LANGUAGES.items():
                self.tts_lang.addItem(entry[0], code)
            lang_index = self.tts_lang.findData(self._tts_language)
            self.tts_lang.setCurrentIndex(lang_index if lang_index >= 0 else 0)
            tts_form.addRow("Voice language", self.tts_lang)
            self.tts_paid = QtWidgets.QCheckBox("Read gifts and paid messages")
            self.tts_paid.setChecked(True)
            self._persist_widget(self.tts_paid, "tts_paid")
            tts_form.addRow(self.tts_paid)
            self.tts_joins = QtWidgets.QCheckBox("Read room joins")
            self._persist_widget(self.tts_joins, "tts_joins")
            tts_form.addRow(self.tts_joins)
            self.tts_translate = QtWidgets.QCheckBox("Read translated messages when available")
            self._persist_widget(self.tts_translate, "tts_translate")
            tts_form.addRow(self.tts_translate)
            self.tts_skip_name = QtWidgets.QCheckBox("Do not announce usernames for chat messages")
            self.tts_skip_name.setChecked(self._settings.value("tts_skip_name", False, type=bool))
            self.tts_skip_name.toggled.connect(
                lambda enabled: self._settings.setValue("tts_skip_name", enabled)
            )
            tts_form.addRow(self.tts_skip_name)
            self.tts_skip_emoji = QtWidgets.QCheckBox("Skip emoji-only messages")
            self.tts_skip_emoji.setChecked(True)
            self._persist_widget(self.tts_skip_emoji, "tts_skip_emoji")
            tts_form.addRow(self.tts_skip_emoji)
            self.tts_rate = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            self.tts_rate.setRange(80, 300)
            self.tts_rate.setValue(150)
            self._persist_widget(self.tts_rate, "tts_rate")
            self.tts_rate.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
            self.tts_rate.setTickInterval(20)
            self.tts_rate_value = QtWidgets.QLabel()
            rate_control = QtWidgets.QWidget()
            rate_layout = QtWidgets.QHBoxLayout(rate_control)
            rate_layout.setContentsMargins(0, 0, 0, 0)
            rate_layout.addWidget(self.tts_rate, 1)
            rate_layout.addWidget(self.tts_rate_value)
            self.tts_rate.valueChanged.connect(
                lambda value: self.tts_rate_value.setText(f"{value} WPM")
            )
            self.tts_rate.valueChanged.emit(self.tts_rate.value())
            tts_form.addRow("Speech rate", rate_control)

            self.tts_volume = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            self.tts_volume.setRange(0, 100)
            self.tts_volume.setValue(100)
            self._persist_widget(self.tts_volume, "tts_volume")
            self.tts_volume.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
            self.tts_volume.setTickInterval(10)
            self.tts_volume_value = QtWidgets.QLabel()
            volume_control = QtWidgets.QWidget()
            volume_layout = QtWidgets.QHBoxLayout(volume_control)
            volume_layout.setContentsMargins(0, 0, 0, 0)
            volume_layout.addWidget(self.tts_volume, 1)
            volume_layout.addWidget(self.tts_volume_value)
            self.tts_volume.valueChanged.connect(
                lambda value: self.tts_volume_value.setText(f"{value}%")
            )
            self.tts_volume.valueChanged.emit(self.tts_volume.value())
            tts_form.addRow("Volume", volume_control)
            layout.addWidget(tts_group)
            feature_group = QtWidgets.QGroupBox("Chat display")
            feature_form = QtWidgets.QFormLayout(feature_group)
            self.show_reading = QtWidgets.QCheckBox("Show pinyin / furigana on hover")
            self.show_reading.setChecked(self._settings.value("show_reading", True, type=bool))
            self.show_reading.toggled.connect(self._set_show_reading)
            feature_form.addRow(self.show_reading)
            self.max_messages = QtWidgets.QSpinBox()
            self.max_messages.setRange(10, 200)
            self.max_messages.setValue(self.config.MAX_CHAT_DISPLAY)
            feature_form.addRow("Maximum chat messages per room", self.max_messages)
            layout.addWidget(feature_group)
            layout.addStretch(1)
            self.translation_toggle.toggled.connect(self._update_translation)
            self.translation_target.currentIndexChanged.connect(self._update_translation)
            self.tts_toggle.toggled.connect(self._set_tts_enabled)
            self.tts_lang.currentIndexChanged.connect(self._set_tts_language)
            self.translation_target.currentIndexChanged.connect(self._set_translation_target)
            self.max_messages.valueChanged.connect(self._set_message_limit)
            self.max_messages.setValue(self._settings.value("max_messages", self.config.MAX_CHAT_DISPLAY, type=int))
            return widget

        def _set_message_limit(self, value):
            self._settings.setValue("max_messages", value)
            self._retain_selected_feed_messages()
            self._refresh_feeds()

        def _apply_ui_language(self):
            language = self._ui_language

            def translate_widget(widget, getter, setter, property_name):
                source = widget.property(property_name)
                current = getter()
                previous = widget.property(property_name + "_rendered")
                if source is None:
                    source = current
                    widget.setProperty(property_name, source)
                elif current != previous:
                    return
                translated = self.i18n.translate(source, language)
                setter(translated)
                widget.setProperty(property_name + "_rendered", translated)

            translate_widget(
                self,
                self.windowTitle,
                self.setWindowTitle,
                "_desktop_source_title",
            )
            for widget in self.findChildren(QtWidgets.QWidget):
                if isinstance(widget, QtWidgets.QGroupBox):
                    translate_widget(
                        widget,
                        widget.title,
                        widget.setTitle,
                        "_desktop_source_text",
                    )
                elif isinstance(widget, (QtWidgets.QLabel, QtWidgets.QAbstractButton)):
                    translate_widget(
                        widget,
                        widget.text,
                        widget.setText,
                        "_desktop_source_text",
                    )
                if isinstance(widget, QtWidgets.QLineEdit):
                    translate_widget(
                        widget,
                        widget.placeholderText,
                        widget.setPlaceholderText,
                        "_desktop_source_placeholder",
                    )
                elif isinstance(widget, (QtWidgets.QPlainTextEdit, QtWidgets.QTextEdit)):
                    translate_widget(
                        widget,
                        widget.placeholderText,
                        widget.setPlaceholderText,
                        "_desktop_source_placeholder",
                    )
                if isinstance(widget, QtWidgets.QTableWidget):
                    headers = widget.property("_desktop_source_headers")
                    current = [
                        widget.horizontalHeaderItem(column).text()
                        if widget.horizontalHeaderItem(column)
                        else ""
                        for column in range(widget.columnCount())
                    ]
                    previous = widget.property("_desktop_rendered_headers")
                    if headers is None:
                        headers = current
                        widget.setProperty("_desktop_source_headers", headers)
                    elif current != previous:
                        continue
                    translated_headers = [
                        self.i18n.translate(header, language) for header in headers
                    ]
                    widget.setHorizontalHeaderLabels(translated_headers)
                    widget.setProperty("_desktop_rendered_headers", translated_headers)

            tab_widgets = [self.centralWidget(), *self.findChildren(QtWidgets.QTabWidget)]
            for tabs in tab_widgets:
                if not isinstance(tabs, QtWidgets.QTabWidget):
                    continue
                source_tabs = tabs.property("_desktop_source_tabs")
                current_tabs = [tabs.tabText(index) for index in range(tabs.count())]
                previous_tabs = tabs.property("_desktop_rendered_tabs")
                if source_tabs is None:
                    source_tabs = current_tabs
                    tabs.setProperty("_desktop_source_tabs", source_tabs)
                if current_tabs == previous_tabs or previous_tabs is None:
                    translated_tabs = [
                        self.i18n.translate(label, language) for label in source_tabs
                    ]
                    for index, label in enumerate(translated_tabs):
                        tabs.setTabText(index, label)
                    tabs.setProperty("_desktop_rendered_tabs", translated_tabs)
            if getattr(self, "_obs_last_state", None) is not None:
                self._render_obs_state(self._obs_last_state)
            self._theme_menu.setTitle(self.i18n.translate("Theme", language))
            for action in self._theme_menu.actions():
                source = action.property("_desktop_source_text")
                if source:
                    action.setText(self.i18n.translate(source, language))
            self._language_menu.setTitle(
                self.i18n.translate("Interface language", language)
            )
            for code, action in self._language_actions.items():
                action.setChecked(code == language)
            self.cookie_browser.setItemText(
                0, self.i18n.translate("Paste / import", language)
            )
            self.hotspot_window.setSuffix(self.i18n.translate(" s window", language))
            self._refresh_overlay_room_selectors()
            self._refresh_transcription_rooms()
            self._refresh_recording_status()
            self.statusBar().showMessage(self.i18n.translate("Ready", language))

        def _set_ui_language(self, language):
            if language not in self.i18n.UI_LANGUAGES:
                return
            self._ui_language = language
            self._settings.setValue("ui_language", language)
            self._settings.sync()
            if self._settings.status() != QtCore.QSettings.Status.NoError:
                self._show_error("Unable to save the interface language setting.")
            self._apply_ui_language()
            self._apply_font_size()
            self._refresh_monitor_cards()

        def _apply_font_size(self):
            system_font = QtGui.QFont(self._base_font)
            system_font.setPointSize(13)
            self.setFont(system_font)
            for widget in self.findChildren(QtWidgets.QWidget):
                widget.setFont(system_font)
            chat_font = QtGui.QFont(system_font)
            chat_font.setPointSize(self._font_size)
            for view in (
                getattr(self, "chat_list", None),
                getattr(self, "paid_list", None),
                getattr(self, "joins_list", None),
            ):
                if view is not None:
                    view.setFont(chat_font)
            if hasattr(self, "chat_list"):
                self._refresh_feeds()
            if hasattr(self, "font_size_value"):
                self.font_size_value.setText(
                    f"{self._font_size} {self.i18n.translate('pt', self._ui_language)}"
                )

        def _set_font_size(self, value):
            self._font_size = min(24, max(8, int(value)))
            self._settings.setValue("desktop_font_size", self._font_size)
            self._apply_font_size()

        def _make_filters_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            row = QtWidgets.QHBoxLayout()
            self.block_input = QtWidgets.QLineEdit()
            self.block_input.setPlaceholderText("Keyword or regular expression")
            row.addWidget(self.block_input, 1)
            add_block = QtWidgets.QPushButton("Block pattern")
            add_block.clicked.connect(lambda: self._add_pattern(False))
            row.addWidget(add_block)
            add_allow = QtWidgets.QPushButton("Allow pattern")
            add_allow.clicked.connect(lambda: self._add_pattern(True))
            row.addWidget(add_allow)
            layout.addLayout(row)
            columns = QtWidgets.QHBoxLayout()
            self.block_patterns_list = QtWidgets.QListWidget()
            self.allow_patterns_list = QtWidgets.QListWidget()
            columns.addWidget(self._feed_group("Blocked patterns", self.block_patterns_list))
            columns.addWidget(self._feed_group("Allowed patterns", self.allow_patterns_list))
            layout.addLayout(columns)
            remove_row = QtWidgets.QHBoxLayout()
            remove_block = QtWidgets.QPushButton("Remove selected block pattern")
            remove_block.clicked.connect(lambda: self._remove_pattern(False))
            remove_allow = QtWidgets.QPushButton("Remove selected allow pattern")
            remove_allow.clicked.connect(lambda: self._remove_pattern(True))
            remove_row.addWidget(remove_block)
            remove_row.addWidget(remove_allow)
            layout.addLayout(remove_row)
            self.blocked_users_list = QtWidgets.QListWidget()
            layout.addWidget(self._feed_group("Blocked users", self.blocked_users_list), 1)
            unblock = QtWidgets.QPushButton("Unblock selected user")
            unblock.clicked.connect(self._unblock_selected)
            layout.addWidget(unblock)
            self._refresh_filters()
            return widget

        def _make_cookies_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            form = QtWidgets.QFormLayout()
            self.cookie_site = QtWidgets.QComboBox()
            self.cookie_site.addItems(["Bilibili", "YouTube", "MissEvan"])
            form.addRow("Site", self.cookie_site)
            self.cookie_browser = QtWidgets.QComboBox()
            self.cookie_browser.addItems(["Paste / import", "Firefox"])
            form.addRow("Cookie source", self.cookie_browser)
            layout.addLayout(form)
            self.cookie_input = QtWidgets.QLineEdit()
            self.cookie_input.setPlaceholderText(
                self.i18n.translate(
                    "Paste a Cookie header or exported cookies JSON (single line)",
                    self._ui_language,
                )
            )
            self.cookie_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal)
            self.cookie_input.setMaxLength(1_000_000)
            self.cookie_input.setClearButtonEnabled(True)
            self.cookie_input.textChanged.connect(self._normalize_cookie_input)
            layout.addWidget(self.cookie_input)
            row = QtWidgets.QHBoxLayout()
            import_button = QtWidgets.QPushButton("Verify and save login")
            import_button.clicked.connect(self._import_cookies)
            read_button = QtWidgets.QPushButton("Read from browser")
            read_button.clicked.connect(self._read_browser_cookies)
            clear_button = QtWidgets.QPushButton("Clear saved login")
            clear_button.clicked.connect(self._clear_login)
            row.addWidget(import_button)
            row.addWidget(read_button)
            row.addWidget(clear_button)
            layout.addLayout(row)
            self.login_status_group = QtWidgets.QGroupBox("Saved login status")
            login_layout = QtWidgets.QHBoxLayout(self.login_status_group)
            self.login_status_labels = {}
            for site in ("YouTube", "Bilibili", "MissEvan"):
                site_status = QtWidgets.QWidget()
                site_layout = QtWidgets.QHBoxLayout(site_status)
                site_layout.setContentsMargins(4, 0, 4, 0)
                site_layout.addWidget(QtWidgets.QLabel(f"{site}:"))
                label = QtWidgets.QLabel()
                self.login_status_labels[site.lower()] = label
                site_layout.addWidget(label)
                login_layout.addWidget(site_status, 1)
            self._refresh_login_status()
            self.cookie_status = QtWidgets.QLabel()
            self.cookie_status.setWordWrap(True)
            layout.addWidget(self.cookie_status)
            return widget

        def _make_obs_tab(self):
            content = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(content)
            self._obs_connected = False
            self._obs_poll_running = False
            self._obs_streaming = False
            self._obs_recording = False
            self._obs_source_snapshot = None
            self._obs_chat_last = None
            self._obs_chat_last_at = 0.0

            self.obs_enabled = QtWidgets.QCheckBox("Connect to OBS")
            self.obs_enabled.setToolTip(
                "Off: the dashboard never contacts OBS. On: stream, recording, scene "
                "and Text source controls appear here once OBS is connected."
            )
            self.obs_enabled.setChecked(
                self._settings.value("obs_enabled", False, type=bool)
            )
            layout.addWidget(self.obs_enabled)
            self.obs_status = QtWidgets.QLabel()
            self.obs_status.setWordWrap(True)
            self.obs_status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(self.obs_status)
            self.obs_status_detail = QtWidgets.QLabel()
            self.obs_status_detail.setWordWrap(True)
            self.obs_status_detail.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(self.obs_status_detail)

            self.obs_setup = QtWidgets.QGroupBox("Setup instructions")
            self.obs_setup.setCheckable(True)
            self.obs_setup.setChecked(False)
            setup_layout = QtWidgets.QVBoxLayout(self.obs_setup)
            self.obs_setup_text = QtWidgets.QLabel()
            self.obs_setup_text.setTextFormat(QtCore.Qt.TextFormat.MarkdownText)
            self.obs_setup_text.setWordWrap(True)
            self.obs_setup_text.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.obs_setup_text.setVisible(False)
            self.obs_setup.toggled.connect(self.obs_setup_text.setVisible)
            setup_layout.addWidget(self.obs_setup_text)
            layout.addWidget(self.obs_setup)

            self.obs_controls = QtWidgets.QWidget()
            controls_layout = QtWidgets.QVBoxLayout(self.obs_controls)
            controls_layout.setContentsMargins(0, 0, 0, 0)
            metrics = QtWidgets.QHBoxLayout()
            self.obs_metrics = {}
            for key, title in (
                ("cpu", "CPU"),
                ("ram", "RAM"),
                ("fps", "FPS"),
                ("dropped", "Dropped Frames"),
            ):
                box = QtWidgets.QGroupBox(title)
                box_layout = QtWidgets.QVBoxLayout(box)
                value = QtWidgets.QLabel("—")
                value.setStyleSheet("font-size: 18pt; font-weight: 600;")
                box_layout.addWidget(value)
                metrics.addWidget(box)
                self.obs_metrics[key] = value
            controls_layout.addLayout(metrics)

            outputs = QtWidgets.QHBoxLayout()
            stream_group = QtWidgets.QGroupBox("🔴 Stream")
            stream_layout = QtWidgets.QVBoxLayout(stream_group)
            self.obs_stream_state = QtWidgets.QLabel()
            self.obs_stream_button = QtWidgets.QPushButton()
            self.obs_stream_button.clicked.connect(self._obs_toggle_stream)
            stream_layout.addWidget(self.obs_stream_state)
            stream_layout.addWidget(self.obs_stream_button)
            outputs.addWidget(stream_group)
            record_group = QtWidgets.QGroupBox("⏺ Recording")
            record_layout = QtWidgets.QVBoxLayout(record_group)
            self.obs_record_state = QtWidgets.QLabel()
            self.obs_record_button = QtWidgets.QPushButton()
            self.obs_record_button.clicked.connect(self._obs_toggle_recording)
            record_layout.addWidget(self.obs_record_state)
            record_layout.addWidget(self.obs_record_button)
            outputs.addWidget(record_group)
            controls_layout.addLayout(outputs)

            scenes_group = QtWidgets.QGroupBox("🎭 Scenes & Sources")
            scenes_layout = QtWidgets.QFormLayout(scenes_group)
            self.obs_scenes = QtWidgets.QComboBox()
            self.obs_scenes.activated.connect(self._obs_switch_scene)
            scenes_layout.addRow("Active scene", self.obs_scenes)
            self.obs_sources = QtWidgets.QListWidget()
            self.obs_sources.setMinimumHeight(140)
            self.obs_sources.itemChanged.connect(self._obs_source_visibility_changed)
            scenes_layout.addRow("Sources in selected scene:", self.obs_sources)
            controls_layout.addWidget(scenes_group)

            text_group = QtWidgets.QGroupBox("📝 OBS Text source")
            text_layout = QtWidgets.QVBoxLayout(text_group)
            self.obs_chat_enabled = QtWidgets.QCheckBox("Send chat to OBS Text source")
            self.obs_chat_enabled.setChecked(
                self._settings.value("obs_chat_enabled", False, type=bool)
            )
            text_layout.addWidget(self.obs_chat_enabled)
            self.obs_chat_names = QtWidgets.QCheckBox("Show usernames")
            self.obs_chat_names.setChecked(
                self._settings.value("obs_chat_names", True, type=bool)
            )
            text_layout.addWidget(self.obs_chat_names)
            self.obs_text_source_row = QtWidgets.QWidget()
            text_source_layout = QtWidgets.QFormLayout(self.obs_text_source_row)
            text_source_layout.setContentsMargins(0, 0, 0, 0)
            self.obs_text_source = QtWidgets.QComboBox()
            text_source_layout.addRow("OBS Text source", self.obs_text_source)
            text_layout.addWidget(self.obs_text_source_row)
            self.obs_text_warning = QtWidgets.QLabel()
            self.obs_text_warning.setWordWrap(True)
            self.obs_text_warning.setStyleSheet("color: #b45309;")
            text_layout.addWidget(self.obs_text_warning)
            controls_layout.addWidget(text_group)
            layout.addWidget(self.obs_controls)

            overlay_group = QtWidgets.QGroupBox("🖥️ Chat Overlay")
            overlay_layout = QtWidgets.QVBoxLayout(overlay_group)
            overlay_intro = QtWidgets.QLabel(
                "Use the overlay URL in OBS as a Browser Source to show a "
                "transparent chat on stream."
            )
            overlay_intro.setWordWrap(True)
            overlay_layout.addWidget(overlay_intro)
            overlay_layout.addWidget(self._make_overlay_tab())
            layout.addWidget(overlay_group)
            layout.addStretch(1)

            self.obs_enabled.toggled.connect(self._set_obs_enabled)
            self.obs_chat_enabled.toggled.connect(self._set_obs_chat_enabled)
            self.obs_chat_names.toggled.connect(self._set_obs_chat_names)
            self.obs_text_source.activated.connect(self._obs_text_source_changed)
            self._obs_timer = QtCore.QTimer(self)
            self._obs_timer.setInterval(3000)
            self._obs_timer.timeout.connect(self._obs_poll)
            self._obs_timer.start()
            self._render_obs_state({"status": {"connected": False}, "error": ("", "")})
            if self.obs_enabled.isChecked():
                QtCore.QTimer.singleShot(0, self._obs_poll)

            scroll_area = QtWidgets.QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll_area.setWidget(content)
            return scroll_area

        def _make_transcription_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            form = QtWidgets.QFormLayout()
            self.transcribe_site = QtWidgets.QComboBox()
            for label, platform in (
                ("YouTube", "youtube"),
                ("Bilibili", "bilibili"),
                ("MissEvan", "missevan"),
            ):
                self.transcribe_site.addItem(label, platform)
            self._persist_widget(self.transcribe_site, "transcribe_site")
            form.addRow("Stream", self.transcribe_site)
            self.transcribe_room = QtWidgets.QComboBox()
            self.transcribe_room.setMinimumWidth(240)
            form.addRow("Room to transcribe", self.transcribe_room)
            self.transcribe_site.currentIndexChanged.connect(
                self._refresh_transcription_rooms
            )
            self.transcribe_room.currentIndexChanged.connect(
                self._transcription_room_changed
            )
            self._refresh_transcription_rooms()
            self.transcribe_model = QtWidgets.QComboBox()
            self.transcribe_model.addItems(["tiny", "base", "small"])
            self.transcribe_model.setCurrentText("base")
            self._persist_widget(self.transcribe_model, "transcribe_model")
            form.addRow("Whisper model", self.transcribe_model)
            self.transcribe_translation = QtWidgets.QCheckBox("Translate transcription")
            self.transcribe_translation.setChecked(True)
            self._persist_widget(self.transcribe_translation, "transcribe_translation")
            form.addRow(self.transcribe_translation)
            layout.addLayout(form)
            row = QtWidgets.QHBoxLayout()
            start = QtWidgets.QPushButton("Start transcription")
            start.clicked.connect(self._start_transcription)
            stop = QtWidgets.QPushButton("Stop transcription")
            stop.clicked.connect(self._stop_transcription)
            row.addWidget(start)
            row.addWidget(stop)
            clear = QtWidgets.QPushButton("Clear all transcripts")
            clear.clicked.connect(self._clear_transcriptions)
            row.addWidget(clear)
            layout.addLayout(row)
            self.transcription_status = QtWidgets.QLabel("Idle")
            layout.addWidget(self.transcription_status)
            self.transcription_output = QtWidgets.QPlainTextEdit()
            self.transcription_output.setReadOnly(True)
            layout.addWidget(self.transcription_output, 1)
            self._transcription_timer = QtCore.QTimer(self)
            self._transcription_timer.timeout.connect(self._poll_transcription)
            self._transcription_timer.start(1000)
            return widget

        def _make_recording_settings(self):
            from src import bili_recorder

            group = QtWidgets.QGroupBox()
            _set_desktop_widget_text(
                group, "Live recording", self._ui_language, self.i18n
            )
            form = QtWidgets.QFormLayout(group)
            intro = QtWidgets.QLabel()
            _set_desktop_widget_text(
                intro,
                "Turn on Record on a YouTube, Bilibili, or MissEvan room card to record its live stream. "
                "YouTube and MissEvan recordings are MKV; Bilibili recordings are FLV. "
                "Recording stops when the room goes offline. FFmpeg is required.",
                self._ui_language,
                self.i18n,
            )
            intro.setWordWrap(True)
            form.addRow(intro)
            folder_row = QtWidgets.QHBoxLayout()
            self.record_folder = QtWidgets.QLineEdit(
                self._settings.value(
                    "record_folder", str(_ROOT / "recordings"), type=str
                )
            )
            self.record_folder.editingFinished.connect(
                lambda: self._save_record_setting(
                    "record_folder", self.record_folder.text().strip()
                )
            )
            folder_row.addWidget(self.record_folder, 1)
            browse = QtWidgets.QPushButton("Browse\u2026")
            browse.clicked.connect(self._browse_record_folder)
            folder_row.addWidget(browse)
            open_folder = QtWidgets.QPushButton("Open folder")
            open_folder.clicked.connect(self._open_record_folder)
            folder_row.addWidget(open_folder)
            form.addRow("Save recordings to", folder_row)
            self.record_quality = QtWidgets.QComboBox()
            for qn, label in bili_recorder.QUALITIES.items():
                self.record_quality.addItem(label, qn)
            saved_qn = self._settings.value("record_quality", 10000, type=int)
            self.record_quality.setCurrentIndex(
                max(0, self.record_quality.findData(saved_qn))
            )
            self.record_quality.setToolTip(
                "Original quality usually needs a Bilibili login; otherwise Bilibili "
                "serves a lower quality."
            )
            self.record_quality.currentIndexChanged.connect(
                lambda: self._save_record_setting(
                    "record_quality", int(self.record_quality.currentData())
                )
            )
            form.addRow("Preferred Bilibili quality", self.record_quality)
            self.record_danmaku = QtWidgets.QCheckBox()
            _set_desktop_widget_text(
                self.record_danmaku,
                "Save Bilibili danmaku, Super Chats and gifts to an XML file next to each video",
                self._ui_language,
                self.i18n,
            )
            self.record_danmaku.setChecked(
                self._settings.value("record_danmaku", True, type=bool)
            )
            self.record_danmaku.toggled.connect(
                lambda checked: self._save_record_setting("record_danmaku", bool(checked))
            )
            form.addRow(self.record_danmaku)
            self._record_timer = QtCore.QTimer(self)
            self._record_timer.timeout.connect(self._refresh_recording_status)
            self._record_timer.start(1000)
            return group

        def _save_record_setting(self, key, value):
            self._settings.setValue(key, value)
            self._settings.sync()
            if self._settings.status() != QtCore.QSettings.Status.NoError:
                self._show_error("Unable to save recording settings.")

        def _browse_record_folder(self):
            folder = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Save recordings to", self.record_folder.text().strip()
            )
            if folder:
                self.record_folder.setText(folder)
                self._save_record_setting("record_folder", folder)

        def _open_record_folder(self):
            folder = Path(self.record_folder.text().strip() or _ROOT / "recordings")
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._show_error(f"Could not create the recording folder: {exc}")
                return
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder)))

        def _set_recording(self, monitor_id, enabled):
            entry = next(
                (t for t in self._monitor_targets if t["id"] == monitor_id), None
            )
            if not enabled:
                self._record_enabled_ids.discard(monitor_id)
                self._stop_recording(monitor_id)
                return
            if not entry:
                self._show_error("Select a configured room before recording.")
                self._refresh_monitor_cards()
                return
            self._record_enabled_ids.add(monitor_id)
            if self._live_states.get(monitor_id, False):
                self._start_recording(monitor_id)

        def _start_recording(self, monitor_id):
            from src import bili_recorder, bilibili, missevan, missevan_recorder

            entry = next(
                (t for t in self._monitor_targets if t["id"] == monitor_id), None
            )
            if not entry or entry["platform"] not in (
                "youtube", "bilibili", "missevan"
            ):
                return
            existing = self._recorders.get(monitor_id)
            if existing and existing.is_running:
                return
            platform = entry["platform"]
            if platform == "youtube":
                from src import youtube, youtube_recorder

                video_state = (
                    self._worker._youtube.get(monitor_id, {})
                    if self._worker else {}
                )
                video_id = str(
                    video_state.get("video_id")
                    or youtube.extract_video_id(entry["target"])
                    or ""
                )
                if not video_id:
                    self._show_error(
                        "The selected YouTube room has no live video to record yet."
                    )
                    self._refresh_monitor_cards()
                    return
                folder = self.record_folder.text().strip() or str(_ROOT / "recordings")
                try:
                    recorder = youtube_recorder.YouTubeRecorder(
                        video_id,
                        folder,
                        source_resolver=lambda: youtube_recorder.resolve_live_source(
                            str(
                                (
                                    self._worker._youtube.get(monitor_id, {}).get("video_id")
                                    if self._worker else ""
                                )
                                or video_id
                            )
                        ),
                        name=self._room_names.get(monitor_id, ""),
                        title=self._room_titles.get(monitor_id, ""),
                    )
                    self._recorders[monitor_id] = recorder
                    recorder.start()
                    self._record_enabled_ids.add(monitor_id)
                    self._refresh_recording_status()
                except Exception as exc:
                    self._show_error(f"Could not start YouTube recording: {exc}")
                    self._refresh_monitor_cards()
                return

            room_id = (
                bilibili.parse_room_id(entry["target"])
                if platform == "bilibili"
                else missevan.parse_room_id(entry["target"])
            )
            if not room_id:
                self._show_error(f"Invalid {platform.title()} room URL or ID.")
                self._refresh_monitor_cards()
                return
            folder = self.record_folder.text().strip() or str(_ROOT / "recordings")
            try:
                if platform == "bilibili":
                    recorder = bili_recorder.BilibiliRecorder(
                        room_id,
                        folder,
                        quality=int(self.record_quality.currentData() or 10000),
                        cookies=self._login_data.get("bilibili") or {},
                        name=self._room_names.get(monitor_id, ""),
                        title=self._room_titles.get(monitor_id, ""),
                        save_danmaku=self.record_danmaku.isChecked(),
                    )
                else:
                    recorder = missevan_recorder.MissEvanRecorder(
                        room_id,
                        folder,
                        source_resolver=lambda: missevan.get_live_audio_url(room_id),
                        name=self._room_names.get(monitor_id, ""),
                        title=self._room_titles.get(monitor_id, ""),
                    )
                self._recorders[monitor_id] = recorder
                recorder.start()
                self._record_enabled_ids.add(monitor_id)
                self._refresh_recording_status()
            except Exception as exc:
                self._show_error(f"Could not start {platform.title()} recording: {exc}")
                self._refresh_monitor_cards()

        def _stop_recording(self, monitor_id):
            recorder = self._recorders.get(monitor_id)
            if recorder:
                recorder.stop()
            self._refresh_recording_status()

        def _recording_status_text(self, monitor_id):
            recorder = self._recorders.get(monitor_id)
            if recorder is None:
                return ""
            state = recorder.snapshot()
            if state["running"]:
                status = state.get("status", "")
                if status == "Recording":
                    text = self.i18n.translate("\u23fa Recording", self._ui_language)
                    if state.get("started_at"):
                        text += " " + _format_record_duration(time.time() - state["started_at"])
                    text += " \u00b7 " + _format_record_size(state.get("total_bytes", 0))
                    if state.get("qn"):
                        text += f" \u00b7 qn {state['qn']}"
                    return text
                return "\u23fa " + self.i18n.translate(status, self._ui_language)
            if state.get("files"):
                return self.i18n.translate(
                    "Last recording: {size}", self._ui_language,
                    size=_format_record_size(state.get("total_bytes", 0)),
                )
            return ""

        def _refresh_recording_status(self):
            for monitor_id, card in self._monitor_cards.items():
                label = card.get("recording")
                if label is None:
                    continue
                recorder = self._recorders.get(monitor_id)
                text = self._recording_status_text(monitor_id)
                if label.text() != text:
                    label.setText(text)
                record_toggle = card.get("record_toggle")
                if record_toggle is not None:
                    is_armed = monitor_id in self._record_enabled_ids
                    if record_toggle.isChecked() != is_armed:
                        record_toggle.blockSignals(True)
                        record_toggle.setChecked(is_armed)
                        record_toggle.blockSignals(False)
                state = recorder.snapshot() if recorder else {}
                tooltip = state.get("error") or state.get("file", "")
                if label.toolTip() != tooltip:
                    label.setToolTip(tooltip)
                label.setVisible(bool(text))

        def _make_analytics_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            self.analytics_summary = QtWidgets.QLabel("Session totals")
            layout.addWidget(self.analytics_summary)
            self.analytics_table = QtWidgets.QTableWidget(0, 4)
            self.analytics_table.setHorizontalHeaderLabels(["Metric", "Platform", "Value", "Details"])
            self.analytics_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
            self.analytics_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            layout.addWidget(self.analytics_table, 1)
            refresh = QtWidgets.QPushButton("Refresh analytics")
            refresh.clicked.connect(self._refresh_analytics)
            self.hotspot_window = QtWidgets.QSpinBox()
            self.hotspot_window.setRange(10, 300)
            self.hotspot_window.setValue(30)
            self._persist_widget(self.hotspot_window, "hotspot_window")
            self.hotspot_window.setSuffix(" s window")
            refresh_row = QtWidgets.QHBoxLayout()
            refresh_row.addWidget(self.hotspot_window)
            refresh_row.addWidget(refresh)
            export_csv = QtWidgets.QPushButton("Export hotspots CSV")
            export_csv.clicked.connect(self._export_hotspots_csv)
            refresh_row.addWidget(export_csv)
            export_edl = QtWidgets.QPushButton("Export DaVinci EDL")
            export_edl.clicked.connect(self._export_hotspots_edl)
            refresh_row.addWidget(export_edl)
            layout.addLayout(refresh_row)
            return widget

        def _make_overlay_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            layout.addWidget(QtWidgets.QLabel("Start the local overlay server for an OBS Browser Source."))
            sites_form = QtWidgets.QFormLayout()
            self.overlay_sites = {}
            self.overlay_rooms = {}
            for platform, title in (
                ("youtube", "YouTube"),
                ("bilibili", "Bilibili"),
                ("missevan", "MissEvan"),
            ):
                check = QtWidgets.QCheckBox(title)
                check.setChecked(
                    self._settings.value(f"overlay_site_{platform}", True, type=bool)
                )
                check.toggled.connect(
                    lambda checked, key=f"overlay_site_{platform}":
                    self._settings.setValue(key, bool(checked))
                )
                room = QtWidgets.QComboBox()
                room.setMinimumWidth(240)
                room.setToolTip(
                    self.i18n.translate(
                        "Monitored {site} room shown in the overlay",
                        self._ui_language,
                        site=title,
                    )
                )
                room.currentIndexChanged.connect(
                    lambda _, key=platform: self._overlay_room_changed(key)
                )
                check.toggled.connect(room.setVisible)
                room.setVisible(check.isChecked())
                self.overlay_sites[platform] = check
                self.overlay_rooms[platform] = room
                sites_form.addRow(check, room)
            layout.addLayout(sites_form)
            self._refresh_overlay_room_selectors()
            counts_form = QtWidgets.QFormLayout()
            self.overlay_count = QtWidgets.QSpinBox()
            self.overlay_count.setRange(1, 50)
            self.overlay_count.setValue(5)
            self._persist_widget(self.overlay_count, "overlay_count")
            counts_form.addRow("Chat messages", self.overlay_count)
            self.overlay_paid_count = QtWidgets.QSpinBox()
            self.overlay_paid_count.setRange(0, 50)
            self.overlay_paid_count.setValue(3)
            self._persist_widget(self.overlay_paid_count, "overlay_paid_count")
            counts_form.addRow("Paid messages", self.overlay_paid_count)
            layout.addLayout(counts_form)
            self.overlay_show_names = QtWidgets.QCheckBox("Show usernames")
            self.overlay_show_names.setChecked(True)
            self._persist_widget(self.overlay_show_names, "overlay_show_names")
            layout.addWidget(self.overlay_show_names)
            self.overlay_translate = QtWidgets.QCheckBox("Add translations to overlay")
            self._persist_widget(self.overlay_translate, "overlay_translate")
            layout.addWidget(self.overlay_translate)
            self.overlay_custom_text = QtWidgets.QLineEdit()
            self.overlay_custom_text.setPlaceholderText("Optional custom overlay message")
            self._persist_widget(self.overlay_custom_text, "overlay_custom_text")
            layout.addWidget(self.overlay_custom_text)
            start = QtWidgets.QPushButton("Start server and copy Browser Source URL")
            start.clicked.connect(self._start_overlay)
            layout.addWidget(start)
            self.overlay_url = QtWidgets.QLineEdit()
            self.overlay_url.setReadOnly(True)
            layout.addWidget(self.overlay_url)
            layout.addStretch(1)
            return widget

        def _make_archive_tab(self):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            row = QtWidgets.QHBoxLayout()
            self.archive_sessions = QtWidgets.QComboBox()
            row.addWidget(self.archive_sessions, 1)
            reload_button = QtWidgets.QPushButton("Reload saved sessions")
            reload_button.clicked.connect(self._load_archive_view)
            row.addWidget(reload_button)
            save_button = QtWidgets.QPushButton("Save current chat")
            save_button.clicked.connect(
                lambda: self._save_archive(refresh_view=True)
            )
            row.addWidget(save_button)
            delete_button = QtWidgets.QPushButton(
                "Delete all saved messages for this channel / room"
            )
            delete_button.clicked.connect(self._delete_saved_session)
            row.addWidget(delete_button)
            layout.addLayout(row)
            self.archive_table = QtWidgets.QTableWidget(0, 4)
            self.archive_table.setHorizontalHeaderLabels(["Time", "Platform", "Author", "Message"])
            self.archive_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
            self.archive_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            layout.addWidget(self.archive_table, 1)
            self.archive_path_label = QtWidgets.QLabel(
                self.i18n.translate("Saved room files: {path}", self._ui_language, path=self._archive.sessions_path)
            )
            layout.addWidget(self.archive_path_label)
            self.archive_sessions.currentIndexChanged.connect(self._show_archive_session)
            return widget

        def _start_monitor(self):
            self._worker = _MonitorWorker(self._login_data, self._monitor_targets)
            self._worker.messages.connect(self._accept_messages)
            self._worker.statuses.connect(self._update_statuses)
            self._worker.failed.connect(self._show_error)
            self._worker.start()

        def _update_monitor_targets(self):
            self._save_monitor_targets()
            if self._worker:
                self._worker.update_targets(self._monitor_targets)
            self.statusBar().showMessage("Monitor targets updated.", 5000)

        def _update_statuses(self, statuses):
            live_channels = []
            viewers_by_platform = defaultdict(int)
            room_names_changed = False
            for monitor_id, card in self._monitor_cards.items():
                entry = next(
                    (target for target in self._monitor_targets if target["id"] == monitor_id),
                    None,
                )
                info = statuses.get(monitor_id, {})
                if not entry:
                    continue
                room_name = str(info.get("room_name") or "").strip()
                if room_name and self._room_names.get(monitor_id) != room_name:
                    self._room_names[monitor_id] = room_name
                    room_names_changed = True
                name = room_name or entry["target"]
                card["title"].setText(f"{entry['platform'].title()} · {name}")
                viewers = info.get("viewers", "")
                live = bool(info.get("live"))
                try:
                    viewers_by_platform[entry["platform"]] += int(viewers or 0)
                except (TypeError, ValueError):
                    pass
                previous = self._live_states.get(monitor_id)
                self._live_states[monitor_id] = live
                if monitor_id == self._transcription_armed_id:
                    if live and previous is not True:
                        self._begin_transcription(entry)
                    elif not live and previous is True and self._transcriber:
                        self._transcriber.stop()
                recording_action = _recording_status_action(
                    previous,
                    live,
                    monitor_id in self._record_enabled_ids,
                )
                if recording_action == "start":
                    self._start_recording(monitor_id)
                elif recording_action == "stop":
                    self._stop_recording(monitor_id)
                room_title = str(info.get("title") or "").strip()
                if room_title:
                    self._room_titles[monitor_id] = room_title
                if previous is False and live and self.notify_live_check.isChecked():
                    self._notify(f"{entry['platform'].title()} is live", name)
                if live:
                    live_channels.append(name)
                detail = f"ID {entry['target']}"
                room_title = str(info.get("title") or "").strip()
                if room_title and room_title != room_name:
                    detail += f" · {room_title}"
                if viewers not in ("", None):
                    detail += self.i18n.translate(
                        " · {count} viewers",
                        self._ui_language,
                        count=viewers,
                    )
                card["detail"].setText(detail)
                connection = info.get("connection", "Connecting")
                _set_desktop_widget_text(
                    card["connection"],
                    connection,
                    self._ui_language,
                    self.i18n,
                )
                card["connection"].setToolTip(info.get("error", ""))
                if connection.startswith("Connected"):
                    color = "#16803c"
                elif connection in ("Connecting", "Waiting for chat", "Waiting for stream", "Reconnecting"):
                    color = "#9a6700"
                elif connection == "Monitoring off":
                    color = "#666666"
                else:
                    color = "#b42318"
                card["connection"].setStyleSheet(f"color: {color}; border: 0;")
            self.live_status.setText(
                "Live: " + (", ".join(live_channels) if live_channels else "No active streams detected")
            )
            if self.config.ANALYTICS_ENABLED:
                self._viewer_samples.append((time.time(), dict(viewers_by_platform)))
                self._viewer_samples = self._viewer_samples[-2000:]
            if room_names_changed:
                self._refresh_chat_room_selectors()
                self._refresh_transcription_rooms()
                self._refresh_archive_session_labels()

        def _append_messages_to_archive(self, messages):
            messages_by_target = defaultdict(list)
            targets_by_id = {}
            for message in messages:
                if message.get("type") == "enter":
                    continue
                entry = _monitored_target_for_message(
                    message, self._monitor_targets
                )
                if entry is None:
                    continue
                messages_by_target[entry["id"]].append({
                    "timestamp": str(message.get("timestamp", "")),
                    "platform": str(message.get("platform", "")).lower(),
                    "author": str(message.get("author", "")),
                    "text": str(message.get("text", "")),
                })
                targets_by_id[entry["id"]] = entry

            errors = []
            for monitor_id, room_messages in messages_by_target.items():
                entry = targets_by_id[monitor_id]
                platform = entry["platform"]
                configured_target = entry["target"]
                if platform == "youtube":
                    channel_id, room_id = configured_target, ""
                else:
                    from src import bilibili, missevan
                    room_id = (
                        bilibili.parse_room_id(configured_target)
                        if platform == "bilibili"
                        else missevan.parse_room_id(configured_target)
                    )
                    channel_id = ""
                identity = channel_id or room_id
                if not identity:
                    errors.append(
                        f"Could not save {platform.title()} messages: enter a valid "
                        "room or channel ID in Stream Monitoring."
                    )
                    continue
                result = self._archive.append_messages(
                    f"{platform}:{identity}",
                    room_messages,
                    platform=platform,
                    room_id=room_id,
                    channel_id=channel_id,
                    room_name=self._room_names.get(monitor_id, ""),
                )
                if not result.get("ok"):
                    errors.append(result["error"])

            if errors:
                self._show_error(" ".join(errors))

        def _accept_messages(self, messages):
            from src import gifts, translate
            from src.tts import is_gift, is_paid, is_emoji_only, strip_emoji, format_announcement

            if self.config.ANALYTICS_ENABLED:
                from src import highlights

            allowed, _blocked = self._filter.filter_messages(messages)
            selected_ids = self._selected_chat_room_ids()
            room_ids = {entry["id"] for entry in self._monitor_targets}
            for message in messages:
                recorder = self._recorders.get(message.get("_monitor_id", ""))
                if (
                    recorder is not None
                    and recorder.is_running
                    and not message.get("history")
                    and callable(getattr(recorder, "add_danmaku", None))
                ):
                    recorder.add_danmaku(message)
            for message in allowed:
                msg = dict(message)
                msg["_arrived"] = time.time()
                self._feed_message_sequence += 1
                msg["_desktop_feed_id"] = str(self._feed_message_sequence)
                selected_room = _message_matches_selected_chat_room(
                    msg, selected_ids, room_ids
                )
                if msg.get("type") == "enter":
                    if selected_room:
                        self._joins.append(msg)
                        self._joins = _limit_messages_per_room(
                            self._joins, self.max_messages.value()
                        )
                    if (
                        selected_room
                        and self._tts_enabled
                        and self.tts_joins.isChecked()
                        and self._is_selected_chat_message(msg)
                    ):
                        rate, volume, lang = self.tts_rate.value(), self._tts_volume_value(), self._tts_language
                        author = msg.get("author", "")
                        generation = self._tts_selection_generation

                        def speak_join_if_current(
                            author=author,
                            rate=rate,
                            volume=volume,
                            lang=lang,
                            message=msg,
                            queued_generation=generation,
                        ):
                            if not self._is_selected_chat_message(
                                message, queued_generation
                            ):
                                return None
                            return self._speak_join(author, rate, volume, lang)

                        self._run_task(
                            speak_join_if_current,
                            lambda audio, message=msg, queued_generation=generation:
                            self._play_audio_bytes(audio)
                            if self._is_selected_chat_message(
                                message, queued_generation
                            )
                            else None,
                        )
                    continue
                if self.config.ANALYTICS_ENABLED:
                    self._activity.append((time.time(), msg))
                    self._hotspot_events.append(
                        highlights.log_entry(msg, is_paid(msg) or is_gift(msg), time.time())
                    )
                if selected_room and self._translate_enabled and msg.get("text"):
                    target, text = self._translate_target, msg["text"]
                    translate.prefetch([text], target)

                    def resolve_translation(text=text, target=target):
                        deadline = time.monotonic() + 8
                        while time.monotonic() < deadline:
                            translated = translate.get_translation(text, target)
                            if translated is not None:
                                return translated
                            time.sleep(0.4)
                        return ""

                    self._run_task(
                        resolve_translation,
                        lambda translated, msg=msg: self._translation_ready(msg, translated),
                    )
                if selected_room:
                    if is_paid(msg) or is_gift(msg):
                        self._paid.append(msg)
                    else:
                        self._messages.append(msg)
                if (
                    not msg.get("history")
                    and self._tts_enabled
                    and self._is_selected_chat_message(msg)
                    and (self.tts_paid.isChecked() or not (is_paid(msg) or is_gift(msg)))
                ):
                    text = msg.get("text", "")
                    if self.tts_skip_emoji.isChecked():
                        text = strip_emoji(text, msg.get("platform", "")) or text
                    if not self.tts_skip_emoji.isChecked() or not is_emoji_only(msg):
                        rate, volume, lang = self.tts_rate.value(), self._tts_volume_value(), self._tts_language
                        paid = is_paid(msg) or is_gift(msg)
                        target = self._translate_target
                        translated_speech = self.tts_translate.isChecked() and self._translate_enabled and not is_gift(msg)
                        skip_name = self.tts_skip_name.isChecked()
                        author = msg.get("author", "")
                        self._queue_chat_speech(
                            text,
                            rate,
                            volume,
                            lang,
                            paid,
                            target,
                            translated_speech,
                            skip_name,
                            author,
                            msg,
                        )
            self._messages = _limit_messages_per_room(
                self._messages, self.max_messages.value()
            )
            self._paid = _limit_messages_per_room(
                self._paid, self.max_messages.value()
            )
            self._refresh_feeds()
            self._sync_obs_chat()
            if allowed:
                self._append_messages_to_archive(allowed)

        def _translation_ready(self, message, translated):
            if translated:
                message["translation"] = translated
                self._refresh_feeds()

        def _queue_chat_speech(
            self,
            text,
            rate,
            volume,
            lang,
            paid,
            target,
            translate_message,
            skip_name,
            author,
            message,
        ):
            generation = self._tts_selection_generation

            def speak_if_current():
                if generation != self._tts_selection_generation:
                    return None
                return self._speak_message(
                    text,
                    rate,
                    volume,
                    lang,
                    paid,
                    target,
                    translate_message,
                    skip_name,
                    author,
                    message,
                )

            def play_if_current(audio):
                if self._is_selected_chat_message(message, generation):
                    self._play_audio_bytes(audio)

            self._run_task(speak_if_current, play_if_current)

        def _speak_message(self, text, rate, volume, lang, paid, target, translate_message, skip_name, author, message):
            from src import translate
            from src.tts import format_announcement, format_message, speak, speak_async

            if translate_message:
                translated = translate.get_translation(text, target)
                if translated:
                    text, lang = translated, target.split("-")[0]
            if paid:
                text = format_announcement(message.get("type", ""), author, text, lang)
            elif not skip_name:
                text = format_message(author, text, lang)
            if self.config.TTS_USE_GTTS:
                return speak(text, rate=rate, volume=volume, lang=lang)
            speak_async(text, rate=rate, volume=volume, lang=lang, priority=paid)
            return None

        def _speak_join(self, author, rate, volume, lang):
            from src.tts import format_join, speak, speak_async
            text = format_join(author, lang)
            if self.config.TTS_USE_GTTS:
                return speak(text, rate=rate, volume=volume, lang=lang)
            speak_async(text, rate=rate, volume=volume, lang=lang)
            return None

        def _tts_volume_value(self):
            return self.tts_volume.value() / 100

        def _play_audio_bytes(self, audio):
            if not audio:
                return
            self._audio_queue.append(bytes(audio))
            if self._audio_player.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.StoppedState:
                self._play_next_audio()

        def _play_next_audio(self):
            if not self._audio_queue:
                return
            self._audio_buffer = QtCore.QBuffer(self)
            self._audio_buffer.setData(QtCore.QByteArray(self._audio_queue.pop(0)))
            self._audio_buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
            self._audio_player.setSourceDevice(self._audio_buffer)
            self._audio_player.play()

        def _audio_status_changed(self, status):
            if status == QtMultimedia.QMediaPlayer.MediaStatus.EndOfMedia:
                if self._audio_buffer:
                    self._audio_buffer.close()
                    self._audio_buffer.deleteLater()
                    self._audio_buffer = None
                self._play_next_audio()

        def _message_visible_in_chat(self, message, selected_ids, room_ids):
            platform = str(message.get("platform", "")).lower()
            return (
                selected_ids.get(platform, "") in room_ids
                and (
                    message.get("_monitor_id") == selected_ids.get(platform, "")
                    if message.get("_monitor_id")
                    else True
                )
                and (
                    self.site_visible[platform].isChecked()
                    if platform in self.site_visible else True
                )
            )

        def _visible_chat_messages(self, feed=None):
            feed = feed or self._active_feed
            room_ids = {entry["id"] for entry in self._monitor_targets}
            selected_ids = {
                platform: selector.currentData() or ""
                for platform, selector in getattr(
                    self, "chat_room_selectors", {}
                ).items()
            }
            feed_messages = {"paid": self._paid, "joins": self._joins}.get(feed, self._messages)
            messages = [
                message
                for message in feed_messages
                if self._message_visible_in_chat(
                    message, selected_ids, room_ids
                )
            ]
            return sorted(messages, key=lambda message: message.get("_arrived", 0))

        def _copy_messages(self, messages):
            if not messages:
                self.statusBar().showMessage(
                    "No chat messages to copy.", 5000
                )
                return
            text = "\n".join(
                _format_message_for_copy(message) for message in messages
            )
            QtWidgets.QApplication.clipboard().setText(text)
            self.statusBar().showMessage(
                f"Copied {len(messages)} chat message(s).", 5000
            )

        def _copy_selected_chat(self, feed=None):
            feed = feed or self._active_feed
            view = self.paid_list if feed == "paid" else self.chat_list
            messages = [
                item.data(QtCore.Qt.ItemDataRole.UserRole)
                for item in view.selectedItems()
            ]
            messages.sort(key=lambda message: message.get("_arrived", 0))
            self._copy_messages(messages)

        def _copy_visible_chat(self, feed=None):
            self._copy_messages(self._visible_chat_messages(feed))

        def _feed_message_clicked(self, feed, item):
            view = self.paid_list if feed == "paid" else self.chat_list
            message = item.data(QtCore.Qt.ItemDataRole.UserRole)
            message_id = message.get("_desktop_feed_id")
            paused, paused_message = _feed_scroll_click_state(
                self._feed_scroll_paused[feed],
                self._feed_paused_messages[feed],
                message_id,
            )
            self._feed_scroll_paused[feed] = paused
            self._feed_paused_messages[feed] = paused_message
            if paused:
                view.setCurrentItem(
                    item,
                    QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect,
                )
            else:
                view.clearSelection()
                view.scrollToBottom()

        def _refresh_feeds(self):
            chat_messages = self._visible_chat_messages("chat")
            paid_messages = self._visible_chat_messages("paid")
            self._render_feed(self.chat_list, chat_messages)
            self._render_feed(self.paid_list, paid_messages)
            self._queue_chat_images(chat_messages + paid_messages)
            self.joins_list.clear()
            for msg in self._visible_chat_messages("joins"):
                item = QtWidgets.QListWidgetItem(
                    f"{_format_chat_timestamp(msg.get('timestamp', ''))}  "
                    f"[{msg.get('platform', '').upper()}]  "
                    f"{msg.get('author', '?')} entered"
                )
                item.setData(QtCore.Qt.ItemDataRole.UserRole, msg)
                self.joins_list.addItem(item)
            self.joins_list.scrollToBottom()

        def _queue_chat_images(self, messages):
            from src import emotes

            urls = set()
            for message in messages:
                message_emotes = message.get("emotes") or {}
                if isinstance(message_emotes, dict):
                    urls.update(
                        safe_url for url in message_emotes.values()
                        if (safe_url := emotes.safe_chat_image_url(url))
                    )
                sticker_url = emotes.safe_chat_image_url(message.get("sticker_url", ""))
                if sticker_url:
                    urls.add(sticker_url)
                membership_icon = emotes.safe_badge_url(message.get("membership_icon", ""))
                if membership_icon:
                    urls.add(membership_icon)
            pending = urls - self._chat_image_cache.keys() - self._chat_images_pending
            if not pending:
                return
            self._chat_images_pending.update(pending)

            def download():
                import requests
                from concurrent.futures import ThreadPoolExecutor

                def fetch(url):
                    try:
                        with requests.get(url, timeout=(5, 10), stream=True) as response:
                            response.raise_for_status()
                            mime = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                            if not mime.startswith("image/"):
                                return url, None
                            image = bytearray()
                            for chunk in response.iter_content(64 * 1024):
                                image.extend(chunk)
                                if len(image) > 2 * 1024 * 1024:
                                    return url, None
                            return url, (mime, bytes(image)) if image else (None)
                    except requests.RequestException:
                        return url, None

                with ThreadPoolExecutor(max_workers=8) as pool:
                    return list(pool.map(fetch, pending))

            def downloaded(results):
                has_images = False
                for url, image in results:
                    self._chat_images_pending.discard(url)
                    self._chat_image_cache[url] = image
                    has_images = has_images or image is not None
                if has_images:
                    self._refresh_feeds()

            self._run_task(download, downloaded)

        def _render_feed(self, view, messages):
            from src import gifts
            from src import emotes
            from src import reading

            feed = "paid" if view is self.paid_list else "chat"
            paused = self._feed_scroll_paused[feed]
            paused_message_id = self._feed_paused_messages[feed]
            cursor_position = QtGui.QCursor.pos()
            cursor_viewport_position = view.viewport().mapFromGlobal(cursor_position)
            hovered_item = view.itemAt(cursor_viewport_position)
            hovered_message_id = (
                hovered_item.data(QtCore.Qt.ItemDataRole.UserRole).get(
                    "_desktop_feed_id"
                )
                if hovered_item is not None
                else None
            )
            selected_indices = _selected_feed_indices(
                messages,
                [{"_desktop_feed_id": paused_message_id}]
                if paused and paused_message_id is not None
                else [],
            )
            scroll_bar = view.verticalScrollBar()
            scroll_position = scroll_bar.value()
            view.clear()
            for msg in messages:
                stamp = _format_chat_timestamp(msg.get("timestamp", ""))
                prefix = f"{stamp}  [{msg.get('platform', '').upper()}]  {msg.get('author', '?')}"
                flags = []
                if msg.get("is_owner"):
                    flags.append("OWNER")
                if msg.get("is_moderator"):
                    flags.append("MOD")
                if msg.get("is_verified"):
                    flags.append("VERIFIED")
                membership_icon = emotes.safe_badge_url(msg.get("membership_icon", ""))
                if msg.get("membership") and not membership_icon:
                    flags.append(str(msg["membership"]))
                membership_badge_markup = ""
                fan_medal_markup = ""
                fan_medal = msg.get("fan_medal")
                if msg.get("platform") == "bilibili" and isinstance(fan_medal, dict):
                    try:
                        medal_level = int(fan_medal.get("level") or 0)
                        medal_color = int(fan_medal.get("color") or 0)
                    except (TypeError, ValueError):
                        medal_level = medal_color = 0
                    if medal_level > 0:
                        medal_name = str(fan_medal.get("name") or "粉丝牌")
                        label = f"{medal_name} Lv.{medal_level}"
                        style = f"color:#{medal_color:06x};" if 0 < medal_color <= 0xFFFFFF else ""
                        fan_medal_markup = (
                            f' <span style="{style}" title="{html.escape(label, quote=True)}">'
                            f'[{html.escape(label)}]</span>'
                        )
                if msg.get("id") in self._thanked_ids:
                    flags.append("THANKED")
                if flags:
                    prefix += f"  ({' · '.join(flags)})"
                if membership_icon:
                    membership_badge = self._chat_image_cache.get(membership_icon)
                    if membership_badge:
                        mime, data = membership_badge
                        encoded = base64.b64encode(data).decode("ascii")
                        membership_badge_markup = (
                            f' <img src="data:{mime};base64,{encoded}" width="20" height="20" '
                            f'alt="{html.escape(str(msg.get("membership", "Member")), quote=True)}" '
                            f'title="{html.escape(str(msg.get("membership", "Member")), quote=True)}">'
                        )
                    elif msg.get("membership"):
                        prefix += f"  ({html.escape(str(msg['membership']))})"
                message_text = str(msg.get("text", ""))
                if (
                    str(msg.get("platform", "")).lower() == "bilibili"
                    and msg.get("type") == "gift"
                ):
                    message_text = _localize_bilibili_gift_text(
                        message_text, self._ui_language, self.i18n
                    )
                author = str(msg.get("author", "?"))
                reading_tooltip = ""
                if self.show_reading.isChecked():
                    author_reading = reading.with_readings(author)
                    message_reading = reading.with_readings(message_text)
                    if author_reading != author or message_reading != message_text:
                        reading_tooltip = self.i18n.translate(
                            "Username: {name}\nMessage: {message}",
                            self._ui_language,
                            name=author_reading,
                            message=message_reading,
                        )
                message_emotes = msg.get("emotes") or {}
                replacements = {
                    code: emotes.safe_chat_image_url(url)
                    for code, url in message_emotes.items()
                    if isinstance(message_emotes, dict)
                } if isinstance(message_emotes, dict) else {}
                replacements = {code: url for code, url in replacements.items() if code and url}
                if replacements:
                    pattern = re.compile(
                        "(" + "|".join(re.escape(code) for code in sorted(replacements, key=len, reverse=True)) + ")"
                    )
                    parts = pattern.split(message_text)
                else:
                    parts = [message_text]
                rendered_parts = []
                for part in parts:
                    image = self._chat_image_cache.get(replacements.get(part, "")) if part in replacements else None
                    if image:
                        mime, data = image
                        encoded = base64.b64encode(data).decode("ascii")
                        rendered_parts.append(
                            f'<img src="data:{mime};base64,{encoded}" width="26" height="26" '
                            f'alt="{html.escape(part, quote=True)}" title="{html.escape(part, quote=True)}">'
                        )
                    else:
                        rendered_parts.append(_plain_chat_html(part))
                body = "".join(rendered_parts)
                text = f"<b>{html.escape(prefix)}{membership_badge_markup}{fan_medal_markup}</b><br>{body}"
                sticker_url = emotes.safe_chat_image_url(msg.get("sticker_url", ""))
                sticker = self._chat_image_cache.get(sticker_url)
                if sticker:
                    mime, data = sticker
                    encoded = base64.b64encode(data).decode("ascii")
                    text += (
                        f'<br><img src="data:{mime};base64,{encoded}" width="96" height="96" '
                        f'alt="sticker" title="sticker">'
                    )
                if msg.get("translation"):
                    translated_text = str(msg["translation"])
                    rendered_translation = _plain_chat_html(translated_text)
                    text += f"<br>🌐 {rendered_translation}"
                price = gifts.gift_price_label(msg) if msg.get("value") else ""
                if price:
                    text += f"<br>{html.escape(price)}"
                item = QtWidgets.QListWidgetItem()
                item.setData(QtCore.Qt.ItemDataRole.UserRole, msg)
                row = _HoverMessageWidget()
                row_layout = QtWidgets.QVBoxLayout(row)
                row_layout.setContentsMargins(4, 3, 4, 3)
                row_layout.setSpacing(2)
                label = QtWidgets.QLabel()
                label.setFont(view.font())
                label.setTextFormat(QtCore.Qt.TextFormat.RichText)
                label.setWordWrap(True)
                label.setText(text)
                label.setToolTip(reading_tooltip)
                row_layout.addWidget(label)
                row.watch_hover(label)

                platform = str(msg.get("platform", "")).lower()
                is_paid_message = view is self.paid_list
                row._chat_label = label
                for widget in (row, label):
                    widget.setContextMenuPolicy(
                        QtCore.Qt.ContextMenuPolicy.CustomContextMenu
                    )
                    widget.customContextMenuRequested.connect(
                        lambda position, message=msg, source=widget, paid=is_paid_message:
                        self._show_message_actions_menu(
                            message, source.mapToGlobal(position), paid
                        )
                    )
                view.addItem(item)
                view.setItemWidget(item, row)
            self._resize_feed_items(view)
            if paused:
                for index in selected_indices:
                    view.item(index).setSelected(True)
                view.doItemsLayout()
                scroll_bar.setValue(scroll_position)
            else:
                view.scrollToBottom()
            if _reading_tooltip_allowed(view) and hovered_message_id is not None:
                for index in range(view.count()):
                    item = view.item(index)
                    message = item.data(QtCore.Qt.ItemDataRole.UserRole)
                    if message.get("_desktop_feed_id") != hovered_message_id:
                        continue
                    row = view.itemWidget(item)
                    if row is None:
                        break
                    label = row._chat_label
                    if not _reading_tooltip_allowed(label) or not label.rect().contains(
                        label.mapFromGlobal(cursor_position)
                    ):
                        break
                    tooltip = label.toolTip()
                    if tooltip:
                        QtWidgets.QToolTip.showText(
                            cursor_position,
                            tooltip,
                            label,
                        )
                    break

        def _show_message_actions_menu(self, message, position, paid):
            menu = QtWidgets.QMenu(self)
            callbacks = {
                "Block": self._block_selected_message,
                "Read": self._replay_selected_message,
                "Thank": self._thank_selected_message,
                "Mute": self._mute_selected_user,
            }
            for action_name in _message_action_names(
                str(message.get("platform", "")).lower(), paid
            ):
                action = menu.addAction(
                    self.i18n.translate(action_name, self._ui_language)
                )
                callback = callbacks.get(action_name)
                if callback is None:
                    action.triggered.connect(
                        lambda _checked=False, selected=message:
                        self._copy_messages([selected])
                    )
                else:
                    action.triggered.connect(
                        lambda _checked=False, handler=callback, selected=message:
                        handler(message=selected)
                    )
            menu.exec(position)

        def _resize_feed_items(self, view):
            width = max(1, view.viewport().width() - 8)
            for index in range(view.count()):
                item = view.item(index)
                row = view.itemWidget(item)
                if not row:
                    continue
                row.setFixedWidth(width)
                label = row._chat_label
                label.setFixedWidth(max(1, width - 8))
                row.adjustSize()
                item.setSizeHint(row.sizeHint())

        def _set_show_reading(self, enabled):
            self._settings.setValue("show_reading", enabled)
            self._refresh_feeds()

        def _send_message(self):
            text = self.send_input.text().strip()
            targets = [site for site, check in self.send_targets.items() if check.isChecked()]
            if not text:
                return
            self.send_input.clear()
            self._send_text(text, targets)

        def _send_text(self, text, targets):
            from src import bilibili, missevan, youtube

            selected_ids = {
                platform: str(
                    selector.currentData() or ""
                )
                for platform, selector in self.chat_room_selectors.items()
            }
            destinations = _selected_send_destinations(
                targets, selected_ids, self._monitor_targets
            )
            worker_states = self._worker._youtube if self._worker else {}

            def send():
                result = {}
                with self._login_context():
                    for entry in destinations:
                        site = entry["platform"]
                        monitor_id = entry["id"]
                        label = f"{site.title()} ({entry['target']})"
                        try:
                            if site == "youtube":
                                state = worker_states.get(monitor_id, {})
                                chat_id = state.get("chat_id", "")
                                video_id = state.get("video_id", "")
                                result[label] = (
                                    youtube.send_chat(chat_id, video_id, text)
                                    if chat_id else (False, "No active YouTube live chat.")
                                )
                            elif site == "bilibili":
                                result[label] = bilibili.send_danmaku(
                                    bilibili.parse_room_id(entry["target"]),
                                    text,
                                )
                            elif site == "missevan":
                                result[label] = missevan.send_message(
                                    missevan.parse_room_id(entry["target"]),
                                    text,
                                )
                        except Exception as exc:
                            result[label] = (False, str(exc))
                    for site in targets:
                        if not any(entry["platform"] == site for entry in destinations):
                            result[site.title()] = (
                                False,
                                "Select an enabled room for this site in Chat rooms.",
                            )
                return result
            self._run_task(send, self._send_finished)

        def _send_finished(self, result):
            if isinstance(result, dict):
                lines = [f"{site}: {'sent' if ok else 'failed'} {detail}" for site, (ok, detail) in result.items()]
                self.statusBar().showMessage(" · ".join(lines), 10000)

        def _selected_message(self, feed=None, message=None):
            if message is not None:
                return message
            feed = feed or self._active_feed
            view = self.paid_list if feed == "paid" else self.chat_list
            item = view.currentItem()
            return item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None

        def _block_selected_message(self, feed=None, message=None):
            msg = self._selected_message(feed, message)
            if not msg:
                self._show_error("Select a message first.")
                return
            author_id = str(msg.get("author_id", ""))
            if author_id and author_id != "0":
                self._filter.block_user(author_id, name=msg.get("author", ""), platform=msg.get("platform", ""))
            else:
                self._filter.block_name(msg.get("author", ""))
            self._refresh_filters()
            self._messages = [message for message in self._messages if self._filter.check(message).allowed]
            self._paid = [message for message in self._paid if self._filter.check(message).allowed]
            self._refresh_feeds()
            self.statusBar().showMessage(f"Blocked {msg.get('author', 'user')}.", 5000)

        def _mute_selected_user(self, feed=None, message=None):
            msg = self._selected_message(feed, message)
            if not msg or msg.get("platform") != "bilibili":
                self._show_error("Select a Bilibili message first.")
                return
            if not str(msg.get("author_id", "")).isdigit() or str(msg.get("author_id")) == "0":
                self._show_error("This Bilibili message does not expose a muteable user ID.")
                return
            confirm = QtWidgets.QMessageBox.question(
                self,
                "Mute viewer in Bilibili",
                f"Mute {msg.get('author', 'this viewer')} in the active Bilibili room?",
            )
            if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            room_id = str(
                msg.get("room_id") or self.target_inputs["bilibili"].text().strip()
            )
            from src import bilibili
            self._run_task(
                lambda: self._with_login(
                    lambda: bilibili.block_user(
                        bilibili.parse_room_id(room_id), int(msg["author_id"])
                    )
                ),
                lambda result: self._show_error(
                    result[1] if not result[0] else f"Muted {msg.get('author', 'viewer')} in Bilibili."
                ),
            )

        def _replay_selected_message(self, feed=None, message=None):
            msg = self._selected_message(feed, message)
            if not msg or not msg.get("text"):
                self._show_error("Select a message with text first.")
                return
            from src.tts import speak_async
            lang = self._tts_language
            text = msg.get("translation") or msg["text"]
            rate, volume = self.tts_rate.value(), self._tts_volume_value()
            skip_name = self.tts_skip_name.isChecked()
            author = msg.get("author", "")
            if not skip_name:
                from src.tts import format_message
                text = format_message(author, text, lang)
            self._run_task(
                lambda: self._speak_message(
                    text, rate, volume, lang, False, self._translate_target,
                    False, True, author, msg,
                ),
                self._play_audio_bytes,
            )

        def _thank_selected_message(self, feed=None, message=None):
            msg = self._selected_message(feed, message)
            if not msg:
                self._show_error("Select a gift or paid message first.")
                return
            msg_id = str(msg.get("id", ""))
            if msg_id in self._thanked_ids:
                self._thanked_ids.remove(msg_id)
            else:
                self._thanked_ids.add(msg_id)
            self._settings.setValue("thanked_ids", sorted(self._thanked_ids))
            self._refresh_feeds()
            self.statusBar().showMessage(f"Marked {msg.get('author', 'message')} as thanked.", 5000)

        def _show_emotes(self):
            from src import bilibili, missevan

            translate = lambda text, **kwargs: self.i18n.translate(
                text, self._ui_language, **kwargs
            )
            sites = QtWidgets.QDialog(self)
            sites.setWindowTitle(translate("Room emotes and stickers"))
            sites.resize(900, 760)
            layout = QtWidgets.QVBoxLayout(sites)
            site = QtWidgets.QComboBox()
            site.addItems(["YouTube channel stamps", "Bilibili", "MissEvan", "MissEvan kaomoji"])
            layout.addWidget(site)
            search_row = QtWidgets.QHBoxLayout()
            search = QtWidgets.QLineEdit()
            search.setPlaceholderText(translate("Search emotes and stickers"))
            search_row.addWidget(search, 1)
            refresh_button = QtWidgets.QPushButton(translate("Refresh"))
            search_row.addWidget(refresh_button)
            layout.addLayout(search_row)
            status = QtWidgets.QLabel(translate("Choose a site to load its available emotes."))
            status.setWordWrap(True)
            layout.addWidget(status)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            sections_widget = QtWidgets.QWidget()
            sections_layout = QtWidgets.QVBoxLayout(sections_widget)
            sections_layout.setContentsMargins(4, 4, 4, 4)
            sections_layout.setSpacing(8)
            sections_layout.addStretch(1)
            scroll.setWidget(sections_widget)
            layout.addWidget(scroll, 1)
            close_button = QtWidgets.QPushButton(translate("Close"))
            close_button.clicked.connect(sites.reject)
            layout.addWidget(close_button)
            groups = []
            active_room = ""
            thumbnail_generation = 0
            load_generation = 0
            login_fingerprint = hashlib.sha256(
                json.dumps(self._login_data, sort_keys=True).encode("utf-8")
            ).hexdigest()

            def cache_key(site_name, identity):
                value = f"{site_name}\0{identity}\0{login_fingerprint}"
                return hashlib.sha256(value.encode("utf-8")).hexdigest()

            def group_state_key(site_name, identity, group_name, group_identity):
                value = (
                    f"{site_name}\0{identity}\0{group_name}\0{group_identity}"
                )
                return "emote_group_collapsed/" + hashlib.sha256(
                    value.encode("utf-8")
                ).hexdigest()

            def clear_sections():
                nonlocal thumbnail_generation
                thumbnail_generation += 1
                groups.clear()
                while sections_layout.count():
                    item = sections_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                sections_layout.addStretch(1)

            def reorder_groups():
                for group in groups:
                    sections_layout.removeWidget(group["header"])
                    sections_layout.removeWidget(group["body"])
                ordered_groups = sorted(
                    groups, key=lambda group: not group["expanded"]
                )
                for index, group in enumerate(ordered_groups):
                    sections_layout.insertWidget(index * 2, group["header"])
                    sections_layout.insertWidget(index * 2 + 1, group["body"])

            def add_group(name, entries):
                if not entries:
                    return
                header = QtWidgets.QToolButton()
                header.setText(f"{name} ({len(entries)})")
                header.setCheckable(True)
                group_identity = next(
                    (
                        str(entry[key])
                        for entry in entries
                        for key in ("_package_id", "unique", "id", "code")
                        if entry.get(key)
                    ),
                    name,
                )
                state_key = group_state_key(
                    site.currentText(), active_room, name, group_identity
                )
                expanded = not self._settings.value(
                    state_key, False, type=bool
                )
                header.setChecked(expanded)
                header.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                header.setArrowType(
                    QtCore.Qt.ArrowType.DownArrow
                    if expanded else QtCore.Qt.ArrowType.RightArrow
                )
                header.setStyleSheet(
                    "QToolButton { text-align: left; font-weight: 600; padding: 6px; "
                    "border: 1px solid #168bd2; border-radius: 4px; }"
                )
                grid = QtWidgets.QListWidget()
                grid.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
                grid.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
                grid.setMovement(QtWidgets.QListView.Movement.Static)
                grid.setWrapping(True)
                grid.setWordWrap(True)
                grid.setUniformItemSizes(True)
                grid.setIconSize(QtCore.QSize(72, 72))
                grid.setGridSize(QtCore.QSize(132, 116))
                columns = max(1, (scroll.viewport().width() - 24) // 132)
                rows = (len(entries) + columns - 1) // columns
                grid.setMinimumHeight(max(132, rows * 116 + 16))
                grid.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                grid.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                for entry in entries:
                    label = str(
                        entry.get("name") or entry.get("emoji") or entry.get("description")
                        or entry.get("code") or entry.get("sticker_id") or entry.get("id") or "Emote"
                    )
                    if entry.get("code"):
                        label += f"  {entry['code']}"
                    if entry.get("locked"):
                        label += " (locked)"
                    item = QtWidgets.QListWidgetItem(label)
                    item.setToolTip(str(entry.get("hint") or label))
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
                    grid.addItem(item)
                body = QtWidgets.QWidget()
                body_layout = QtWidgets.QVBoxLayout(body)
                body_layout.setContentsMargins(0, 0, 0, 0)
                body_layout.addWidget(grid)
                group = {
                    "name": name,
                    "header": header,
                    "body": body,
                    "grid": grid,
                    "entries": entries,
                    "expanded": expanded,
                    "thumbnails_requested": False,
                }
                groups.append(group)
                reorder_groups()

                def set_expanded(
                    expanded, group=group, header=header, body=body,
                    state_key=state_key,
                ):
                    group["expanded"] = expanded
                    body.setVisible(expanded)
                    header.setArrowType(
                        QtCore.Qt.ArrowType.DownArrow if expanded
                        else QtCore.Qt.ArrowType.RightArrow
                    )
                    reorder_groups()
                    if expanded:
                        load_thumbnails(group)
                    self._settings.setValue(state_key, not expanded)
                    self._settings.sync()
                    if self._settings.status() != QtCore.QSettings.Status.NoError:
                        self._show_error(
                            "Unable to save emote group expansion settings."
                        )

                header.toggled.connect(set_expanded)
                body.setVisible(expanded)
                grid.itemClicked.connect(
                    lambda item: use_item(item.data(QtCore.Qt.ItemDataRole.UserRole))
                )
                if expanded:
                    load_thumbnails(group)

            def load_thumbnails(group):
                if group["thumbnails_requested"]:
                    return
                group["thumbnails_requested"] = True
                generation = thumbnail_generation
                from src import emotes

                requests_for_images = []
                for index, entry in enumerate(group["entries"]):
                    url = (
                        entry.get("url") or entry.get("image_url") or entry.get("sticker_url")
                        or entry.get("icon_url") or entry.get("image") or ""
                    )
                    url = emotes.safe_chat_image_url(url)
                    if url:
                        requests_for_images.append((index, url))
                if not requests_for_images:
                    return

                bridge = _EmoteImageBridge(sites)
                group["image_bridge"] = bridge
                progress = {"loaded": 0, "failed": 0, "cache_error": ""}

                def is_current():
                    return generation == thumbnail_generation

                def image_loaded(result):
                    if not is_current():
                        return
                    index, data, cache_error = result
                    if cache_error and not progress["cache_error"]:
                        progress["cache_error"] = cache_error
                    if not data or index >= group["grid"].count():
                        progress["failed"] += 1
                        return
                    pixmap = QtGui.QPixmap()
                    if pixmap.loadFromData(data):
                        group["grid"].item(index).setIcon(QtGui.QIcon(pixmap.scaled(
                            64, 64,
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                            QtCore.Qt.TransformationMode.SmoothTransformation,
                        )))
                        progress["loaded"] += 1
                    else:
                        progress["failed"] += 1

                def thumbnails_finished():
                    if not is_current():
                        return
                    if progress["failed"]:
                        status.setText(
                            f"Loaded {progress['loaded']} image previews; "
                            f"{progress['failed']} could not be loaded."
                        )
                    if progress["cache_error"]:
                        status.setText(
                            f"{status.text()} {translate('Emote cache could not be written: {error}', error=progress['cache_error'])}"
                        )

                bridge.loaded.connect(image_loaded)
                bridge.finished.connect(thumbnails_finished)
                _submit_emote_image_loads(
                    self._emote_image_pool,
                    requests_for_images,
                    self._emote_cache,
                    bridge.loaded.emit,
                    bridge.finished.emit,
                    lambda: not is_current(),
                )

            def filter_items(*_):
                query = search.text().strip().casefold()
                visible = 0
                for group in groups:
                    matches = 0
                    for index in range(group["grid"].count()):
                        item = group["grid"].item(index)
                        matched = not query or query in item.text().casefold()
                        item.setHidden(not matched)
                        matches += int(matched)
                    group["header"].setVisible(matches > 0 or not query)
                    if query and matches:
                        group["header"].setChecked(True)
                    visible += matches
                if query and not visible:
                    status.setText(translate("No emotes or stickers match your search."))
                elif query:
                    status.setText(translate(
                        "{count} matching emotes or stickers.", count=visible
                    ))
                elif groups:
                    status.setText(
                        f"{sum(group['grid'].count() for group in groups)} "
                        f"emotes or stickers in {len(groups)} packs."
                    )

            def load():
                nonlocal active_room, load_generation
                nonlocal thumbnail_generation
                load_generation += 1
                request_generation = load_generation
                thumbnail_generation += 1
                clear_sections()
                search.clear()
                selected_site = site.currentText()
                if selected_site == "YouTube channel stamps":
                    youtube_target = next(
                        (entry for entry in self._channels_for_platform("youtube", enabled_only=True)),
                        None,
                    )
                    youtube_state = (
                        self._worker._youtube.get(youtube_target["id"], {})
                        if self._worker and youtube_target else {}
                    )
                    video_id = youtube_state.get("video_id", "")
                    if not video_id:
                        status.setText("Connect a YouTube live stream in Stream Monitoring first.")
                        return
                    active_room = video_id
                    key = cache_key("youtube", video_id)
                    cached_stamps, cache_read_error = self._emote_cache.get(key)
                    cache_displayed = False

                    def fetch_youtube_stamps():
                        from src import youtube_web
                        with self._login_context():
                            stamps = youtube_web.channel_emojis(video_id, fetch=True)
                        cache_error = (
                            self._emote_cache.set(key, stamps) if stamps else ""
                        )
                        return {"stamps": stamps, "cache_error": cache_error}

                    def youtube_stamps_loaded(result, from_cache=False):
                        nonlocal cache_displayed
                        if request_generation != load_generation:
                            return
                        if from_cache:
                            cache_displayed = True
                        elif cache_displayed:
                            clear_sections()
                        stamps = result if from_cache else result["stamps"]
                        entries = [{**stamp, "kind": "youtube"} for stamp in stamps]
                        if not entries:
                            status.setText("No channel stamps found. Log in to YouTube or wait for stamps to appear in chat.")
                        else:
                            add_group("Channel stamps", entries)
                            status.setText(
                                f"{len(entries)} YouTube channel stamps. Click one to add it to the message box."
                            )
                        cache_error = (
                            cache_read_error if from_cache
                            else result.get("cache_error", "")
                        )
                        if from_cache:
                            status.setText(
                                f"{status.text()} {translate('Using cached emotes.')}"
                            )
                        if cache_error:
                            status.setText(
                                f"{status.text()} {translate('Emote cache could not be read: {error}', error=cache_error) if from_cache else translate('Emote cache could not be written: {error}', error=cache_error)}"
                            )

                    if isinstance(cached_stamps, list):
                        youtube_stamps_loaded(cached_stamps, from_cache=True)
                    elif cache_read_error:
                        status.setText(
                            translate(
                                "Emote cache could not be read: {error}",
                                error=cache_read_error,
                            )
                        )
                    self._run_task(fetch_youtube_stamps, youtube_stamps_loaded)
                    return

                platform = "bilibili" if selected_site == "Bilibili" else "missevan"
                selector = self.chat_room_selectors.get(platform)
                target = _selected_monitor_target(
                    platform,
                    str(selector.currentData() or "") if selector else "",
                    self._monitor_targets,
                ).strip()
                room_id = (
                    bilibili.parse_room_id(target)
                    if platform == "bilibili"
                    else missevan.parse_room_id(target)
                )
                active_room = room_id
                if selected_site.endswith("kaomoji"):
                    entries = [{"name": face, "value": face} for face in missevan.preset_kaomoji()]
                    add_group("Presets", entries)
                    status.setText("Click a preset to add it to the message composer.")
                    return
                if not room_id:
                    status.setText(f"Enter a valid {selected_site} room in Stream Monitoring first.")
                    return
                key = cache_key(platform, room_id)
                cached_result, cache_read_error = self._emote_cache.get(key)
                cache_displayed = False

                def fetch():
                    with self._login_context():
                        if selected_site == "Bilibili":
                            packs, error = bilibili.get_emoticons(room_id)
                            result = {"bilibili_packs": packs, "error": error}
                        else:
                            packages, error = missevan.get_sticker_tabs(room_id)
                            all_stickers = []
                            if packages:
                                from concurrent.futures import ThreadPoolExecutor

                                def fetch_package(package):
                                    package_id = package.get("package_id") or package.get("id")
                                    if not package_id:
                                        return [], "MissEvan returned a sticker package without an ID."
                                    with self._login_context():
                                        stickers, package_error = missevan.get_stickers(
                                            room_id, int(package_id)
                                        )
                                    package_name = str(
                                        package.get("name") or package.get("package_name")
                                        or package.get("package_id") or package.get("id")
                                        or "Sticker pack"
                                    )
                                    return [
                                        {**sticker, "_package_id": int(package_id), "_pack": package_name}
                                        for sticker in stickers
                                    ], package_error

                                with ThreadPoolExecutor(max_workers=4) as pool:
                                    results = list(pool.map(fetch_package, packages))
                                for stickers, package_error in results:
                                    all_stickers.extend(stickers)
                                    if package_error and not error:
                                        error = package_error
                            result = {
                                "packages": packages,
                                "error": error,
                                "stickers": all_stickers,
                            }
                    cache_error = (
                        self._emote_cache.set(key, result)
                        if not result.get("error") else ""
                    )
                    result["cache_error"] = cache_error
                    return result

                def loaded(result, from_cache=False):
                    nonlocal cache_displayed
                    if request_generation != load_generation:
                        return
                    error = result["error"]
                    if from_cache:
                        cache_displayed = True
                    elif cache_displayed and error:
                        status.setText(
                            f"{translate('Using cached emotes.')} {error}"
                        )
                        return
                    elif not from_cache and cache_displayed:
                        payload_key = (
                            "bilibili_packs" if selected_site == "Bilibili"
                            else "stickers"
                        )
                        if (
                            isinstance(cached_result, dict)
                            and result.get(payload_key) == cached_result.get(payload_key)
                        ):
                            cache_error = result.get("cache_error", "")
                            if cache_error:
                                status.setText(
                                    f"{status.text()} "
                                    + translate(
                                        "Emote cache could not be written: {error}",
                                        error=cache_error,
                                    )
                                )
                            return
                        clear_sections()
                    if from_cache and error:
                        status.setText(error)
                    if error:
                        if not from_cache:
                            status.setText(error)
                    if selected_site == "Bilibili":
                        packs = result["bilibili_packs"]
                        count = 0
                        for group in packs:
                            if not isinstance(group, dict):
                                continue
                            entries = [
                                {**emote, "_room_id": room_id, "kind": "bilibili"}
                                for emote in group.get("emotes", [])
                            ]
                            count += len(entries)
                            add_group(str(group.get("name") or "Emotes"), entries)
                        if not count and not error:
                            status.setText("This room has no emotes you can send.")
                    else:
                        stickers = result["stickers"]
                        stickers_by_pack = defaultdict(list)
                        for sticker in stickers:
                            stickers_by_pack[sticker["_pack"]].append(sticker)
                        for pack_name, entries in stickers_by_pack.items():
                            add_group(pack_name, entries)
                        if not stickers and not error:
                            status.setText("This room has no sticker packages.")
                    if groups:
                        filter_items()
                        summary = (
                            f"{sum(group['grid'].count() for group in groups)} "
                            f"emotes or stickers in {len(groups)} packs. "
                            "Click an item to use it; click a pack name to collapse it."
                        )
                        extra = (
                            f" {translate('Using cached emotes.')}"
                            if from_cache else ""
                        )
                        cache_error = (
                            cache_read_error if from_cache
                            else result.get("cache_error", "")
                        )
                        if cache_error:
                            extra += " " + translate(
                                "Emote cache could not be read: {error}"
                                if from_cache else "Emote cache could not be written: {error}",
                                error=cache_error,
                            )
                        status.setText(
                            f"{summary}{extra} {error}" if error
                            else f"{summary}{extra}"
                        )
                    else:
                        cache_error = (
                            cache_read_error if from_cache
                            else result.get("cache_error", "")
                        )
                        if cache_error:
                            status.setText(
                                f"{status.text()} "
                                + translate(
                                    "Emote cache could not be read: {error}"
                                    if from_cache else "Emote cache could not be written: {error}",
                                    error=cache_error,
                                )
                            )

                if isinstance(cached_result, dict) and (
                    "bilibili_packs" in cached_result
                    if selected_site == "Bilibili"
                    else "stickers" in cached_result
                ):
                    loaded(cached_result, from_cache=True)
                elif cache_read_error:
                    status.setText(
                        translate(
                            "Emote cache could not be read: {error}",
                            error=cache_read_error,
                        )
                    )
                self._run_task(fetch, loaded)

            def use_item(item):
                if not isinstance(item, dict):
                    return
                if item.get("locked"):
                    status.setText(item.get("hint") or "This emote or sticker is locked for this account.")
                    return
                selected_site = site.currentText()
                room_id = item.get("_room_id") or active_room
                if item.get("value"):
                    self.send_input.insert(item["value"])
                    sites.accept()
                elif item.get("kind") == "youtube":
                    self.send_targets["youtube"].setChecked(True)
                    self.send_input.insert(item.get("code", ""))
                    sites.accept()
                elif item.get("kind") == "bilibili":
                    unique = item["unique"]
                    self._run_task(
                        lambda: self._with_login(
                            lambda: bilibili.send_emoticon(room_id, unique)
                        ),
                        lambda result: self._show_error(
                            result[1] if not result[0] else "Bilibili emote sent."
                        ),
                    )
                elif selected_site == "MissEvan":
                    sticker_id = item.get("sticker_id") or item.get("id")
                    package_id = item.get("_package_id")
                    if not sticker_id or not package_id:
                        self._show_error("MissEvan returned a sticker without an ID.")
                        return
                    self._run_task(
                        lambda: self._with_login(
                            lambda: missevan.send_sticker(room_id, int(package_id), int(sticker_id))
                        ),
                        lambda result: self._show_error(
                            result[1] if not result[0] else "MissEvan sticker sent."
                        ),
                    )
                sites.accept()

            def cancel_thumbnails(*_):
                nonlocal thumbnail_generation
                thumbnail_generation += 1

            search.textChanged.connect(filter_items)
            refresh_button.clicked.connect(load)
            sites.finished.connect(cancel_thumbnails)
            room_targets = {"Bilibili": "bilibili", "MissEvan": "missevan"}
            preferred_site = next(
                (
                    label for label, target in room_targets.items()
                    if self.send_targets[target].isChecked()
                    and self.target_inputs[target].text().strip()
                ),
                "YouTube channel stamps",
            )
            preferred_index = site.findText(preferred_site)
            if preferred_index >= 0:
                site.setCurrentIndex(preferred_index)
            site.currentIndexChanged.connect(load)
            load()
            sites.exec()

        def _with_login(self, function):
            with self._login_context():
                return function()

        def _run_task(self, function, callback=None):
            bridge = _TaskBridge(self)
            self._task_bridges = getattr(self, "_task_bridges", [])
            self._task_bridges.append(bridge)
            def completed(future):
                try:
                    value, error = future.result(), None
                except Exception as exc:
                    value, error = None, exc
                bridge.finished.emit(value, error)
            bridge.finished.connect(lambda value, error: self._task_finished(bridge, value, error, callback))
            self._executor.submit(function).add_done_callback(completed)

        def _task_finished(self, bridge, value, error, callback):
            if bridge in self._task_bridges:
                self._task_bridges.remove(bridge)
            if error:
                self._show_error(f"{type(error).__name__}: {error}")
            elif callback:
                callback(value)

        def _show_error(self, message):
            self.statusBar().showMessage(str(message), 12000)

        def _update_translation(self, *_):
            self._translate_enabled = self.translation_toggle.isChecked()
            self._translate_target = self.translation_target.currentData()
            self._settings.setValue("translate_enabled", self._translate_enabled)
            self._settings.setValue("translate_target", self._translate_target)

        def _set_tts_enabled(self, enabled):
            self._tts_enabled = enabled
            self._settings.setValue("tts_enabled", enabled)

        def _set_tts_language(self, *_):
            self._tts_language = self.tts_lang.currentData()
            self._settings.setValue("tts_language", self._tts_language)

        def _set_translation_target(self, *_):
            self._translate_target = self.translation_target.currentData()
            self._update_translation()

        def _set_notify_live(self, enabled):
            self._notify_live = enabled
            self._settings.setValue("notify_live", enabled)

        def _notify(self, title, detail):
            if not hasattr(self, "_tray"):
                self._tray = QtWidgets.QSystemTrayIcon(
                    self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon), self
                )
                self._tray.setToolTip("Streaming Dashboard")
                self._tray.show()
            self._tray.showMessage(title, detail or "The stream has started.", QtWidgets.QSystemTrayIcon.MessageIcon.Information, 10000)

        def _stop_speech(self, clear):
            from src.tts import stop_speaking
            dropped = stop_speaking(clear=clear)
            if self.config.TTS_USE_GTTS:
                if clear:
                    self._audio_queue.clear()
                if hasattr(self, "_audio_player"):
                    self._audio_player.stop()
                    if self._audio_buffer:
                        self._audio_buffer.close()
                        self._audio_buffer.deleteLater()
                        self._audio_buffer = None
                    if not clear:
                        self._play_next_audio()
            self.statusBar().showMessage(
                f"Speech stopped; {dropped} queued item(s) removed." if clear else "Skipped current speech.",
                5000,
            )

        def _add_pattern(self, allow):
            pattern = self.block_input.text().strip()
            if not pattern:
                return
            try:
                (self._filter.add_allow_pattern if allow else self._filter.add_block_pattern)(pattern)
            except re.error as exc:
                self._show_error(f"Invalid regular expression: {exc}")
                return
            self.block_input.clear()
            self._refresh_filters()

        def _remove_pattern(self, allow):
            view = self.allow_patterns_list if allow else self.block_patterns_list
            item = view.currentItem()
            if item:
                (self._filter.remove_allow_pattern if allow else self._filter.remove_block_pattern)(item.text())
                self._refresh_filters()

        def _refresh_filters(self):
            self.block_patterns_list.clear()
            self.block_patterns_list.addItems(self._filter.block_patterns)
            self.allow_patterns_list.clear()
            self.allow_patterns_list.addItems(self._filter.allow_patterns)
            self.blocked_users_list.clear()
            self.blocked_users_list.addItems(
                [f"{key} — {name}" if name else key for key, name in self._filter.blocked_users.items()]
                + self._filter.blocked_names
            )

        def _unblock_selected(self):
            item = self.blocked_users_list.currentItem()
            if not item:
                return
            key = item.text().split(" — ", 1)[0]
            if key in self._filter.blocked_users:
                self._filter.unblock_user(key)
            else:
                self._filter.unblock_name(key)
            self._refresh_filters()

        def _import_cookies(self):
            from src import browser_cookies as bc, missevan, user_login, youtube_web
            site = self.cookie_site.currentText()
            raw = self.cookie_input.text()
            try:
                cookies = bc.parse_cookie_text(raw, bc.SITES[site])
                if not cookies:
                    raise ValueError("No cookies were found.")
                with self._login_context():
                    if site == "Bilibili":
                        if not cookies.get("SESSDATA"):
                            raise ValueError("Bilibili cookies must include SESSDATA.")
                        result = bc.verify_bilibili_login(cookies)
                        if result.get("error") or not result.get("is_login"):
                            raise ValueError(result.get("error") or "Bilibili rejected these cookies.")
                        bc.save_bilibili_credentials(cookies)
                        name = result.get("uname", "")
                    elif site == "MissEvan":
                        result = missevan.verify_login(cookies)
                        if result.get("error") or not result.get("is_login"):
                            raise ValueError(result.get("error") or "MissEvan rejected these cookies.")
                        missevan.save_login(cookies)
                        name = result.get("username", "")
                    else:
                        result = youtube_web.verify_login(cookies)
                        if result.get("error") or not result.get("is_login"):
                            raise ValueError(result.get("error") or "YouTube rejected these cookies.")
                        youtube_web.save_login(cookies)
                        name = result.get("name", "")
                if not self._persist_logins():
                    self.cookie_status.setText(
                        self.i18n.translate(
                            "Unable to save login cookies to application settings.",
                            self._ui_language,
                        )
                    )
                    return
                self.cookie_input.clear()
                self.cookie_status.setText(
                    self.i18n.translate(
                        "Logged in to {site} as {name}. Cookies are stored encrypted in application settings.",
                        self._ui_language,
                        site=site,
                        name=name,
                    )
                )
            except Exception as exc:
                self.cookie_status.setText(f"Login not saved: {exc}")

        def _normalize_cookie_input(self, text):
            one_line = " ".join(text.splitlines())
            if one_line == text:
                return
            cursor = self.cookie_input.cursorPosition()
            signals_blocked = self.cookie_input.blockSignals(True)
            self.cookie_input.setText(one_line)
            self.cookie_input.setCursorPosition(min(cursor, len(one_line)))
            self.cookie_input.blockSignals(signals_blocked)

        def _refresh_login_status(self):
            for site, label in self.login_status_labels.items():
                saved = bool(self._login_data.get(site))
                label.setText(
                    self.i18n.translate(
                        "Signed in (saved in app settings)" if saved else "Not signed in",
                        self._ui_language,
                    )
                )
                label.setStyleSheet(
                    "color: #16803c;" if saved else "color: #666666;"
                )

        def _read_browser_cookies(self):
            from src import browser_cookies as bc
            browser = self.cookie_browser.currentText()
            site = self.cookie_site.currentText()
            if browser not in bc.BROWSERS:
                self.cookie_status.setText("Select Firefox as the cookie source, or paste cookies and choose Verify and save login.")
                return
            def read():
                return bc.read_cookies(bc.BROWSERS[browser], bc.SITES[site])
            def done(cookies):
                if not cookies:
                    self.cookie_status.setText(f"No {site} cookies found in {browser}.")
                else:
                    self.cookie_input.setText("; ".join(f"{k}={v}" for k, v in cookies.items()))
                    self.cookie_status.setText(f"Read {len(cookies)} cookies. Review then choose Verify and save login.")
            self._run_task(read, done)

        def _persist_logins(self):
            self._settings.setValue("login_token", self._encode_logins(self._login_data))
            self._settings.sync()
            if self._worker:
                self._worker.update_logins(self._login_data)
            if hasattr(self, "login_status_labels"):
                self._refresh_login_status()
            return self._settings.status() == QtCore.QSettings.Status.NoError

        def _clear_login(self):
            from src import browser_cookies as bc
            site = self.cookie_site.currentText().lower()
            with self._login_context():
                bc.clear_login(site)
            if self._persist_logins():
                self.cookie_status.setText(f"Cleared {site} login.")
            else:
                self.cookie_status.setText(
                    self.i18n.translate(
                        "Unable to save login cookies to application settings.",
                        self._ui_language,
                    )
                )

        def _obs_text(self, text, **kwargs):
            return self.i18n.translate(text, self._ui_language, **kwargs)

        def _set_obs_enabled(self, enabled):
            self._settings.setValue("obs_enabled", bool(enabled))
            self._settings.sync()
            self._obs_chat_last = None
            if enabled:
                from src import obs_ctrl

                obs_ctrl.retry_now()
                self._obs_poll()
            else:
                self._obs_source_snapshot = None
                self._render_obs_state({"status": {"connected": False}, "error": ("", "")})

        def _set_obs_chat_names(self, enabled):
            self._settings.setValue("obs_chat_names", bool(enabled))
            self._settings.sync()
            self._sync_obs_chat()

        def _set_obs_chat_enabled(self, enabled):
            self._settings.setValue("obs_chat_enabled", bool(enabled))
            self._settings.sync()
            self._obs_chat_last = None
            if enabled:
                self._obs_poll()
            else:
                self._render_obs_text_sources(None, "")

        def _obs_text_source_changed(self, _index=None):
            source = self.obs_text_source.currentData() or ""
            self._settings.setValue("obs_chat_source", source)
            self._settings.sync()
            self._obs_chat_last = None
            self._sync_obs_chat()

        def _obs_poll(self):
            if not self.obs_enabled.isChecked() or self._obs_poll_running:
                return
            self._obs_poll_running = True
            chat_enabled = self.obs_chat_enabled.isChecked()

            def fetch():
                from src import obs_ctrl

                state = {
                    "status": {"connected": False},
                    "error": ("", ""),
                    "scenes": [],
                    "sources": [],
                    "text_sources": None,
                    "text_error": "",
                }
                try:
                    state["status"] = obs_ctrl.get_status()
                    state["error"] = tuple(obs_ctrl.last_error)
                    if state["status"].get("connected"):
                        state["scenes"] = obs_ctrl.get_scenes()
                        scene = state["status"].get("current_scene") or ""
                        if scene:
                            state["sources"] = obs_ctrl.get_sources(scene)
                        if chat_enabled:
                            try:
                                state["text_sources"] = obs_ctrl.get_text_sources()
                            except Exception as exc:
                                state["text_error"] = str(exc)
                except Exception as exc:
                    state["status"] = {"connected": False}
                    state["error"] = ("unreachable", str(exc))
                return state

            self._run_task(fetch, self._obs_poll_finished)

        def _obs_poll_finished(self, state):
            self._obs_poll_running = False
            if not self.obs_enabled.isChecked():
                return
            self._render_obs_state(state)
            self._sync_obs_chat()

        def _render_obs_state(self, state):
            self._obs_last_state = state
            enabled = self.obs_enabled.isChecked()
            status = state.get("status") or {}
            connected = bool(enabled and status.get("connected"))
            self._obs_connected = connected
            self.obs_controls.setVisible(connected)
            self.obs_setup.setVisible(enabled and not connected)
            self.obs_status_detail.setVisible(False)
            self.obs_setup_text.setText(
                _OBS_SETUP_MD
                if self._ui_language == "en"
                else self._obs_text("obs_setup_md")
            )
            if not enabled:
                self.obs_status.setText(self._obs_text("OBS functions are off."))
                return
            if not connected:
                from src.config import OBS_HOST, OBS_PORT

                message, detail = _obs_connection_message(
                    tuple(state.get("error") or ("", "")),
                    OBS_HOST,
                    OBS_PORT,
                    self._obs_text,
                )
                self.obs_status.setText(message)
                self.obs_status_detail.setText(detail)
                self.obs_status_detail.setVisible(bool(detail))
                return
            self.obs_status.setText(self._obs_text("OBS connected ✓"))
            self.obs_metrics["cpu"].setText(f"{status.get('cpu_usage', 0)}%")
            self.obs_metrics["ram"].setText(f"{status.get('memory_usage', 0)} MB")
            self.obs_metrics["fps"].setText(f"{status.get('fps', 0)}")
            self.obs_metrics["dropped"].setText(f"{status.get('output_skipped_frames', 0)}")
            self._obs_streaming = bool(status.get("streaming"))
            self._obs_recording = bool(status.get("recording"))
            self.obs_stream_state.setText(
                self._obs_text("Streaming is LIVE" if self._obs_streaming else "Not streaming")
            )
            self.obs_stream_button.setText(
                self._obs_text("⏹ Stop Stream" if self._obs_streaming else "▶️ Start Stream")
            )
            self.obs_record_state.setText(
                self._obs_text(
                    "Recording in progress" if self._obs_recording else "Not recording"
                )
            )
            self.obs_record_button.setText(
                self._obs_text(
                    "⏹ Stop Recording" if self._obs_recording else "▶️ Start Recording"
                )
            )
            scenes = list(state.get("scenes") or [])
            current_scene = status.get("current_scene") or ""
            if [self.obs_scenes.itemText(i) for i in range(self.obs_scenes.count())] != scenes:
                self.obs_scenes.blockSignals(True)
                self.obs_scenes.clear()
                self.obs_scenes.addItems(scenes)
                self.obs_scenes.blockSignals(False)
            if not self.obs_scenes.view().isVisible():
                index = self.obs_scenes.findText(current_scene)
                if index >= 0 and index != self.obs_scenes.currentIndex():
                    self.obs_scenes.blockSignals(True)
                    self.obs_scenes.setCurrentIndex(index)
                    self.obs_scenes.blockSignals(False)
            self._obs_show_sources(current_scene, state.get("sources") or [])
            if self.obs_chat_enabled.isChecked():
                self._render_obs_text_sources(
                    state.get("text_sources"), state.get("text_error", "")
                )
            else:
                self._render_obs_text_sources(None, "")

        def _render_obs_text_sources(self, sources, error):
            chat_enabled = self.obs_chat_enabled.isChecked()
            self.obs_text_source_row.setVisible(chat_enabled and bool(sources))
            warning = ""
            if chat_enabled and error:
                warning = self._obs_text("Couldn't list OBS Text sources: {err}", err=error)
            elif chat_enabled and sources is not None and not sources:
                warning = self._obs_text("Add a Text source in OBS to display chat.")
            if warning or not chat_enabled:
                self.obs_text_warning.setText(warning)
            self.obs_text_warning.setVisible(bool(self.obs_text_warning.text()) and chat_enabled)
            if sources is None:
                return
            sources = list(sources)
            current = [
                self.obs_text_source.itemData(i) for i in range(self.obs_text_source.count())
            ]
            saved = self._settings.value("obs_chat_source", "", type=str)
            if current != sources:
                self.obs_text_source.blockSignals(True)
                self.obs_text_source.clear()
                for name in sources:
                    self.obs_text_source.addItem(name, name)
                self.obs_text_source.blockSignals(False)
            if sources:
                index = self.obs_text_source.findData(saved)
                if index < 0:
                    index = 0
                if index != self.obs_text_source.currentIndex():
                    self.obs_text_source.blockSignals(True)
                    self.obs_text_source.setCurrentIndex(index)
                    self.obs_text_source.blockSignals(False)
                selected = self.obs_text_source.currentData() or ""
                if selected != saved:
                    self._settings.setValue("obs_chat_source", selected)
                    self._settings.sync()
                    self._obs_chat_last = None
                self.obs_text_warning.setText("")
                self.obs_text_warning.setVisible(False)

        def _sync_obs_chat(self):
            if (
                not self.obs_enabled.isChecked()
                or not self.obs_chat_enabled.isChecked()
                or not self._obs_connected
            ):
                if not self.obs_chat_enabled.isChecked():
                    self._obs_chat_last = None
                return
            source = self.obs_text_source.currentData() or ""
            if not source:
                return
            from src import obs_ctrl, translate

            chat = [msg for msg in self._messages if self._is_selected_chat_message(msg)]
            translate_enabled, target = self._translate_enabled, self._translate_target
            if translate_enabled:
                translate.prefetch(
                    [msg.get("text", "") for msg in obs_ctrl.recent_chat(chat)], target
                )
            text = obs_ctrl.format_chat_text(
                chat,
                translate_enabled,
                target,
                translate.get_translation,
                show_names=self.obs_chat_names.isChecked(),
            )
            now = time.monotonic()
            if not _obs_chat_update_due(
                self._obs_chat_last, self._obs_chat_last_at, source, text, now
            ):
                return
            self._obs_chat_last = (source, text)
            self._obs_chat_last_at = now

            def push():
                try:
                    obs_ctrl.set_text_source(source, text)
                except Exception as exc:
                    return str(exc)
                return ""

            self._run_task(push, self._obs_chat_pushed)

        def _obs_chat_pushed(self, error):
            if error:
                self._obs_chat_last = None
                self.obs_text_warning.setText(
                    self._obs_text("Couldn't update OBS chat text: {err}", err=error)
                )
                self.obs_text_warning.setVisible(True)

        def _obs_action(self, operation, failure):
            def run():
                from src import obs_ctrl

                try:
                    return bool(operation(obs_ctrl))
                except Exception:
                    return False

            def done(ok):
                if not ok:
                    self._show_error(self._obs_text(failure))
                self._obs_poll()

            self._run_task(run, done)

        def _obs_toggle_stream(self):
            if self._obs_streaming:
                self._obs_action(lambda obs: obs.stop_stream(), "Could not stop stream.")
            else:
                self._obs_action(
                    lambda obs: obs.start_stream(),
                    "Could not start stream; check OBS connection and settings.",
                )

        def _obs_toggle_recording(self):
            if self._obs_recording:
                self._obs_action(lambda obs: obs.stop_recording(), "Could not stop recording.")
            else:
                self._obs_action(lambda obs: obs.start_recording(), "Could not start recording.")

        def _obs_switch_scene(self, _index=None):
            scene = self.obs_scenes.currentText()
            if scene:
                self._obs_source_snapshot = None
                self._obs_action(
                    lambda obs: obs.switch_scene(scene), "Could not switch scene."
                )

        def _obs_show_sources(self, scene, sources):
            snapshot = (scene, tuple((s.get("name"), bool(s.get("visible"))) for s in sources))
            if snapshot == self._obs_source_snapshot:
                return
            self._obs_source_snapshot = snapshot
            self.obs_sources.blockSignals(True)
            self.obs_sources.clear()
            for source in sources:
                item = QtWidgets.QListWidgetItem(source["name"])
                item.setData(QtCore.Qt.ItemDataRole.UserRole, scene)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    QtCore.Qt.CheckState.Checked if source["visible"] else QtCore.Qt.CheckState.Unchecked
                )
                self.obs_sources.addItem(item)
            self.obs_sources.blockSignals(False)

        def _obs_source_visibility_changed(self, item):
            scene = item.data(QtCore.Qt.ItemDataRole.UserRole) or self.obs_scenes.currentText()
            name = item.text()
            visible = item.checkState() == QtCore.Qt.CheckState.Checked
            self._obs_source_snapshot = None
            self._obs_action(
                lambda obs: obs.set_source_visibility(scene, name, visible),
                f"Could not update source {name} visibility.",
            )

        def _start_overlay(self):
            from src import overlay_server, config
            from src import bilibili, missevan, youtube, youtube_web
            targets = {}
            for platform, check in self.overlay_sites.items():
                monitor_id = str(self.overlay_rooms[platform].currentData() or "")
                entry = next(
                    (t for t in self._monitor_targets if t["id"] == monitor_id), None
                )
                targets[platform] = entry["target"].strip() if entry and check.isChecked() else ""
            yt_target = targets["youtube"]
            if yt_target:
                yt_target = youtube_web.channel_url(yt_target) or youtube.extract_video_id(yt_target)
                if not yt_target:
                    self._show_error("Enter a valid YouTube channel, live URL, or video ID for the overlay.")
                    return
            selected = {
                "youtube": yt_target,
                "bilibili": bilibili.parse_room_id(targets["bilibili"]) if targets["bilibili"] else "",
                "missevan": missevan.parse_room_id(targets["missevan"]) if targets["missevan"] else "",
            }
            if not any(selected.values()):
                self._show_error(self.i18n.translate("Select at least one monitored room for the overlay.", self._ui_language))
                return
            count = self.overlay_count.value()
            host = (
                config.OVERLAY_PUBLIC_URL
                or f"http://{'127.0.0.1' if config.OVERLAY_HOST in ('0.0.0.0', '::') else config.OVERLAY_HOST}:{config.OVERLAY_PORT}"
            )
            short_names = {"youtube": "yt", "bilibili": "bili", "missevan": "me"}
            query_values = {
                **{short_names[p]: v for p, v in selected.items() if v},
                "n": count,
                "sc": self.overlay_paid_count.value(),
                "names": 1 if self.overlay_show_names.isChecked() else 0,
                "text": self.overlay_custom_text.text().strip(),
            }
            if self.overlay_translate.isChecked():
                query_values["tr"] = self._translate_target
            query = urlencode(query_values)

            def start():
                overlay_server.ensure_started()
                return f"{host.rstrip('/')}/overlay?{query}"
            self._run_task(start, lambda url: (self.overlay_url.setText(url), QtWidgets.QApplication.clipboard().setText(url), self.statusBar().showMessage("Overlay URL copied.", 5000)))

        def _refresh_transcription_rooms(self, *_):
            if not hasattr(self, "transcribe_room"):
                return
            platform = self.transcribe_site.currentData()
            if not platform:
                return
            previous_id = (
                self.transcribe_room.currentData()
                if getattr(self, "_transcribe_room_platform", "") == platform
                else ""
            )
            saved_id = self._settings.value(
                f"transcribe_room_{platform}", "", type=str
            )
            entries = _transcription_room_entries(
                platform, self._monitor_targets
            )
            self.transcribe_room.blockSignals(True)
            self.transcribe_room.clear()
            self.transcribe_room.addItem(self.i18n.translate("Select a room", self._ui_language), "")
            for entry in entries:
                target = entry["target"]
                name = self._room_names.get(entry["id"], "").strip()
                label = f"{name} · {target}" if name and name != target else target
                self.transcribe_room.addItem(label, entry["id"])
            preferred_id = previous_id or saved_id
            if not preferred_id:
                chat_selector = getattr(self, "chat_room_selectors", {}).get(
                    platform
                )
                preferred_id = (
                    str(chat_selector.currentData() or "")
                    if chat_selector else ""
                )
            index = (
                self.transcribe_room.findData(preferred_id)
                if preferred_id else -1
            )
            self.transcribe_room.setCurrentIndex(max(0, index))
            self.transcribe_room.blockSignals(False)
            self._transcribe_room_platform = platform
            self.transcribe_room.setToolTip(
                "Select a room; transcription can start when it goes live."
            )
            if self.transcribe_room.count() == 1:
                self.transcribe_room.setEnabled(False)
                self.transcription_status.setText(
                    "Add a room before starting transcription."
                )
            else:
                self.transcribe_room.setEnabled(True)
                if preferred_id and index < 0:
                    self._settings.setValue(
                        f"transcribe_room_{platform}", ""
                    )

        def _transcription_room_changed(self, *_):
            platform = self.transcribe_site.currentData()
            if platform:
                self._settings.setValue(
                    f"transcribe_room_{platform}",
                    str(self.transcribe_room.currentData() or ""),
                )
                self._settings.sync()
                if self._settings.status() != QtCore.QSettings.Status.NoError:
                    self._show_error(
                        "Unable to save the transcription room selection."
                    )

        def _start_transcription(self):
            platform = self.transcribe_site.currentData()
            monitor_id = str(self.transcribe_room.currentData() or "")
            target = _selected_transcription_room(
                platform, monitor_id, self._monitor_targets
            )
            if not target:
                self.transcription_status.setText(
                    "Select a room to transcribe."
                )
                return
            path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
                self,
                self.i18n.translate("Choose transcript file", self._ui_language),
                str(_ROOT / "recordings" / "transcription.txt"),
                "Text files (*.txt);;LRC files (*.lrc)",
            )
            if not path:
                return
            destination = Path(path)
            if not destination.suffix:
                destination = destination.with_suffix(
                    ".lrc" if selected_filter == "LRC files (*.lrc)" else ".txt"
                )
            try:
                self._transcription_lrc_offset = max(
                    _existing_lrc_offset(destination),
                    self._transcription_lrc_offsets.get(
                        destination.resolve(), 0
                    ),
                )
            except (OSError, UnicodeError) as exc:
                self.transcription_status.setText(
                    f"Could not read transcript file: {exc}"
                )
                return
            self._stop_transcription()
            self._transcription_armed_id = monitor_id
            self._transcription_destination = destination
            if not self._live_states.get(monitor_id, False):
                self.transcription_status.setText(
                    self.i18n.translate("Waiting for room to go live", self._ui_language)
                )
                return
            self._begin_transcription(target)

        def _begin_transcription(self, target):
            from src import transcription, bilibili, missevan

            platform = target["platform"]
            if platform == "youtube":
                youtube_state = (
                    self._worker._youtube.get(target["id"], {})
                    if self._worker else {}
                )
                source_id = youtube_state.get("video_id", "")
                if not source_id:
                    self.transcription_status.setText(
                        "The selected YouTube room has no live video yet."
                    )
                    return
                resolver = lambda: transcription.resolve_youtube_audio_source(
                    f"https://www.youtube.com/watch?v={source_id}"
                )
            elif platform == "bilibili":
                source_id = bilibili.parse_room_id(target["target"])
                resolver = lambda: self._with_login(
                    lambda: bilibili.get_live_audio_url(source_id)
                )
            else:
                source_id = missevan.parse_room_id(target["target"])
                resolver = lambda: self._with_login(
                    lambda: missevan.get_live_audio_url(source_id)
                )
            try:
                if self._transcriber and self._transcriber.is_running:
                    self._transcriber.stop()
                self._transcriber = transcription.LiveTranscriber(
                    platform, source_id, resolver, self._translate_target,
                    self.transcribe_model.currentText(), self.transcribe_translation.isChecked(),
                )
                self._transcriber.start()
                self._transcription_sessions.append(
                    {
                        "worker": self._transcriber,
                        "skip": 0,
                        "appended": 0,
                        "path": self._transcription_destination,
                        "lrc_offset": self._transcription_lrc_offset,
                    }
                )
                room_name = self._room_names.get(target["id"], target["target"])
                self.transcription_status.setText(
                    f"Starting transcription for {room_name}…"
                )
            except Exception as exc:
                self.transcription_status.setText(str(exc))

        def _stop_transcription(self):
            self._transcription_armed_id = None
            if self._transcriber:
                self._transcriber.stop()

        def _clear_transcriptions(self):
            for session in self._transcription_sessions:
                session["skip"] = len(session["worker"].snapshot()["segments"])
            self._segments = []
            self.transcription_output.clear()

        def _poll_transcription(self):
            if not self._transcriber:
                return
            snapshot = self._transcriber.snapshot()
            waiting = (
                self._transcription_armed_id is not None
                and not self._live_states.get(self._transcription_armed_id, False)
            )
            self.transcription_status.setText(
                self.i18n.translate("Waiting for room to go live", self._ui_language)
                if waiting else
                snapshot["status"] + (f": {snapshot['error']}" if snapshot["error"] else "")
            )
            append_error = ""
            for session in self._transcription_sessions:
                worker_segments = session["worker"].snapshot()["segments"]
                appended = session.get("appended", 0)
                for index in range(appended, len(worker_segments)):
                    try:
                        _append_transcription_segment(
                            session["path"],
                            worker_segments[index],
                            session.get("lrc_offset", 0),
                        )
                    except (OSError, ValueError) as exc:
                        append_error = f"Could not append transcript: {exc}"
                        break
                    if session["path"].suffix.lower() == ".lrc":
                        seconds = worker_segments[index].get("start_seconds")
                        if isinstance(seconds, (int, float)) and math.isfinite(seconds):
                            next_offset = session.get("lrc_offset", 0) + seconds + 8
                            path_key = session["path"].resolve()
                            self._transcription_lrc_offsets[path_key] = max(
                                self._transcription_lrc_offsets.get(path_key, 0),
                                next_offset,
                            )
                    session["appended"] = index + 1
                if append_error:
                    break
            if append_error:
                self.transcription_status.setText(append_error)
            segments = [
                segment
                for session in self._transcription_sessions
                for segment in session["worker"].snapshot()["segments"][session["skip"]:]
            ]
            if segments != self._segments:
                self._segments = segments
                self.transcription_output.setPlainText(
                    _format_transcription(segments)
                )
                self.transcription_output.verticalScrollBar().setValue(
                    self.transcription_output.verticalScrollBar().maximum()
                )

        def _refresh_analytics(self):
            from src import highlights
            from src.tts import is_paid
            totals = defaultdict(float)
            sites = Counter()
            chatters = Counter()
            per_minute = Counter()
            for timestamp, msg in self._activity:
                sites[msg.get("platform", "")] += 1
                chatters[(msg.get("platform", ""), msg.get("author", ""))] += 1
                if is_paid(msg) and msg.get("currency") and msg.get("value"):
                    try:
                        totals[(msg["platform"], msg["currency"])] += float(msg["value"])
                    except (ValueError, TypeError):
                        pass
                per_minute[datetime.fromtimestamp(timestamp).strftime("%H:%M")] += 1
            current_viewers = self._viewer_samples[-1][1] if self._viewer_samples else {}
            peak_viewers = {
                site: max((sample.get(site, 0) for _, sample in self._viewer_samples), default=0)
                for site in ("youtube", "bilibili", "missevan")
            }
            viewer_summary = " · ".join(
                f"{site.title()}: {current_viewers.get(site, 0):,} now / {peak_viewers[site]:,} peak"
                for site in ("youtube", "bilibili", "missevan")
                if site in current_viewers
            )
            self.analytics_summary.setText(
                f"Session messages: {len(self._activity)}"
                + (f" · {viewer_summary}" if viewer_summary else "")
            )
            rows = []
            for site, count in sites.most_common():
                rows.append(("Messages", site, count, "All observed messages"))
            for (site, currency), value in totals.items():
                rows.append(("Paid value", site, f"{value:g} {currency}", "Original platform currency"))
            for (site, author), count in chatters.most_common(20):
                rows.append(("Top chatter", site, count, author))
            for minute, count in per_minute.most_common(20):
                rows.append(("Messages/minute", "", count, minute))
            self._hotspots = highlights.find_highlights(
                self._hotspot_events, window=self.hotspot_window.value()
            )
            for index, clip in enumerate(self._hotspots, 1):
                rows.append(("Hotspot", ", ".join(clip["platforms"]), clip["score"], highlights.summary(clip)))
            self.analytics_table.setRowCount(len(rows))
            for r, values in enumerate(rows):
                for c, value in enumerate(values):
                    self.analytics_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(value)))

        def _export_hotspots_csv(self):
            from src import highlights
            if not self._hotspots:
                self._refresh_analytics()
            if not self._hotspots:
                self._show_error("No chat hotspots are available to export.")
                return
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export chat hotspots", "chat-hotspots.csv", "CSV files (*.csv)"
            )
            if path:
                Path(path).write_bytes(highlights.to_csv(self._hotspots))
                self.statusBar().showMessage(f"Exported hotspots to {path}.", 5000)

        def _export_hotspots_edl(self):
            from src import highlights
            if not self._hotspots:
                self._refresh_analytics()
            if not self._hotspots:
                self._show_error("No chat hotspots are available to export.")
                return
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export DaVinci Resolve markers", "chat-hotspots.edl", "EDL files (*.edl)"
            )
            if path:
                origin = min((event["ts"] for event in self._hotspot_events), default=time.time())
                Path(path).write_bytes(highlights.to_edl(self._hotspots, origin))
                self.statusBar().showMessage(f"Exported EDL to {path}.", 5000)

        def _load_archive_view(self):
            result = self._archive.load_archive()
            if not result.get("ok"):
                self._show_error(result["error"])
                return
            self._saved_archive = result["archive"]
            self.archive_sessions.blockSignals(True)
            self.archive_sessions.clear()
            for session in reversed(self._saved_archive["sessions"]):
                identity = session.get("channel_id") or session.get("room_id")
                platform = session.get("platform", "")
                if identity:
                    room_name = _saved_session_room_label(session)
                    label = (
                        f"{platform.title()} · {room_name} · "
                        f"{len(session['messages'])} messages"
                    )
                else:
                    label = f"{session['started_at']} · {len(session['messages'])} messages"
                self.archive_sessions.addItem(
                    label,
                    session["session_id"],
                )
            saved_session_id = self._settings.value(
                "archive_session", "", type=str
            )
            if saved_session_id:
                saved_index = self.archive_sessions.findData(saved_session_id)
                if saved_index >= 0:
                    self.archive_sessions.setCurrentIndex(saved_index)
            self.archive_sessions.blockSignals(False)
            self._show_archive_session()
            self.archive_path_label.setText(
                self.i18n.translate("Saved room files: {path}", self._ui_language, path=self._archive.sessions_path)
            )

        def _refresh_archive_session_labels(self):
            if not hasattr(self, "_saved_archive") or not hasattr(
                self, "archive_sessions"
            ):
                return
            current_session_id = self.archive_sessions.currentData()
            sessions = {
                session["session_id"]: session
                for session in self._saved_archive["sessions"]
            }
            self.archive_sessions.blockSignals(True)
            try:
                for index in range(self.archive_sessions.count()):
                    session_id = self.archive_sessions.itemData(index)
                    session = sessions.get(session_id)
                    if not session:
                        continue
                    identity = session.get("channel_id") or session.get("room_id")
                    if not identity:
                        continue
                    room_name = session.get("room_name") or ""
                    if not room_name:
                        platform, _, saved_identity = session_id.partition(":")
                        for target in self._monitor_targets:
                            if target["platform"] != platform:
                                continue
                            target_identity = target["target"]
                            if platform == "bilibili":
                                from src import bilibili
                                target_identity = bilibili.parse_room_id(target_identity)
                            elif platform == "missevan":
                                from src import missevan
                                target_identity = missevan.parse_room_id(target_identity)
                            if (
                                target_identity == saved_identity
                                and target["id"] in self._room_names
                            ):
                                room_name = self._room_names[target["id"]]
                                break
                    display_name = room_name or _saved_session_room_label(session)
                    self.archive_sessions.setItemText(
                        index,
                        f"{session.get('platform', '').title()} · {display_name} · "
                        f"{len(session['messages'])} messages",
                    )
            finally:
                self.archive_sessions.blockSignals(False)
            if current_session_id is not None:
                index = self.archive_sessions.findData(current_session_id)
                if index >= 0:
                    self.archive_sessions.setCurrentIndex(index)

        def _show_archive_session(self, *_):
            if not hasattr(self, "_saved_archive") or self.archive_sessions.count() == 0:
                self.archive_table.setRowCount(0)
                return
            session_id = self.archive_sessions.currentData()
            if session_id:
                self._settings.setValue("archive_session", str(session_id))
            session = next((item for item in self._saved_archive["sessions"] if item["session_id"] == session_id), None)
            messages = session.get("messages", []) if session else []
            self.archive_table.setRowCount(len(messages))
            for row, msg in enumerate(messages):
                for col, key in enumerate(("timestamp", "platform", "author", "text")):
                    value = (
                        _format_chat_timestamp(msg.get(key, ""))
                        if key == "timestamp"
                        else msg.get(key, "")
                    )
                    self.archive_table.setItem(
                        row, col, QtWidgets.QTableWidgetItem(value)
                    )

        def _delete_saved_session(self):
            session_id = self.archive_sessions.currentData()
            if not session_id:
                self._show_error("Select a saved channel or room first.")
                return
            session = next(
                (
                    item for item in self._saved_archive.get("sessions", [])
                    if item.get("session_id") == session_id
                ),
                None,
            )
            if session is None:
                self._show_error("The selected saved chat session no longer exists.")
                return
            identity = session.get("channel_id") or session.get("room_id") or session_id
            platform = session.get("platform", "").title()
            confirm = QtWidgets.QMessageBox.question(
                self,
                self.i18n.translate("Delete saved chat", self._ui_language),
                self.i18n.translate(
                    "Delete all saved messages for {site} {identity}? This cannot be undone.",
                    self._ui_language,
                    site=platform,
                    identity=identity,
                ),
            )
            if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                return

            result = self._archive.delete_session(session_id)
            if not result.get("ok"):
                self._show_error(result["error"])
                return

            platform_key, _, saved_identity = session_id.partition(":")
            monitor_ids = set()
            for entry in self._monitor_targets:
                if entry["platform"] != platform_key:
                    continue
                target_identity = entry["target"]
                if platform_key == "bilibili":
                    from src import bilibili
                    target_identity = bilibili.parse_room_id(target_identity)
                elif platform_key == "missevan":
                    from src import missevan
                    target_identity = missevan.parse_room_id(target_identity)
                if target_identity == saved_identity or entry["id"] == session_id:
                    monitor_ids.add(entry["id"])

            for messages in (self._messages, self._paid, self._joins):
                messages[:] = [
                    message for message in messages
                    if not (
                        message.get("platform") == platform_key
                        and (
                            message.get("_monitor_id") in monitor_ids
                            or (
                                not message.get("_monitor_id")
                                and len(monitor_ids) == 1
                            )
                        )
                    )
                ]
            self._saved_archive = result["archive"]
            self._refresh_feeds()
            self._load_archive_view()
            self.statusBar().showMessage(
                self.i18n.translate(
                    "Deleted saved messages for {site} {identity}.",
                    self._ui_language,
                    site=platform,
                    identity=identity,
                ),
                5000,
            )

        def _save_archive(self, refresh_view=False):
            archive_messages = sorted(
                [*self._messages, *self._paid, *self._joins],
                key=lambda msg: msg.get("_arrived", 0),
            )
            if not archive_messages:
                return
            messages_by_target = defaultdict(list)
            for msg in archive_messages:
                if msg.get("type") == "enter":
                    continue
                platform = str(msg.get("platform", "")).lower()
                if platform not in self.target_inputs:
                    continue
                entry = _monitored_target_for_message(
                    msg, self._monitor_targets
                )
                if entry is None:
                    continue
                messages_by_target[entry["id"]].append({
                    "timestamp": str(msg.get("timestamp", "")),
                    "platform": platform,
                    "author": str(msg.get("author", "")),
                    "text": str(msg.get("text", "")),
                })

            if not messages_by_target:
                self.statusBar().showMessage(
                    self.i18n.translate(
                        "Enable saving for a room before saving its chat.",
                        self._ui_language,
                    ),
                    5000,
                )
                return

            errors = []
            saved_any = False
            for monitor_id, messages in messages_by_target.items():
                entry = next(
                    target for target in self._monitor_targets if target["id"] == monitor_id
                )
                platform = entry["platform"]
                configured_target = entry["target"]
                if platform == "youtube":
                    channel_id = configured_target
                    room_id = ""
                else:
                    from src import bilibili, missevan
                    room_id = (
                        bilibili.parse_room_id(configured_target)
                        if platform == "bilibili"
                        else missevan.parse_room_id(configured_target)
                    )
                    channel_id = ""
                identity = channel_id or room_id
                if not identity:
                    errors.append(
                        f"Could not save {platform.title()} messages: enter a valid "
                        "room or channel ID in Stream Monitoring."
                    )
                    continue
                session_id = f"{platform}:{identity}"
                result = self._archive.save_snapshot(
                    session_id,
                    messages[-_MAX_SESSION_MESSAGES:],
                    platform=platform,
                    room_id=room_id,
                    channel_id=channel_id,
                    room_name=self._room_names.get(monitor_id, ""),
                )
                if not result.get("ok"):
                    errors.append(result["error"])
                    continue
                self._saved_archive = result["archive"]
                saved_any = True

            if errors:
                self._show_error(" ".join(errors))
            if saved_any and refresh_view:
                self._load_archive_view()

        def changeEvent(self, event):
            if event.type() == QtCore.QEvent.Type.WindowDeactivate:
                QtWidgets.QToolTip.hideText()
            super().changeEvent(event)

        def closeEvent(self, event):
            if self._memory_timer:
                self._memory_timer.stop()
                self._sample_memory_usage()
            if self._memory_logger:
                self._memory_logger.info(
                    json.dumps({"event": "monitor_stopped"})
                )
            self._settings.setValue("window_geometry", self.saveGeometry())
            if hasattr(self, "_feed_splitter"):
                self._save_splitter_sizes(
                    "feed_splitter_sizes", self._feed_splitter
                )
            if hasattr(self, "_chat_splitter_layout_name"):
                self._save_chat_splitter_sizes()
            self._settings.sync()
            if self._transcriber:
                self._transcriber.stop()
            if self._worker:
                self._worker.stop()
            self._obs_timer.stop()
            for recorder in self._recorders.values():
                recorder.stop()
            for recorder in self._recorders.values():
                recorder.stop(wait=3)
            self._save_monitor_targets()
            self._save_archive()
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._emote_image_pool.shutdown(wait=False, cancel_futures=True)
            event.accept()


def main() -> int:
    argparse.ArgumentParser(
        description="Run the full Streaming Dashboard in a native PySide6 desktop window."
    ).parse_args()
    if QtWidgets is None:
        print(
            "PySide6 is required for the native desktop UI. Install it with "
            f'"{sys.executable}" -m pip install PySide6.',
            file=sys.stderr,
        )
        return 1
    try:
        app = QtWidgets.QApplication(sys.argv[:1])
        app.setApplicationName("Streaming Dashboard")
        app.setOrganizationName("OneJan111")
        app.setStyle("Fusion")
        window = _DesktopWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        print(f"Unable to start the Qt desktop dashboard: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
