"""Persistent collector that bridges the existing platform clients to EdgeOne Pages.

Run on a small always-on Python host. EdgeOne Functions handle storage and Tencent
Cloud APIs; this process keeps platform WebSockets and FFmpeg audio capture alive.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from src import bilibili, missevan, transcription, tencent_realtime_asr, youtube as yt, youtube_web as ytw
from src import config as app_config
from src.server_chat_history import ServerChatHistory, ServerChatPoller

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("edgeone_collector")

_PLATFORM_PRIORITY = ("bilibili", "youtube", "missevan")
_STATUS_INTERVAL = max(10, int(os.getenv("EDGEONE_STATUS_INTERVAL", "20")))
_CONFIG_INTERVAL = max(2, int(os.getenv("EDGEONE_CONFIG_INTERVAL", "5")))
_POLL_INTERVAL = max(1, app_config.SIMPLE_CHAT_POLL_INTERVAL)


def configured_sources() -> dict[str, str]:
    sources = {}
    if app_config.YOUTUBE_CHANNEL.strip():
        sources["youtube"] = app_config.YOUTUBE_CHANNEL.strip()
    if app_config.BILIBILI_ROOM_ID.strip():
        sources["bilibili"] = bilibili.parse_room_id(app_config.BILIBILI_ROOM_ID)
    if app_config.MISSEVAN_ROOM_ID.strip():
        sources["missevan"] = missevan.parse_room_id(app_config.MISSEVAN_ROOM_ID)
    return {site: source for site, source in sources.items() if source}


class EdgeOneCollector:
    def __init__(
        self,
        base_url: str,
        collector_token: str,
        sources: dict[str, str] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("EDGEONE_BASE_URL must use HTTPS")
        if len(collector_token) < 32:
            raise ValueError("EDGEONE_COLLECTOR_TOKEN must contain at least 32 characters")
        self.base_url = base_url.rstrip("/")
        self._token = collector_token
        self.sources = sources if sources is not None else configured_sources()
        self.session = session or requests.Session()
        self.stop_event = threading.Event()
        self.history = ServerChatHistory()
        self.poller: ServerChatPoller | None = None
        self.transcriber: transcription.LiveTranscriber | None = None
        self._transcription_key: tuple[str, str, str] | None = None
        self._chat_cursor = 0
        self._gift_cursor = 0
        self._last_status_poll = 0.0
        self._last_config_poll = 0.0
        self._config: dict | None = None
        self._live: dict[str, bool] = {}
        self._active_source = ""
        self._last_synced_live: dict[str, bool] | None = None
        self._last_synced_active_source: str | None = None
        self._api_headers = {"Authorization": f"Bearer {collector_token}"}

    def _request(self, path: str, *, payload: dict | None = None) -> dict:
        response = self.session.request(
            "POST" if payload is not None else "GET",
            f"{self.base_url}{path}",
            headers=self._api_headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError(f"EdgeOne returned an invalid response for {path}")
        return result

    def _youtube_status(self, source: str) -> tuple[bool, str]:
        if ytw.channel_url(source):
            info = ytw.find_live_video(source)
            return bool(info.get("live") and info.get("video_id")), str(info.get("video_id") or "")
        video_id = yt.extract_video_id(source)
        if not video_id:
            return False, ""
        info = ytw.get_video_status(video_id)
        return info.get("broadcast") == "live", video_id

    def _check_live_sources(self) -> dict[str, tuple[bool, str]]:
        live: dict[str, tuple[bool, str]] = {}
        for site in _PLATFORM_PRIORITY:
            source = self.sources.get(site)
            if not source:
                live[site] = (False, "")
                continue
            try:
                if site == "bilibili":
                    info = bilibili.get_room_info(source)
                    live[site] = (bool(info.get("live_status") == 1), source)
                elif site == "youtube":
                    live[site] = self._youtube_status(source)
                else:
                    info = missevan.get_room_info(source)
                    live[site] = (bool(info.get("live")), source)
            except Exception:
                log.exception("Could not check %s live status", site)
                live[site] = (False, "")
        self._live = {site: status for site, (status, _) in live.items()}
        return live

    def _choose_audio_source(
        self, live: dict[str, tuple[bool, str]]
    ) -> tuple[str, str, Callable[[], str | dict]] | None:
        for site in _PLATFORM_PRIORITY:
            is_live, source_id = live.get(site, (False, ""))
            if not is_live:
                continue
            source = self.sources[site]
            if site == "bilibili":
                resolver = lambda room=source: bilibili.get_live_audio_url(room)
            elif site == "youtube":
                resolver = lambda video=source_id: transcription.resolve_youtube_audio_source(
                    f"https://www.youtube.com/watch?v={video}"
                )
            else:
                resolver = lambda room=source: missevan.get_live_audio_url(room)
            return site, source_id, resolver
        return None

    def _recognize_segment(
        self, path: Path, source_language: str, platform: str
    ) -> dict:
        original, duration = tencent_realtime_asr.recognize_wav_segment(
            path,
            source_language,
            os.getenv("TENCENT_ASR_APP_ID", "").strip(),
            os.getenv("TENCENT_ASR_SECRET_ID", "").strip(),
            os.getenv("TENCENT_ASR_SECRET_KEY", "").strip(),
        )
        if not original:
            return {"original": "", "translated": "", "detected_language": source_language}
        response = self._request(
            "/api/transcribe",
            payload={
                "original": original,
                "audioDuration": duration,
                "platform": platform,
                "sourceLanguage": source_language,
            },
        )
        return {
            "original": response.get("original", ""),
            "translated": response.get("translated", ""),
            "detected_language": source_language,
        }

    def _stop_transcriber(self) -> None:
        transcriber, self.transcriber = self.transcriber, None
        self._transcription_key = None
        self._active_source = ""
        if transcriber:
            transcriber.stop()
            thread = transcriber._thread
            if thread and thread.is_alive():
                thread.join(timeout=3)

    def _sync_transcriber(
        self,
        config: dict,
        live: dict[str, tuple[bool, str]] | None = None,
    ) -> None:
        if not config.get("transcriptionEnabled"):
            self._stop_transcriber()
            return
        live = live if live is not None else self._check_live_sources()
        selected = self._choose_audio_source(live)
        if selected is None:
            self._stop_transcriber()
            return
        site, source_id, resolver = selected
        language = config.get("audioLanguage", "ja")
        if language not in ("ja", "zh"):
            raise ValueError("EdgeOne returned an unsupported transcription language")
        key = (site, source_id, language)
        if key == self._transcription_key and self.transcriber and self.transcriber.is_running:
            return
        self._stop_transcriber()
        self.transcriber = transcription.LiveTranscriber(
            platform=site,
            source_id=source_id,
            source_resolver=resolver,
            target_language="zh-CN" if language == "ja" else "ja",
            translation_enabled=True,
            segment_recognizer=lambda path: self._recognize_segment(path, language, site),
        )
        self._transcription_key = key
        self._active_source = site
        try:
            self.transcriber.start()
        except Exception:
            self.transcriber = None
            self._transcription_key = None
            self._active_source = ""
            raise

    def _sync_chat(self) -> None:
        chats = self.history.chat()
        gifts = self.history.gifts()
        next_chat_cursor = len(chats)
        next_gift_cursor = len(gifts)
        new_items = chats[self._chat_cursor:next_chat_cursor] + gifts[self._gift_cursor:next_gift_cursor]
        new_items.sort(key=lambda message: int(
            message.get("_simple_arrived") or message.get("_arrived") or 0
        ))
        if (
            not new_items
            and self._live == self._last_synced_live
            and self._active_source == self._last_synced_active_source
        ):
            return
        batches = [new_items[index:index + 100] for index in range(0, len(new_items), 100)]
        if not batches:
            batches = [[]]
        for batch in batches:
            self._request(
                "/api/collector/ingest",
                payload={
                    "activeSource": self._active_source,
                    "live": self._live,
                    "messages": batch,
                },
            )
        self._chat_cursor = next_chat_cursor
        self._gift_cursor = next_gift_cursor
        self._last_synced_live = dict(self._live)
        self._last_synced_active_source = self._active_source

    def run(self) -> None:
        if not self.sources:
            raise RuntimeError("Configure at least one of YOUTUBE_CHANNEL, BILIBILI_ROOM_ID, or MISSEVAN_ROOM_ID")
        self.poller = ServerChatPoller(self.history, self.sources)
        log.info("Collector started for platforms: %s", ", ".join(self.sources))
        try:
            while not self.stop_event.is_set():
                started = time.monotonic()
                try:
                    if (
                        self._config is None
                        or started - self._last_config_poll >= _CONFIG_INTERVAL
                    ):
                        try:
                            self._config = self._request("/api/collector/config")
                            self._last_config_poll = started
                        except (requests.RequestException, RuntimeError, ValueError):
                            self._stop_transcriber()
                            raise
                    config = self._config
                    if config is None:
                        raise RuntimeError("EdgeOne collector configuration is unavailable")
                    live = None
                    if started - self._last_status_poll >= _STATUS_INTERVAL:
                        live = self._check_live_sources()
                        self._last_status_poll = started
                    self._sync_transcriber(config, live)
                    self._sync_chat()
                except requests.RequestException:
                    log.exception("Could not reach the EdgeOne API")
                except Exception:
                    log.exception("EdgeOne collector iteration failed")
                self.stop_event.wait(max(0, _POLL_INTERVAL - (time.monotonic() - started)))
        finally:
            self._stop_transcriber()
            if self.poller:
                self.poller.stop()

    def stop(self, *_args) -> None:
        self.stop_event.set()


def main() -> None:
    base_url = os.getenv("EDGEONE_BASE_URL", "").strip()
    token = os.getenv("EDGEONE_COLLECTOR_TOKEN", "").strip()
    collector = EdgeOneCollector(base_url, token)
    signal.signal(signal.SIGINT, collector.stop)
    signal.signal(signal.SIGTERM, collector.stop)
    collector.run()


if __name__ == "__main__":
    main()
