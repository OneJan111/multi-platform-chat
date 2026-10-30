"""Tencent Cloud realtime ASR V2 client for short PCM WAV segments."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import wave
from pathlib import Path
from urllib.parse import quote, urlencode
from uuid import uuid4

import websocket

_ASR_HOST = "asr.cloud.tencent.com"
_FRAME_BYTES = 1280
_MAX_AUDIO_BYTES = 500_000
_HANDSHAKE_TIMEOUT = 10
_RESULT_TIMEOUT = 20


def build_asr_url(
    app_id: str,
    secret_id: str,
    secret_key: str,
    source_language: str,
    *,
    timestamp: int | None = None,
    nonce: int | None = None,
    voice_id: str | None = None,
) -> str:
    if not app_id.isdigit() or not secret_id or not secret_key:
        raise ValueError("Tencent ASR app ID, secret ID, and secret key are required")
    engines = {"ja": "16k_ja", "zh": "16k_zh"}
    engine = engines.get(source_language)
    if engine is None:
        raise ValueError("Tencent realtime ASR source language must be ja or zh")

    issued_at = int(time.time()) if timestamp is None else int(timestamp)
    params = {
        "secretid": secret_id,
        "timestamp": str(issued_at),
        "expired": str(issued_at + 3600),
        "nonce": str(secrets.randbelow(2**31) if nonce is None else int(nonce)),
        "engine_model_type": engine,
        "voice_id": voice_id or uuid4().hex,
        "voice_format": "1",
        "needvad": "1",
    }
    sorted_params = sorted(params.items())
    unsigned_query = "&".join(f"{key}={value}" for key, value in sorted_params)
    signing_text = f"{_ASR_HOST}/asr/v2/{app_id}?{unsigned_query}"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        signing_text.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    signature = quote(base64.b64encode(digest).decode("ascii"), safe="")
    query = urlencode(sorted_params)
    return f"wss://{_ASR_HOST}/asr/v2/{app_id}?{query}&signature={signature}"


def _append_text(results: dict[int, str], result: object) -> None:
    if not isinstance(result, dict):
        return
    text = str(result.get("voice_text_str") or result.get("sentence") or "").strip()
    if not text:
        return
    try:
        index = int(result.get("index", result.get("sentence_id", 0)))
    except (TypeError, ValueError):
        index = 0
    results[index] = text


def recognize_wav_segment(
    path: Path,
    source_language: str,
    app_id: str,
    secret_id: str,
    secret_key: str,
) -> tuple[str, float]:
    if path.stat().st_size > _MAX_AUDIO_BYTES:
        raise ValueError("Audio segment exceeds the Tencent ASR request limit")
    with wave.open(str(path), "rb") as audio_file:
        if (
            audio_file.getnchannels() != 1
            or audio_file.getsampwidth() != 2
            or audio_file.getframerate() != 16000
        ):
            raise ValueError("Tencent realtime ASR requires 16 kHz mono 16-bit PCM WAV audio")
        frame_count = audio_file.getnframes()
        pcm = audio_file.readframes(frame_count)
        duration = frame_count / audio_file.getframerate()
    if not pcm:
        return "", duration

    url = build_asr_url(app_id, secret_id, secret_key, source_language)
    connection = websocket.create_connection(url, timeout=_HANDSHAKE_TIMEOUT)
    try:
        connection.settimeout(_RESULT_TIMEOUT)
        try:
            handshake = json.loads(connection.recv())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Tencent ASR returned an invalid handshake") from exc
        if not isinstance(handshake, dict) or int(handshake.get("code", -1)) != 0:
            message = handshake.get("message", "unknown error") if isinstance(handshake, dict) else "invalid response"
            raise RuntimeError(f"Tencent ASR handshake failed: {message}")

        for offset in range(0, len(pcm), _FRAME_BYTES):
            connection.send_binary(pcm[offset:offset + _FRAME_BYTES])
        connection.send(json.dumps({"type": "end"}))

        results: dict[int, str] = {}
        deadline = time.monotonic() + _RESULT_TIMEOUT
        while time.monotonic() < deadline:
            try:
                raw = connection.recv()
            except websocket.WebSocketTimeoutException as exc:
                raise TimeoutError("Timed out waiting for Tencent ASR results") from exc
            try:
                event = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError("Tencent ASR returned an invalid result frame") from exc
            if not isinstance(event, dict):
                continue
            code = int(event.get("code", 0))
            if code != 0:
                raise RuntimeError(
                    f"Tencent ASR failed ({code}): {event.get('message', 'unknown error')}"
                )
            _append_text(results, event.get("result"))
            sentences = event.get("sentences")
            if isinstance(sentences, dict):
                _append_text(results, sentences)
            elif isinstance(sentences, list):
                for sentence in sentences:
                    _append_text(results, sentence)
            if int(event.get("final", 0)) == 1:
                break
        else:
            raise TimeoutError("Timed out waiting for Tencent ASR completion")
        return " ".join(results[index] for index in sorted(results)).strip(), duration
    finally:
        connection.close()
