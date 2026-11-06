"""Local HTML dashboard backed by the existing Python platform integrations."""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

import desktop_app
from src import gifts, tts, user_login
from src import i18n as base_i18n
from src.filters import ChatFilter
from src.gift_assets import GiftArtwork
from src.room_events import RoomEvents
from src.caption_engine import TRANSCRIPTION_DEFAULTS, caption_options

# Same translator as the desktop window: shared strings plus desktop-only strings.
i18n = desktop_app._DesktopI18n(base_i18n)


def catalog(lang: str) -> dict[str, str]:
    """Browser string table for one interface language, including desktop-only strings."""
    index = {"zh": 0, "ja": 1}[lang]
    return {**base_i18n.catalog(lang),
            **{text: values[index] for text, values in desktop_app._DESKTOP_STRINGS.items()}}

log = logging.getLogger(__name__)
ASSETS = Path(__file__).parent / "assets" / "html_dashboard"
SITES = tuple(user_login.SITES)
# Same option names and defaults as the desktop app's QSettings.
DEFAULTS = {
    **TRANSCRIPTION_DEFAULTS,
    "max_messages": 100, "gift_effects": False, "ui_language": "en",
    "show_reading": True, "notify_live": True,
    "visible_sites": list(SITES), "send_sites": ["bilibili", "missevan"], "selected_rooms": {},
    "tts_enabled": False, "tts_language": "auto", "tts_rate": 150, "tts_volume": 100,
    "tts_paid": True, "tts_joins": False, "tts_translate": False,
    "tts_skip_name": False, "tts_skip_emoji": True,
    "translate_enabled": False, "translate_target": "en",
    "record_folder": "", "record_quality": 10000, "record_danmaku": True,
    "obs_enabled": False, "obs_chat_enabled": False, "obs_chat_names": True, "obs_chat_source": "",
    "hotspot_window": 30,
    "overlay_count": 5, "overlay_paid_count": 3, "overlay_show_names": True,
    "overlay_translate": False, "overlay_custom_text": "",
}
SPEECH_BACKLOG = 50


@lru_cache(maxsize=4096)
def _reading(text):
    from src import reading
    return reading.segments(text)


class Dashboard:
    def __init__(self, path: Path, *, start: bool = True):
        self.path = path
        self.lock = threading.RLock()
        self.settings = deepcopy(DEFAULTS)
        self.transcription_api_key = ""
        self.transcription_api_key_dpapi = ""
        self.transcription_key_error = ""
        self.targets = []
        self.record_armed = set()
        self.thanked = set()
        if path.exists():
            self.load_saved()
        self.logins = {}
        self.login_names = {}
        self.statuses = {}
        self.messages = deque(maxlen=3000)
        self.joins = deque(maxlen=600)
        self._bilibili_gift_revenue = {}
        self._bilibili_gift_events = {}
        self.speech = deque(maxlen=SPEECH_BACKLOG)
        self.speech_pending = 0
        self.errors = deque(maxlen=20)
        self.notifications = deque(maxlen=20)
        self.sequence = 0
        self.recorders = {}
        self.record_attempts = {}
        self.closed = False
        self.transcriber = None
        self.translation_client = None
        self.overlay_translation_id = secrets.token_hex(16)
        self.jobs = {}
        self.obs_state = {"connected": False, "error": "", "pushed": None, "pushed_at": 0.0}
        self.avatar_cache, self.avatar_failures, self.avatar_pending = {}, {}, set()
        self.artwork = GiftArtwork()
        self.archive = desktop_app.DesktopChatArchive()
        self.emote_cache = desktop_app.DesktopEmoteCache()
        self.filters = ChatFilter(path.with_name("html_filters.json"))
        self.filters.load()
        self.event_store = RoomEvents(path.with_name("html_room_events.sqlite3"))
        self.event_error = ""
        self.pools = {
            name: ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"html-{name}")
            for name in ("archive", "record", "obs", "transcription", "network", "login", "speech",
                         "avatars", "emotes", "events")
        }
        self.worker = None
        self.load_site_cookies()
        if start:
            self.worker = desktop_app._MonitorWorker(self.logins, self.targets)
            direct = desktop_app.QtCore.Qt.ConnectionType.DirectConnection
            self.worker.statuses.connect(self.receive_statuses, direct)
            self.worker.messages.connect(self.receive_messages, direct)
            self.worker.failed.connect(self.error, direct)
            self.worker.start()
            self.obs_thread = threading.Thread(target=self.obs_loop, name="html-obs-poll", daemon=True)
            self.obs_thread.start()

    def obs_loop(self):
        """Desktop OBS tab refresh: status, scenes, sources and chat text every 3 s while enabled."""
        while not self.closed:
            if self.settings["obs_enabled"]:
                try:
                    self.pools["obs"].submit(self.refresh_obs).result()
                except Exception as exc:
                    if not self.closed:
                        log.debug("OBS poll failed: %s", exc)
            elif self.obs_state["connected"]:
                with self.lock:
                    self.obs_state.update(connected=False, error="", pushed=None)
            for _ in range(30):
                if self.closed:
                    return
                time.sleep(0.1)

    def refresh_obs(self):
        from src import obs_ctrl
        status = obs_ctrl.get_status()
        update = {"connected": bool(status.get("connected")), "error": "", "hint": ""}
        if not update["connected"]:
            from src import config
            language = self.settings["ui_language"]
            update["error"], update["hint"] = desktop_app._obs_connection_message(
                obs_ctrl.last_error if obs_ctrl.last_error[0] else ("auth", str(status.get("error") or "")),
                config.OBS_HOST, config.OBS_PORT,
                lambda text, **kwargs: i18n.translate(text, language, **kwargs))
        if update["connected"]:
            scenes = obs_ctrl.get_scenes()
            current = str(status.get("current_scene") or "")
            update.update(
                status={key: status.get(key) for key in (
                    "cpu_usage", "memory_usage", "fps", "output_skipped_frames", "streaming", "recording")},
                scenes=scenes, current_scene=current,
                sources=obs_ctrl.get_sources(current) if current else [],
            )
            try:
                update["text_sources"] = obs_ctrl.get_text_sources()
                update["text_error"] = ""
            except Exception as exc:
                update["text_sources"] = []
                update["text_error"] = i18n.translate("Couldn't list OBS Text sources: {err}",
                                                      self.settings["ui_language"], err=exc)
        with self.lock:
            self.obs_state.update(update)
            if not update["connected"]:
                self.obs_state["pushed"] = None
        self.push_obs_chat()
        return update["connected"]

    def schedule_obs_chat(self):
        if self.settings["obs_enabled"] and self.settings["obs_chat_enabled"] and self.obs_state["connected"]:
            with self.lock:
                if self.obs_state.get("pushing") or self.closed:
                    return
                self.obs_state["pushing"] = True
            try:
                self.pools["obs"].submit(self.push_obs_chat)
            except RuntimeError:
                self.obs_state["pushing"] = False

    def push_obs_chat(self):
        """Mirror the desktop OBS chat sync: last ten selected-room chat lines into a text source."""
        from src import obs_ctrl
        translate = self.translations()
        try:
            with self.lock:
                settings = deepcopy(self.settings)
                settings["selected_rooms"] = self.effective_rooms(settings)
                source = settings["obs_chat_source"]
                if not (settings["obs_enabled"] and settings["obs_chat_enabled"]
                        and self.obs_state["connected"] and source):
                    if not settings["obs_chat_enabled"]:
                        self.obs_state["pushed"] = None
                    return
                chat = [m for m in self.messages if not m.get("_paid") and self.selected_room(m, settings)]
                last, last_at = self.obs_state["pushed"], self.obs_state["pushed_at"]
            translate_enabled, target = settings["translate_enabled"], settings["translate_target"]
            if translate_enabled:
                translate.prefetch([m.get("text", "") for m in obs_ctrl.recent_chat(chat)], target)
            text = obs_ctrl.format_chat_text(chat, translate_enabled, target, translate.get_translation,
                                             show_names=settings["obs_chat_names"])
            now = time.monotonic()
            if not desktop_app._obs_chat_update_due(last, last_at, source, text, now):
                return
            try:
                obs_ctrl.set_text_source(source, text)
            except Exception as exc:
                with self.lock:
                    self.obs_state.update(pushed=None, text_error=i18n.translate(
                        "Couldn't update OBS chat text: {err}", settings["ui_language"], err=exc))
                return
            with self.lock:
                self.obs_state.update(pushed=(source, text), pushed_at=now, text_error="")
        finally:
            self.obs_state["pushing"] = False

    def load_saved(self):
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            settings, targets = saved["settings"], saved["targets"]
            if not isinstance(settings, dict) or not isinstance(targets, list):
                raise TypeError("unexpected structure")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("Ignoring unreadable HTML dashboard settings %s: %s", self.path, exc)
            return
        for key, value in settings.items():
            if key in DEFAULTS and type(value) is type(DEFAULTS[key]):
                self.settings[key] = value
        encrypted = saved.get("transcription_api_key_dpapi", "")
        if isinstance(encrypted, str) and encrypted:
            from src.api_secrets import unprotect
            self.transcription_api_key_dpapi = encrypted
            try:
                self.transcription_api_key = unprotect(encrypted)
            except ValueError as exc:
                self.transcription_key_error = str(exc)
                log.error("%s", self.transcription_key_error)
        # Out-of-range values would make every later settings save fail validation.
        try:
            self.validate_settings(self.settings)
        except ValueError as exc:
            log.warning("Resetting invalid HTML dashboard settings: %s", exc)
            self.settings = deepcopy(DEFAULTS)
        seen = set()
        for target in targets:
            if (
                isinstance(target, dict) and target.get("platform") in user_login.SITES
                and isinstance(target.get("target"), str) and target["target"]
                and target.get("id") == f"{target['platform']}:{target['target']}"
                and target["id"] not in seen
            ):
                seen.add(target["id"])
                self.targets.append({
                    "id": target["id"], "platform": target["platform"],
                    "target": target["target"], "enabled": target.get("enabled") is not False,
                })
        armed, thanked = saved.get("record_armed", []), saved.get("thanked", [])
        if isinstance(armed, list):
            self.record_armed = {room for room in armed if room in seen}
        if isinstance(thanked, list):
            self.thanked = {str(item) for item in thanked[-5000:] if isinstance(item, (str, int))}

    @staticmethod
    def validate_settings(settings):
        caption_options(settings)
        if not 10 <= settings["max_messages"] <= 200:
            raise ValueError("Message limit must be 10–200.")
        if settings["tts_language"] not in tts.LANGUAGES or not 80 <= settings["tts_rate"] <= 300:
            raise ValueError("Invalid speech language or rate.")
        if not 0 <= settings["tts_volume"] <= 100:
            raise ValueError("Speech volume must be 0–100.")
        if settings["translate_target"] not in ("en", "zh-CN", "zh-TW", "ja", "ko"):
            raise ValueError("Invalid translation target.")
        if settings["record_quality"] not in (10000, 400, 250, 150, 80):
            raise ValueError("Invalid recording quality.")
        if settings["ui_language"] not in i18n.UI_LANGUAGES:
            raise ValueError("Invalid interface language.")
        for key in ("visible_sites", "send_sites"):
            values = settings[key]
            if len(set(values)) != len(values) or any(value not in SITES for value in values):
                raise ValueError("Invalid site list.")
        rooms = settings["selected_rooms"]
        if any(site not in SITES or not isinstance(room, str) or len(room) > 600
               for site, room in rooms.items()):
            raise ValueError("Invalid chat room selection.")
        if not 10 <= settings["hotspot_window"] <= 300:
            raise ValueError("Hotspot window must be 10–300 seconds.")
        if not 1 <= settings["overlay_count"] <= 50 or not 0 <= settings["overlay_paid_count"] <= 50:
            raise ValueError("Overlay counts must be 1–50 chat and 0–50 paid messages.")
        if len(settings["overlay_custom_text"]) > 300 or len(settings["obs_chat_source"]) > 300:
            raise ValueError("Text is too long.")

    def error(self, message):
        log.error("%s", message)
        with self.lock:
            self.errors.append({"time": time.time(), "message": str(message)})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "settings": self.settings, "targets": self.targets,
            "record_armed": sorted(self.record_armed), "thanked": sorted(self.thanked),
            "transcription_api_key_dpapi": self.transcription_api_key_dpapi,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def save_site_cookies(self, logins, names):
        from src.api_secrets import protect
        encrypted = {}
        try:
            for site in user_login.SITES:
                if logins.get(site):
                    payload = {"cookies": logins[site], "name": names.get(site, "")}
                    if site == "youtube":
                        payload["page_id"] = logins.get("youtube_page_id", "")
                    encrypted[site] = protect(json.dumps(payload))
        except ValueError:
            raise ValueError("Could not encrypt site cookies for this Windows account.") from None
        path = self.path.with_name("html_site_cookies.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(encrypted), encoding="utf-8")
        temporary.replace(path)

    def load_site_cookies(self):
        from src.api_secrets import unprotect
        path = self.path.with_name("html_site_cookies.json")
        if not path.exists():
            return
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(stored, dict):
                raise ValueError("Invalid cookie storage.")
        except (OSError, ValueError):
            self.error("Could not read saved site cookies. Import cookies again.")
            return
        for site in user_login.SITES:
            if site not in stored:
                continue
            try:
                payload = json.loads(unprotect(stored[site]))
                cookies, name = payload["cookies"], payload["name"]
                page_id = payload.get("page_id", "")
                if (not isinstance(cookies, dict) or not cookies
                        or any(not isinstance(key, str) or not isinstance(value, str)
                               for key, value in cookies.items())
                        or not isinstance(name, str) or not isinstance(page_id, str)):
                    raise ValueError("Invalid cookie data.")
            except (ValueError, TypeError, KeyError, AttributeError):
                self.error(f"Could not decrypt saved {site} cookies. Import cookies again on this Windows account.")
                continue
            self.logins[site], self.login_names[site] = cookies, name
            if site == "youtube" and page_id:
                self.logins["youtube_page_id"] = page_id

    def receive_statuses(self, statuses):
        with self.lock:
            previous = self.statuses
            monitored = {target["id"] for target in self.targets}
            self.record_events(RoomEvents.statuses(
                {room: info for room, info in statuses.items() if room in monitored},
                previous, time.time()))
            self.statuses = deepcopy(statuses)
            for room_id, info in statuses.items():
                if (info.get("live") and not previous.get(room_id, {}).get("live")
                        and self.settings["notify_live"]):
                    target = next((item for item in self.targets if item["id"] == room_id), {})
                    details = desktop_app._live_notification_details(
                        target, info, str(info.get("video_id") or ""))
                    self.sequence += 1
                    self.notifications.append({
                        "id": self.sequence, "room": room_id,
                        **details,
                    })
                if room_id in self.record_armed or room_id in self.recorders:
                    changed = info.get("live") != previous.get(room_id, {}).get("live")
                    busy = any(job["kind"] == f"record:{room_id}" and job["status"] == "running"
                               for job in self.jobs.values())
                    recorder = self.recorders.get(room_id)
                    running = bool(recorder and recorder.is_running)
                    wanted = room_id in self.record_armed and bool(info.get("live"))
                    due = time.monotonic() - self.record_attempts.get(room_id, float("-inf")) >= 5
                    if not busy and (changed or (running != wanted and due)):
                        self.record_attempts[room_id] = time.monotonic()
                        self.submit("record", f"record:{room_id}", lambda room_id=room_id:
                                    self.sync_recording(room_id))

    def selected_room(self, message, settings):
        """Desktop rule: only the selected room of each visible site is read and shown."""
        platform = message.get("platform")
        return (platform in settings["visible_sites"]
                and settings["selected_rooms"].get(platform) == message.get("_monitor_id"))

    def effective_rooms(self, settings=None):
        """Saved chat room per site, falling back to the first monitored room like the desktop."""
        settings = settings or self.settings
        rooms = {}
        for site in SITES:
            ids = [target["id"] for target in self.targets if target["platform"] == site]
            saved = settings["selected_rooms"].get(site)
            rooms[site] = saved if saved in ids or saved == "" else (ids[0] if ids else "")
        return rooms

    def receive_messages(self, messages):
        with self.lock:
            desktop_app._accumulate_bilibili_gift_revenue(self, messages)
            monitored = {target["id"] for target in self.targets}
            received_at = time.time()
            self.record_events([
                RoomEvents.message(message, received_at) for message in messages
                if message.get("_monitor_id") in monitored
            ])
            allowed, _ = self.filters.filter_messages(messages)
            settings = deepcopy(self.settings)
            settings["selected_rooms"] = self.effective_rooms(settings)
            targets = {target["id"]: dict(target) for target in self.targets}
            # Recorders receive every live message; their own setting decides whether XML is written.
            for message in messages:
                recorder = self.recorders.get(message.get("_monitor_id", ""))
                if (recorder is not None and recorder.is_running and not message.get("history")
                        and callable(getattr(recorder, "add_danmaku", None))):
                    recorder.add_danmaku(message)
            archive_batches = {}
            for source in allowed:
                message = dict(source)
                self.sequence += 1
                message["_html_id"] = self.sequence
                paid = tts.is_paid(message) or tts.is_gift(message)
                message["_paid"] = paid
                joined = message.get("type") == "enter"
                (self.joins if joined else self.messages).append(message)
                target = targets.get(message.get("_monitor_id"))
                if target and target["enabled"] and not joined:
                    record = {key: str(message.get(key, "")) for key in (
                        "timestamp", "author", "text", "platform", "type", "translation",
                    )}
                    archive_batches.setdefault(target["id"], []).append(record)
                if (settings["tts_enabled"] and not message.get("history")
                        and self.selected_room(message, settings)
                        and (settings["tts_joins"] if joined else settings["tts_paid"] or not paid)):
                    self.queue_speech(message, settings, paid, joined)
            for room_id, batch in archive_batches.items():
                room_name = str(self.statuses.get(room_id, {}).get("room_name") or "")
                self.pools["archive"].submit(
                    self.append_archive, targets[room_id], batch, room_name
                )
        if allowed:
            self.schedule_obs_chat()

    def record_events(self, events):
        if not events:
            return
        batch = deepcopy(events)

        def write():
            try:
                self.event_store.append(batch)
            except Exception as exc:
                with self.lock:
                    self.event_error = str(exc)
                self.error(f"Room event recording failed: {exc}")
        self.pools["events"].submit(write)

    def event_query(self, function, *args):
        # Queries share the writer queue so they include all events received before the request.
        return self.pools["events"].submit(function, *args).result()

    @staticmethod
    def event_room(data):
        room = data.get("room")
        if not isinstance(room, str) or not room or len(room) > 600:
            raise ValueError("Select a room for analysis.")
        return room

    def queue_speech(self, message, settings, paid, joined):
        """Compose speech off the worker thread, in arrival order (translation may wait briefly)."""
        text = message.get("text", "")
        if not joined and settings["tts_skip_emoji"]:
            if tts.is_emoji_only(message):
                return
            text = tts.strip_emoji(text, message.get("platform", "")) or text
        if self.speech_pending >= SPEECH_BACKLOG:
            self.error("Speech queue full; skipped incoming speech.")
            return
        self.speech_pending += 1
        self.pools["speech"].submit(self.compose_speech, message, text, settings, paid, joined)

    def compose_speech(self, message, text, settings, paid, joined):
        try:
            translate = self.translations()
            lang, author = settings["tts_language"], message.get("author", "")
            if joined:
                spoken = tts.format_join(author, lang)
                text = author
            else:
                if settings["tts_translate"] and settings["translate_enabled"]:
                    target = settings["translate_target"]
                    translate.prefetch([text], target, wait=8)
                    translated = translate.get_translation(text, target)
                    if translated:
                        text, lang = translated, target.split("-")[0]
                if paid:
                    spoken = tts.format_announcement(message.get("type", ""), author, text, lang)
                elif settings["tts_skip_name"]:
                    spoken = text
                else:
                    spoken = tts.format_message(author, text, lang)
            with self.lock:
                self.sequence += 1
                self.speech.append({
                    "id": self.sequence, "text": spoken, "paid": paid,
                    **({"text_without_name": text,
                        "text_with_name": tts.format_message(author, text, lang)}
                       if not paid and not joined else {}),
                    # Browser voices use the selected language or the shared detector.
                    "language": tts.resolve_language(lang, text),
                    "room": message.get("_monitor_id", ""), "platform": message.get("platform", ""),
                })
        except Exception as exc:
            self.error(f"Speech failed: {exc}")
        finally:
            with self.lock:
                self.speech_pending -= 1

    def append_archive(self, target, messages, room_name=""):
        try:
            platform = target["platform"]
            result = self.archive.append_messages(
                target["id"], messages, platform=platform,
                room_id=target["target"] if platform != "youtube" else "",
                channel_id=target["target"] if platform == "youtube" else "",
                room_name=room_name,
            )
            if not result["ok"]:
                raise RuntimeError(result["error"])
        except Exception as exc:
            self.error(f"Archive write failed: {exc}")

    def submit(self, pool, kind, function):
        with self.lock:
            if self.closed:
                raise ValueError("Dashboard is shutting down.")
            if any(job["kind"] == kind and job["status"] == "running"
                   for job in self.jobs.values()):
                raise ValueError(f"{kind} is already running.")
            job_id = secrets.token_hex(8)
            self.jobs[job_id] = {"kind": kind, "status": "running"}

        def run():
            try:
                result = function()
            except Exception as exc:
                self.error(f"{kind}: {exc}")
                result = {"status": "failed", "error": str(exc)}
            else:
                result = {"status": "done", "result": result}
            with self.lock:
                self.jobs[job_id].update(result)
                completed = [key for key, job in self.jobs.items()
                             if job["status"] != "running"]
                for key in completed[:-30]:
                    self.jobs.pop(key)
        self.pools[pool].submit(run)
        return {"job": job_id}

    def target(self, room_id):
        with self.lock:
            target = next((dict(t) for t in self.targets if t["id"] == room_id), None)
        if target is None:
            raise ValueError("Room no longer exists.")
        return target

    def sync_recording(self, room_id):
        from src import bili_recorder, missevan, missevan_recorder, youtube_recorder

        target = self.target(room_id)
        with self.lock:
            info = dict(self.statuses.get(room_id, {}))
            armed = room_id in self.record_armed
            recorder = self.recorders.get(room_id)
            settings = dict(self.settings)
            logins = deepcopy(self.logins)
        if not armed or not info.get("live"):
            if recorder:
                recorder.stop(wait=3)
            return {"armed": armed}
        if recorder and recorder.is_running:
            return recorder.snapshot()
        folder = settings["record_folder"] or str(self.path.parent / "recordings")
        platform, value = target["platform"], target["target"]
        common = {"name": info.get("room_name", ""), "title": info.get("title", "")}
        if platform == "bilibili":
            recorder = bili_recorder.BilibiliRecorder(
                value, folder, quality=settings["record_quality"],
                cookies=logins.get("bilibili"), save_danmaku=settings["record_danmaku"], **common,
            )
        elif platform == "missevan":
            recorder = missevan_recorder.MissEvanRecorder(
                value, folder, lambda: missevan.get_live_audio_url(value), **common,
            )
        else:
            video = info.get("video_id")
            if not video:
                from src.youtube import extract_video_id
                video = extract_video_id(value)
            if not video:
                raise ValueError("No live YouTube video resolved yet.")
            recorder = youtube_recorder.YouTubeRecorder(
                video, folder, lambda: youtube_recorder.resolve_live_source(video), **common,
            )
        with self.lock:
            # A room may go offline, be removed, or be disarmed during URL resolution.
            if self.closed or room_id not in self.record_armed or not self.statuses.get(room_id, {}).get("live"):
                return {"armed": room_id in self.record_armed}
            recorder.start()
            self.recorders[room_id] = recorder
        return recorder.snapshot()

    def render_message(self, source, settings):
        """Browser copy of a message with the desktop feed's derived fields and only trusted image URLs."""
        from src import emotes
        translate = self.translations()
        try:
            message = self.artwork.resolve(source)
        except RuntimeError as exc:
            self.error(str(exc))
            message = dict(source)
        message = dict(message)
        if settings["translate_enabled"]:
            translated = translate.get_translation(
                message.get("text", ""), settings["translate_target"]
            )
            if translated:
                message["translation"] = translated
        if (message.get("platform") == "bilibili" and not message.get("avatar")
                and str(message.get("author_id", "")).isdigit()):
            message["avatar"] = self.bilibili_avatar(str(message["author_id"]))
        for key in ("avatar", "sticker_url", "gift_animation_url"):
            message[key] = emotes.safe_chat_image_url(message.get(key, ""))
        message["membership_icon"] = emotes.safe_badge_url(message.get("membership_icon", ""))
        if isinstance(message.get("emotes"), dict):
            message["emotes"] = {
                code: url for code, raw in message["emotes"].items()
                if (url := emotes.safe_chat_image_url(raw))
            }
        text = str(message.get("text", ""))
        if message.get("platform") == "bilibili" and message.get("type") == "gift":
            text = desktop_app._localize_bilibili_gift_text(text, settings["ui_language"], i18n)
        message["_text"] = text
        message["_time"] = desktop_app._format_chat_timestamp(message.get("timestamp", ""))
        message["_amount"] = gifts.amount_label(message) if message.get("_paid") else ""
        message["_thanked"] = str(message.get("id", "")) in self.thanked
        if settings["show_reading"]:
            author = str(message.get("author", "?"))
            message["_author_readings"] = _reading(author)
            message["_text_readings"] = _reading(text)
        return message

    def bilibili_avatar(self, uid):
        """Cached Bilibili avatar URL; unknown users are looked up in the background (desktop behaviour)."""
        if uid == "0":
            return ""
        if uid in self.avatar_cache:
            return self.avatar_cache[uid]
        failed = self.avatar_failures.get(uid)
        if uid not in self.avatar_pending and (failed is None or time.monotonic() - failed >= 300):
            self.avatar_pending.add(uid)
            self.pools["avatars"].submit(self.fetch_avatar, uid)
        return ""

    def fetch_avatar(self, uid):
        from src import bilibili
        try:
            url = bilibili.get_user_avatar(uid)
        except Exception as exc:
            log.debug("Bilibili avatar lookup failed for %s: %s", uid, exc)
            url = ""
        with self.lock:
            self.avatar_pending.discard(uid)
            if url:
                if len(self.avatar_cache) >= 500:
                    self.avatar_cache.pop(next(iter(self.avatar_cache)))
                self.avatar_cache[uid] = url
                self.avatar_failures.pop(uid, None)
            else:
                self.avatar_failures[uid] = time.monotonic()

    @staticmethod
    def recording_status(recorder, language):
        """Recorder snapshot plus the desktop monitor card's status line."""
        state = recorder.snapshot()
        label = ""
        if state.get("running"):
            status = state.get("status", "")
            if status == "Recording":
                label = i18n.translate("\u23fa Recording", language)
                if state.get("started_at"):
                    label += " " + desktop_app._format_record_duration(time.time() - state["started_at"])
                label += " \u00b7 " + desktop_app._format_record_size(state.get("total_bytes", 0))
                if state.get("qn"):
                    label += f" \u00b7 qn {state['qn']}"
            else:
                label = "\u23fa " + i18n.translate(status, language)
        elif state.get("files"):
            label = i18n.translate("Last recording: {size}", language,
                                   size=desktop_app._format_record_size(state.get("total_bytes", 0)))
        return {"label": label, "detail": str(state.get("error") or state.get("file") or ""),
                "running": bool(state.get("running"))}

    def snapshot(self):
        with self.lock:
            settings = deepcopy(self.settings)
            settings["selected_rooms"] = rooms = self.effective_rooms(settings)
            limit = settings["max_messages"]
            selected = [m for m in self.messages if self.selected_room(m, settings)]
            feeds = {
                "messages": [m for m in selected if not m.get("_paid")][-limit:],
                "paid": [m for m in selected if m.get("_paid")][-limit:],
                "joins": [m for m in self.joins if self.selected_room(m, settings)][-limit:],
            }
            rendered = {key: [self.render_message(m, settings) for m in items]
                        for key, items in feeds.items()}
            if settings["translate_enabled"]:
                translate = self.translations()
                missing = [m.get("text", "") for key in ("messages", "paid") for m in rendered[key]
                           if m.get("text") and not m.get("translation")]
                if missing:
                    translate.prefetch(missing, settings["translate_target"])
            return {
                "targets": deepcopy(self.targets), "settings": settings,
                "statuses": deepcopy(self.statuses), **rendered,
                "bilibili_gift_revenue": {
                    room: gifts.format_amount("¥", amount)
                    for room, amount in self._bilibili_gift_revenue.items()
                },
                "speech": list(self.speech),
                "errors": list(self.errors), "notifications": list(self.notifications),
                "jobs": deepcopy(self.jobs), "filters": deepcopy(self.filters.to_dict()),
                "recording": {key: self.recording_status(recorder, settings["ui_language"])
                              for key, recorder in self.recorders.items()},
                "record_armed": sorted(self.record_armed),
                "transcription": self.transcriber.snapshot() if self.transcriber else None,
                "transcription_api": {"key_saved": bool(self.transcription_api_key),
                                      "error": self.transcription_key_error},
                "obs": {key: value for key, value in self.obs_state.items()
                        if key not in ("pushed", "pushed_at")},
                "rooms": rooms,
                "event_recording": {"error": self.event_error},
                "logins": {
                    site: {"signed_in": bool(self.logins.get(site)),
                           "name": self.login_names.get(site, ""),
                           **({"page_id": str(self.logins.get("youtube_page_id") or "")}
                              if site == "youtube" else {})}
                    for site in user_login.SITES
                },
                "totals": gifts.platform_totals(
                    [m for m in self.messages if m.get("_paid")], user_login.SITES),
            }

    def action(self, data):
        action = data.get("action")
        if action == "transcription_settings":
            with self.lock:
                settings, key = self.transcription_configuration(data)
                from src.api_secrets import protect
                encrypted = protect(key) if key else ""
                previous = (self.settings, self.transcription_api_key_dpapi)
                self.settings, self.transcription_api_key_dpapi = settings, encrypted
                try:
                    self.save()
                except OSError:
                    self.settings, self.transcription_api_key_dpapi = previous
                    raise
                self.transcription_api_key, self.transcription_key_error = key, ""
            return {"ok": True}
        if action in ("transcription_models", "transcription_test"):
            with self.lock:
                settings, key = self.transcription_configuration(data)
                options = caption_options(settings, key)
            if action == "transcription_models":
                from src.openai_compatible_translate import list_models
                return self.submit("network", action, lambda: {
                    "models": list_models(options.api_base, options.api_key)})
            return self.submit("network", action, lambda: self.test_transcription_api(settings, options))
        if action == "settings":
            values = data.get("values", {})
            if not isinstance(values, dict):
                raise ValueError("Settings must be an object.")
            with self.lock:
                settings = deepcopy(self.settings)
                for key, value in values.items():
                    if key not in DEFAULTS or type(value) is not type(DEFAULTS[key]):
                        raise ValueError(f"Invalid setting: {key}")
                    settings[key] = value
                self.validate_settings(settings)
                if any(settings[key] != self.settings[key] for key in (
                        "obs_chat_source", "obs_chat_names", "selected_rooms", "visible_sites")):
                    self.obs_state["pushed"] = None
                self.settings = settings
                self.save()
            return {"ok": True}
        if action == "add_room":
            from src import bilibili, missevan, youtube, youtube_web
            platform = data.get("platform")
            value = str(data.get("target", "")).strip()
            if platform == "bilibili":
                value = bilibili.parse_room_id(value)
            elif platform == "missevan":
                value = missevan.parse_room_id(value)
            elif platform == "youtube":
                value = youtube.extract_video_id(value) or youtube_web.channel_url(value)
            else:
                raise ValueError("Invalid platform.")
            if not value or len(value) > 500:
                raise ValueError("Enter a valid room or channel ID/URL.")
            with self.lock:
                room_id = f"{platform}:{value}"
                if any(t["id"] == room_id for t in self.targets):
                    raise ValueError("Room already added.")
                if len(self.targets) >= 50:
                    raise ValueError("At most 50 monitored rooms are supported.")
                self.targets.append({
                    "id": room_id, "platform": platform, "target": value, "enabled": True,
                })
                self.save()
                if self.worker:
                    self.worker.update_targets(self.targets)
            return {"ok": True}
        if action in ("remove_room", "allow_saving", "record"):
            room_id = data.get("room")
            self.target(room_id)
            if action == "record":
                with self.lock:
                    if data.get("enabled") is True:
                        self.record_armed.add(room_id)
                    else:
                        self.record_armed.discard(room_id)
                    self.save()
                return self.submit("record", f"record:{room_id}", lambda: self.sync_recording(room_id))
            with self.lock:
                if action == "remove_room":
                    self.targets = [t for t in self.targets if t["id"] != room_id]
                    self.record_armed.discard(room_id)
                    recorder = self.recorders.pop(room_id, None)
                    if recorder:
                        self.pools["record"].submit(recorder.stop, 3)
                else:
                    for target in self.targets:
                        if target["id"] == room_id:
                            target["enabled"] = data.get("enabled") is True
                self.save()
                if self.worker:
                    self.worker.update_targets(self.targets)
            return {"ok": True}
        if action == "import_cookies":
            text = data.get("text", "")
            if not isinstance(text, str) or len(text) > 1_000_000:
                raise ValueError("Cookie text must be at most 1 MB.")
            return self.submit("login", "import_cookies", lambda: self.import_logins(text))
        if action == "clear_login":
            site = data.get("site")
            if site not in (*user_login.SITES, "all"):
                raise ValueError("Invalid cookie platform.")
            with self.lock:
                logins, names = deepcopy(self.logins), deepcopy(self.login_names)
                for name in user_login.SITES if site == "all" else (site,):
                    logins.pop(name, None)
                    names.pop(name, None)
                    if name == "youtube":
                        logins.pop("youtube_page_id", None)
                self.save_site_cookies(logins, names)
                self.logins, self.login_names = logins, names
                if self.worker:
                    self.worker.update_logins(deepcopy(self.logins))
            return {"ok": True}
        if action == "archives":
            return self.submit("archive", "archives", self.load_archives)
        if action == "delete_archive":
            session_id = str(data.get("session", ""))
            def delete():
                result = self.archive.delete_session(session_id)
                if not result["ok"]:
                    raise RuntimeError(result["error"])
                return self.load_archives()
            return self.submit("archive", "archives", delete)
        if action == "moderation":
            with self.lock:
                if "unblock" in data:
                    key = str(data["unblock"])
                    if data.get("kind") == "name":
                        self.filters.unblock_name(key)
                    else:
                        self.filters.unblock_user(key)
                    return {"ok": True}
                pattern = str(data.get("pattern", "")).strip()
                if not pattern or len(pattern) > 300:
                    raise ValueError("Enter a pattern of at most 300 characters.")
                allow = data.get("allow") is True
                if data.get("remove"):
                    (self.filters.remove_allow_pattern if allow else self.filters.remove_block_pattern)(pattern)
                else:
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        raise ValueError(f"Invalid pattern: {exc}") from None
                    (self.filters.add_allow_pattern if allow else self.filters.add_block_pattern)(pattern)
            return {"ok": True}
        if action == "message":
            return self.message_action(data)
        if action == "clear_chat":
            with self.lock:
                self.messages.clear()
                self.joins.clear()
            return {"ok": True}
        if action == "send":
            text = str(data.get("text", "")).strip()
            if not text or len(text) > 500:
                raise ValueError("Message must be 1–500 characters.")
            sites = data.get("sites")
            if not isinstance(sites, list) or not sites or any(site not in SITES for site in sites):
                raise ValueError("Choose at least one site to send to.")
            with self.lock:
                rooms = self.effective_rooms()
                # Desktop rule: each checked site sends to its selected chat room, if that room is enabled.
                destinations = {
                    site: next((dict(t) for t in self.targets
                                if t["id"] == rooms[site] and t["enabled"]), None)
                    for site in dict.fromkeys(sites)
                }
                statuses = deepcopy(self.statuses)
                logins = deepcopy(self.logins)

            def send():
                from src import bilibili, missevan, youtube
                results = {}
                with user_login.using(logins):
                    for site, target in destinations.items():
                        if target is None:
                            results[site] = {"ok": False, "error": "Select an enabled room for this site in Chat rooms."}
                            continue
                        value = target["target"]
                        try:
                            if site == "youtube":
                                video = statuses.get(target["id"], {}).get("video_id") or youtube.extract_video_id(value)
                                ok, error = (youtube.send_chat(f"web:{video}", video, text) if video
                                             else (False, "No active YouTube live chat."))
                            elif site == "bilibili":
                                ok, error = bilibili.send_danmaku(value, text)
                            else:
                                ok, error = missevan.send_message(value, text)
                        except Exception as exc:
                            ok, error = False, str(exc)
                        results[site] = {"ok": bool(ok), "error": "" if ok else str(error or "")}
                return results
            return self.submit("network", "send", send)
        if action == "obs":
            return self.submit("obs", "obs", lambda: self.obs_action(data))
        if action == "transcription":
            return self.submit("transcription", "transcription", lambda: self.transcribe(data))
        if action == "youtube_accounts":
            cookies = deepcopy(self.logins.get("youtube") or {})
            if not cookies:
                raise ValueError("Import YouTube cookies first.")

            def accounts():
                from src import youtube_web
                result = youtube_web.list_channels(cookies)
                if result.get("error"):
                    raise RuntimeError(f"Could not list YouTube accounts: {result['error']}")
                with self.lock:
                    selected = str(self.logins.get("youtube_page_id") or "")
                return {"channels": result.get("channels", []), "selected": selected}
            return self.submit("login", "youtube_accounts", accounts)
        if action == "youtube_account":
            from src import youtube_web
            page_id = str(data.get("page_id", ""))
            if len(page_id) > 200:
                raise ValueError("Invalid YouTube account.")
            with self.lock:
                if not self.logins.get("youtube"):
                    raise ValueError("Import YouTube cookies first.")
                logins = deepcopy(self.logins)
                with user_login.using(logins):
                    youtube_web.select_channel(page_id)
                self.save_site_cookies(logins, self.login_names)
                self.logins = logins
                if self.worker:
                    self.worker.update_logins(deepcopy(self.logins))
                return {"ok": True, "page_id": str(self.logins.get("youtube_page_id") or "")}
        if action == "emotes":
            return self.submit("emotes", "emotes", lambda: self.load_emotes(str(data.get("site", ""))))
        if action == "use_emote":
            return self.submit("network", "use_emote", lambda: self.use_emote(data))
        if action == "overlay":
            return self.submit("network", "overlay", lambda: self.overlay_url(data))
        if action == "analytics":
            return self.analytics(self.event_room(data))
        if action == "export_hotspots":
            return self.export_hotspots(str(data.get("format", "")), self.event_room(data))
        if action == "event_rooms":
            return self.event_query(self.event_store.rooms)
        if action == "room_events":
            return self.event_query(self.event_store.page, self.event_room(data),
                                    data.get("before", 0), data.get("limit", 100))
        if action == "delete_room_events":
            return self.event_query(self.event_store.delete, self.event_room(data))
        raise ValueError("Unknown action.")

    def message_action(self, data):
        """Block / Mute / Thank a message by id; Read and Copy run in the browser."""
        command, message_id = data.get("command"), data.get("id")
        with self.lock:
            message = next((m for m in (*self.messages, *self.joins)
                            if m.get("_html_id") == message_id), None)
            if message is None:
                raise ValueError("Message no longer exists.")
            message = dict(message)
            if command == "block":
                author_id = str(message.get("author_id", ""))
                if author_id and author_id != "0":
                    self.filters.block_user(author_id, name=message.get("author", ""),
                                            platform=message.get("platform", ""))
                else:
                    self.filters.block_name(message.get("author", ""))
                for feed in (self.messages, self.joins):
                    kept = [m for m in feed if self.filters.check(m).allowed]
                    feed.clear()
                    feed.extend(kept)
                return {"ok": True}
            if command == "thank":
                key = str(message.get("id", ""))
                if not key or not message.get("_paid"):
                    raise ValueError("Select a gift or paid message first.")
                self.thanked.symmetric_difference_update({key})
                self.save()
                return {"ok": True, "thanked": key in self.thanked}
            if command == "read":
                lang = self.settings["tts_language"]
                text = str(message.get("translation") or message.get("text") or "")
                spoken = text if self.settings["tts_skip_name"] else tts.format_message(
                    message.get("author", ""), text, lang)
                self.sequence += 1
                self.speech.append({
                    "id": self.sequence, "text": spoken, "paid": bool(message.get("_paid")),
                    "text_without_name": text,
                    "text_with_name": tts.format_message(message.get("author", ""), text, lang),
                    "language": tts.resolve_language(lang, text), "manual": True,
                    "room": message.get("_monitor_id", ""), "platform": message.get("platform", ""),
                })
                return {"ok": True}
            if command != "mute":
                raise ValueError("Unknown message action.")
            if message.get("platform") != "bilibili":
                raise ValueError("Select a Bilibili message first.")
            author_id = str(message.get("author_id", ""))
            if not author_id.isdigit() or author_id == "0":
                raise ValueError("This Bilibili message does not expose a muteable user ID.")
            target = next((t for t in self.targets if t["id"] == message.get("_monitor_id")), None)
            room = str(message.get("room_id") or (target["target"] if target else ""))
            logins = deepcopy(self.logins)

        def mute():
            from src import bilibili
            with user_login.using(logins):
                ok, error = bilibili.block_user(bilibili.parse_room_id(room), int(author_id))
            if not ok:
                raise RuntimeError(error)
            return {"muted": message.get("author", "")}
        return self.submit("network", "mute", mute)

    def emote_room(self, site):
        with self.lock:
            room = self.effective_rooms()[site]
            target = next((dict(t) for t in self.targets if t["id"] == room), None)
            status = dict(self.statuses.get(room, {}))
            logins = deepcopy(self.logins)
        return target, status, logins

    def load_emotes(self, site):
        """Desktop emote picker data: YouTube channel stamps, Bilibili emotes, MissEvan stickers / kaomoji."""
        import hashlib
        from concurrent.futures import ThreadPoolExecutor as Pool
        from src import bilibili, emotes, missevan, youtube_web

        if site == "kaomoji":
            return {"site": site, "groups": [{"name": "Presets", "entries": [
                {"name": face, "value": face} for face in missevan.preset_kaomoji()]}], "error": ""}
        if site not in SITES:
            raise ValueError("Invalid emote site.")
        target, status, logins = self.emote_room(site)
        if target is None:
            raise ValueError("Select a monitored room for this site in Chat rooms first.")
        fingerprint = hashlib.sha256(json.dumps(logins, sort_keys=True).encode()).hexdigest()
        identity = status.get("video_id", "") if site == "youtube" else target["target"]
        if not identity:
            raise ValueError("Connect a YouTube live stream in Stream Monitoring first.")
        key = "html:" + hashlib.sha256(f"{site}\0{identity}\0{fingerprint}".encode()).hexdigest()
        cached, _ = self.emote_cache.get(key)
        error = ""
        if isinstance(cached, list):
            groups = cached
        else:
            groups = []
            with user_login.using(logins):
                if site == "youtube":
                    stamps = youtube_web.channel_emojis(identity, fetch=True)
                    groups.append({"name": "Channel stamps",
                                   "entries": [{**stamp, "kind": "youtube"} for stamp in stamps]})
                elif site == "bilibili":
                    packs, error = bilibili.get_emoticons(identity)
                    for pack in packs or []:
                        if isinstance(pack, dict):
                            groups.append({"name": str(pack.get("name") or "Emotes"), "entries": [
                                {**emote, "kind": "bilibili"} for emote in pack.get("emotes", [])]})
                else:
                    packages, error = missevan.get_sticker_tabs(identity)

                    def fetch(package):
                        package_id = package.get("package_id") or package.get("id")
                        if not package_id:
                            return None, "MissEvan returned a sticker package without an ID."
                        with user_login.using(logins):
                            stickers, package_error = missevan.get_stickers(identity, int(package_id))
                        name = str(package.get("name") or package.get("package_name") or package_id)
                        return {"name": name, "entries": [
                            {**sticker, "kind": "missevan", "_package_id": int(package_id)}
                            for sticker in stickers]}, package_error

                    with Pool(max_workers=4) as pool:
                        for group, package_error in pool.map(fetch, packages or []):
                            if group:
                                groups.append(group)
                            error = error or package_error
            groups = [group for group in groups if group["entries"]]
            if not error and groups:
                self.emote_cache.set(key, groups)
        for group in groups:
            entries = []
            for entry in group["entries"][:500]:
                image = (entry.get("url") or entry.get("image_url") or entry.get("sticker_url")
                         or entry.get("icon_url") or entry.get("image") or "")
                label = str(entry.get("name") or entry.get("emoji") or entry.get("description")
                            or entry.get("code") or entry.get("sticker_id") or entry.get("id") or "Emote")
                entries.append({
                    "label": label, "code": str(entry.get("code") or ""),
                    "value": str(entry.get("value") or ""), "kind": entry.get("kind", ""),
                    "unique": str(entry.get("unique") or ""),
                    "sticker_id": str(entry.get("sticker_id") or entry.get("id") or ""),
                    "package_id": entry.get("_package_id", 0),
                    "locked": bool(entry.get("locked")), "hint": str(entry.get("hint") or ""),
                    "image": emotes.safe_chat_image_url(image),
                })
            group["entries"] = entries
        return {"site": site, "groups": groups, "error": error or ""}

    def use_emote(self, data):
        from src import bilibili, missevan
        site = data.get("site")
        if site not in ("bilibili", "missevan"):
            raise ValueError("Invalid emote site.")
        target, _, logins = self.emote_room(site)
        if target is None:
            raise ValueError("Select a monitored room for this site in Chat rooms first.")
        with user_login.using(logins):
            if site == "bilibili":
                ok, error = bilibili.send_emoticon(target["target"], str(data.get("unique", "")))
            else:
                try:
                    package_id, sticker_id = int(data.get("package_id")), int(data.get("sticker_id"))
                except (TypeError, ValueError):
                    raise ValueError("MissEvan returned a sticker without an ID.") from None
                ok, error = missevan.send_sticker(target["target"], package_id, sticker_id)
        if not ok:
            raise RuntimeError(error)
        return {"sent": site}

    def overlay_url(self, data):
        """Start the shared overlay server and build the same OBS browser-source URL as the desktop."""
        from urllib.parse import urlencode
        from src import config, overlay_server, youtube, youtube_web
        rooms = data.get("rooms")
        if not isinstance(rooms, dict):
            raise ValueError("Select at least one monitored room for the overlay.")
        with self.lock:
            settings = dict(self.settings)
            targets = {t["id"]: dict(t) for t in self.targets}
        selected = {}
        for site, short in (("youtube", "yt"), ("bilibili", "bili"), ("missevan", "me")):
            target = targets.get(rooms.get(site))
            if target and target["platform"] == site:
                value = target["target"]
                if site == "youtube":
                    value = youtube_web.channel_url(value) or youtube.extract_video_id(value)
                if value:
                    selected[short] = value
        if not selected:
            raise ValueError("Select at least one monitored room for the overlay.")
        host = config.OVERLAY_PUBLIC_URL or (
            f"http://{'127.0.0.1' if config.OVERLAY_HOST in ('0.0.0.0', '::') else config.OVERLAY_HOST}"
            f":{config.OVERLAY_PORT}"
        )
        query = {
            **selected, "n": settings["overlay_count"], "sc": settings["overlay_paid_count"],
            "names": 1 if settings["overlay_show_names"] else 0,
            "text": settings["overlay_custom_text"].strip(),
        }
        if settings["overlay_translate"]:
            query["tr"] = settings["translate_target"]
            query["translation_source"] = self.overlay_translation_id
            overlay_server.register_translation_source(self.overlay_translation_id, self.translations)
        overlay_server.ensure_started()
        return {"url": f"{host.rstrip('/')}/overlay?{urlencode(query)}"}

    def analytics(self, room):
        """All persisted events for one room, independent of display filters and restarts."""
        from src import highlights
        with self.lock:
            window = self.settings["hotspot_window"]
        result = self.event_query(self.event_store.analytics, room)
        for row in result["rows"]:
            row[1] = room.partition(":")[0]
        hotspots, _ = self.event_query(self.event_store.hotspots, room, window)
        result["rows"] += [["Hotspot", "", clip["score"], highlights.summary(clip)] for clip in hotspots]
        result["hotspots"] = len(hotspots)
        return result

    def export_hotspots(self, kind, room):
        from src import highlights
        if kind not in ("csv", "edl"):
            raise ValueError("Unknown export format.")
        with self.lock:
            window = self.settings["hotspot_window"]
        hotspots, origin = self.event_query(self.event_store.hotspots, room, window)
        if not hotspots:
            raise ValueError("No chat hotspots are available to export.")
        if kind == "csv":
            data = highlights.to_csv(hotspots)
        else:
            data = highlights.to_edl(hotspots, origin)
        return {"text": data.decode("utf-8"), "filename": f"chat-hotspots.{kind}"}

    def import_logins(self, text):
        """Verify every site found in pasted cookies, or in local browsers when nothing is pasted."""
        from src import browser_cookies as bc, missevan, youtube_web

        domains = {"youtube": bc.SITES["YouTube"], "bilibili": bc.SITES["Bilibili"],
                   "missevan": bc.SITES["MissEvan"]}
        candidates = {site: [] for site in domains}
        browser_errors = {}
        if text.strip():
            for site, domain in domains.items():
                try:
                    cookies = bc.parse_cookie_text(text, domain)
                except bc.CookieReadError as exc:
                    raise ValueError(str(exc)) from exc
                if cookies:
                    candidates[site].append(("pasted", cookies))
        else:
            for browser, loader in bc.BROWSERS.items():
                for site, domain in domains.items():
                    try:
                        cookies = bc.read_cookies(loader, domain)
                    except bc.CookieReadError as exc:
                        # The same profile/encryption problem affects every site in this browser.
                        browser_errors[browser] = str(exc)
                        break
                    if cookies:
                        candidates[site].append((browser, cookies))

        # MissEvan's login cookie names are not fixed here, so its server check decides.
        required = {
            "bilibili": ("SESSDATA",),
            "youtube": ("SAPISID", "__Secure-3PAPISID"),
        }

        def verify(site, cookies):
            if site == "bilibili":
                result = bc.verify_bilibili_login(cookies)
                return result, result.get("uname", ""), bc.save_bilibili_credentials
            if site == "missevan":
                result = missevan.verify_login(cookies)
                return result, result.get("username", ""), missevan.save_login
            result = youtube_web.verify_login(cookies)
            return result, result.get("name", ""), youtube_web.save_login

        def check(site):
            reason = "No login cookies found."
            for source, cookies in candidates[site]:
                if site in required and not any(cookies.get(name) for name in required[site]):
                    continue
                result, name, save = verify(site, cookies)
                if result.get("is_login"):
                    stored = {}
                    with user_login.using(stored):
                        save(cookies)
                    return site, {"name": name, "source": source, "cookies": stored[site]}
                reason = result.get("error") or "The site rejected these cookies (expired or signed out)."
            return site, {"error": reason}

        # Each verification is a network request; check the three sites concurrently.
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="html-login-verify") as pool:
            results = dict(pool.map(check, domains))
        signed_in = {site: result for site, result in results.items() if "cookies" in result}
        with self.lock:
            logins, names = deepcopy(self.logins), deepcopy(self.login_names)
            for site, result in signed_in.items():
                logins[site] = result.pop("cookies")
                names[site] = result["name"]
                if site == "youtube":
                    logins.pop("youtube_page_id", None)
            if signed_in:
                self.save_site_cookies(logins, names)
                self.logins, self.login_names = logins, names
            if signed_in and self.worker:
                self.worker.update_logins(deepcopy(self.logins))
        return {
            "signed_in": signed_in,
            "failed": {site: result["error"] for site, result in results.items() if "error" in result},
            "browser_errors": browser_errors,
        }

    def load_archives(self):
        result = self.archive.load_archive()
        if not result["ok"]:
            raise RuntimeError(result["error"])
        sessions = result["archive"]["sessions"]
        return [
            {**session, "messages": list(reversed(session["messages"][-500:]))}
            for session in reversed(sessions)
        ]

    def obs_action(self, data):
        from src import obs_ctrl
        command = data.get("command", "status")
        obs_ctrl.retry_now()
        if command == "status":
            if not self.refresh_obs():
                raise ConnectionError(self.obs_state.get("error") or "OBS is not connected. Check OBS WebSocket settings.")
            return {"connected": True}
        commands = {
            "start_record": obs_ctrl.start_recording, "stop_record": obs_ctrl.stop_recording,
            "start_stream": obs_ctrl.start_stream, "stop_stream": obs_ctrl.stop_stream,
        }
        if command in commands:
            if not commands[command]():
                raise RuntimeError(f"OBS {command} failed.")
        elif command == "scene":
            if not obs_ctrl.switch_scene(str(data.get("name", ""))):
                raise RuntimeError("OBS scene switch failed.")
        elif command == "text":
            obs_ctrl.set_text_source(str(data.get("name", "")), str(data.get("text", "")))
        elif command == "source":
            if not obs_ctrl.set_source_visibility(str(data.get("scene", "")), str(data.get("name", "")),
                                                  data.get("visible") is True):
                raise RuntimeError("OBS source visibility change failed.")
        else:
            raise ValueError("Unknown OBS command.")
        self.refresh_obs()
        return {"ok": True}

    def translations(self):
        """Replace provider/cache atomically when shared API settings change."""
        from src.translate import TranslationClient
        with self.lock:
            options = caption_options(self.settings, self.transcription_api_key)
            client = self.translation_client
            if client is None or any(getattr(client.options, key) != getattr(options, key)
                                     for key in ("provider", "api_base", "api_model", "api_key",
                                                 "background", "glossary")):
                self.translation_client = client = TranslationClient(options, self.error)
            return client

    def translate_text(self, text, target, *, context=()):
        return self.translations().translate(text, target, context=context)

    def transcription_configuration(self, data):
        values = data.get("values", {})
        if not isinstance(values, dict):
            raise ValueError("Settings must be an object.")
        settings = deepcopy(self.settings)
        for key, value in values.items():
            if key not in TRANSCRIPTION_DEFAULTS or type(value) is not type(TRANSCRIPTION_DEFAULTS[key]):
                raise ValueError(f"Invalid transcription setting: {key}")
            settings[key] = value
        key = data.get("api_key", "")
        clear = data.get("clear_api_key", False)
        if not isinstance(key, str) or type(clear) is not bool:
            raise ValueError("Invalid API key option.")
        key = "" if clear else key.strip() or self.transcription_api_key
        if self.transcription_key_error and not clear and not data.get("api_key"):
            raise ValueError(self.transcription_key_error)
        self.validate_settings(settings)
        caption_options(settings, key)
        return settings, key

    @staticmethod
    def test_transcription_api(settings, options):
        from src.openai_compatible_translate import translate_batch
        try:
            result = translate_batch(
                ["Hello"], settings["transcribe_target_language"],
                api_base=options.api_base, api_key=options.api_key, model=options.api_model,
                background=options.background, glossary=options.glossary,
            )[0][0]
        except Exception as exc:
            log.error("Transcription API test failed (%s).", type(exc).__name__)
            raise ValueError("Translation API request failed. Check the URL, model ID and API key.") from None
        if not result.strip():
            raise ValueError("The translation service returned an empty result.")
        return {"text": result}

    def transcribe(self, data):
        from src import bilibili, missevan, transcription, youtube
        from src.caption_engine import StreamingTranscriber
        if data.get("command") == "stop":
            if self.transcriber:
                self.transcriber.stop()
            return {"ok": True}
        if self.transcriber and self.transcriber.is_running:
            raise ValueError("Stop the current transcription first.")
        with self.lock:
            settings = deepcopy(self.settings)
            options = caption_options(settings, self.transcription_api_key)
            if settings["transcribe_translate"] and options.provider == "openai_compatible" and self.transcription_key_error:
                raise ValueError(self.transcription_key_error)
        target = self.target(data.get("room"))
        platform, value = target["platform"], target["target"]
        if platform == "youtube":
            value = self.statuses.get(target["id"], {}).get("video_id") or youtube.extract_video_id(value)
            if not value:
                raise ValueError("No live YouTube video resolved yet.")
            resolver = lambda: transcription.resolve_youtube_audio_source(
                f"https://www.youtube.com/watch?v={value}"
            )
        elif platform == "bilibili":
            cookies = deepcopy(self.logins.get("bilibili", {}))
            resolver = lambda: bilibili.get_live_audio_url(value, cookies)
        else:
            resolver = lambda: missevan.get_live_audio_url(value)
        transcriber = StreamingTranscriber(
            platform, value, resolver, str(data.get("language", settings["transcribe_target_language"])),
            model_size=str(data.get("model", settings["transcribe_model"])),
            translation_enabled=data.get("translate", settings["transcribe_translate"]) is True,
            options=options,
            translation_function=self.translate_text,
        )
        transcriber.start()
        self.transcriber = transcriber
        return {"ok": True}

    def close(self):
        from src import overlay_server
        overlay_server.unregister_translation_source(self.overlay_translation_id)
        with self.lock:
            self.closed = True
            self.record_armed.clear()
        if getattr(self, "obs_thread", None):
            self.obs_thread.join(timeout=5)
        if self.worker:
            self.worker.stop()
        if self.transcriber:
            self.transcriber.stop()
        for recorder in self.recorders.values():
            recorder.stop(wait=3)
        for pool in self.pools.values():
            pool.shutdown(wait=True, cancel_futures=False)


def make_server(dashboard: Dashboard, port: int = 8765):
    token = secrets.token_urlsafe(32)
    # Interface strings are public; they come from the shared desktop/browser translation table.
    translations = json.dumps({
        "languages": i18n.UI_LANGUAGES,
        "strings": {lang: catalog(lang) for lang in i18n.UI_LANGUAGES if lang != "en"},
    }, ensure_ascii=False).encode()
    assets = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
        "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # The browser polls state every second; keep routine access logs out of the console.
            log.debug(format, *args)

        def reply(self, code, data, mime="application/json"):
            body = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "img-src https: data:; connect-src 'self'; "
                             "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            host = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            return (
                self.headers.get("Host") == host
                and (origin is None or origin == f"http://{host}")
                and hmac.compare_digest(self.headers.get("X-Dashboard-Token", ""), token)
            )

        def do_GET(self):
            path = urlsplit(self.path).path
            if path.startswith("/api/"):
                if not self.authorized():
                    return self.reply(403, {"error": "Not authorized. Open the launch URL."})
                if path == "/api/state":
                    try:
                        return self.reply(200, dashboard.snapshot())
                    except Exception:
                        log.exception("Dashboard snapshot failed")
                        return self.reply(500, {"error": "Unable to retrieve dashboard state."})
                if path == "/api/room-events":
                    try:
                        room = dashboard.event_room({
                            "room": parse_qs(urlsplit(self.path).query).get("room", [""])[0]})
                        dashboard.event_query(lambda: None)
                        events = dashboard.event_store.export(room)
                        first = next(events, b"")
                    except ValueError as exc:
                        return self.reply(400, {"error": str(exc)})
                    except Exception:
                        log.exception("Room event export failed")
                        return self.reply(500, {"error": "Unable to export room events."})
                    try:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                        self.send_header("Content-Disposition", 'attachment; filename="room-events.jsonl"')
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("X-Content-Type-Options", "nosniff")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(first)
                        for event in events:
                            self.wfile.write(event)
                    except (BrokenPipeError, ConnectionResetError):
                        log.debug("Room event download disconnected")
                    finally:
                        events.close()
                    return
                return self.reply(404, {"error": "Unknown endpoint."})
            if path == "/i18n.json":
                return self.reply(200, translations, "application/json; charset=utf-8")
            if path not in assets:
                return self.reply(404, {"error": "Not found."})
            name, mime = assets[path]
            self.reply(200, (ASSETS / name).read_bytes(), mime)

        def do_POST(self):
            if not self.authorized():
                return self.reply(403, {"error": "Not authorized."})
            if self.path != "/api/action":
                return self.reply(404, {"error": "Unknown endpoint."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("Request is empty or too large.")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("JSON request required.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("JSON object required.")
                result = dashboard.action(data)
            except (ValueError, TypeError, KeyError, re.error) as exc:
                return self.reply(400, {"error": str(exc)})
            except Exception:
                log.exception("Dashboard action failed")
                return self.reply(500, {"error": "Action failed; see backend log."})
            self.reply(200, result)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if desktop_app.QtCore is None:
        parser.error("PySide6 is required for the reused monitoring worker.")
    logging.basicConfig(level=logging.INFO)
    app = desktop_app.QtCore.QCoreApplication([])
    base = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "StreamingDashboard"
    dashboard = Dashboard(base / "html_dashboard.json")
    try:
        server, token = make_server(dashboard, args.port)
    except OSError as exc:
        dashboard.close()
        parser.exit(1, f"Cannot listen on 127.0.0.1:{args.port} ({exc}). "
                       "Close the other dashboard or use --port.\n")
    except Exception:
        dashboard.close()
        raise
    thread = threading.Thread(target=server.serve_forever, name="html-http")
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/#token={token}"
    print(f"Open this local URL (keep it private): {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    # Let Python handle Ctrl+C while the Qt worker's event loop remains active.
    timer = desktop_app.QtCore.QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(250)
    import signal
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    try:
        return app.exec()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        dashboard.close()


if __name__ == "__main__":
    raise SystemExit(main())
