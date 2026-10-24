"""Text-to-Speech module. Supports pyttsx3 (offline) and gTTS (online)."""
from __future__ import annotations

import collections
import io
import logging
import re
import threading

from src.config import TTS_PRIORITY_QUEUE_LIMIT, TTS_QUEUE_LIMIT, TTS_USE_GTTS

log = logging.getLogger(__name__)
_lock = threading.Lock()

_UNICODE_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # pictographs, emoticons, transport, symbols & pictographs ext.
    "\U0001F1E6-\U0001F1FF"  # regional indicators (flags)
    "\u2600-\u27BF"          # misc symbols, dingbats
    "\u2B00-\u2BFF"          # arrows/stars (⭐ ⬆)
    "\u2300-\u23FF"          # technical (⌚ ⏰)
    "\uFE0E\uFE0F\u200D\u20E3"  # variation selectors, ZWJ, keycap
    "\U000E0020-\U000E007F"  # tag sequences
    "]"
)
# YouTube renders custom/standard emoji as :name: in displayMessage (e.g. :face-blue-smiling:)
_YT_EMOJI_RE = re.compile(r":[A-Za-z_][A-Za-z0-9_\-]*:")
# Bilibili inline emotes look like [doge] / [OH] / [热词系列_好耶]
_BILI_EMOTE_RE = re.compile(r"\[[^\[\]\s]{1,20}\]")


def strip_emoji(text: str, platform: str = "") -> str:
    """Remove unicode emoji and platform emote codes from text."""
    text = _UNICODE_EMOJI_RE.sub("", text or "")
    if platform != "bilibili":
        text = _YT_EMOJI_RE.sub("", text)
    if platform != "youtube":
        text = _BILI_EMOTE_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def is_emoji_only(msg: dict) -> bool:
    """True for sticker danmaku or messages with nothing left to read once emoji are removed."""
    if msg.get("is_emoticon"):
        return True
    rest = strip_emoji(msg.get("text", ""), msg.get("platform", ""))
    # Letters/digits in any script count as readable; punctuation alone doesn't.
    return not re.sub(r"[\W_]+", "", rest)

# key -> (label, gTTS language code, SAPI/pyttsx3 language tag, spoken template)
LANGUAGES: dict[str, tuple[str, str, str, str]] = {
    "auto": ("Auto-detect", "", "", ""),
    "zh": ("Chinese (中文)", "zh-CN", "zh-CN", "{author}说：{text}"),
    "en": ("English", "en", "en-US", "{author} says {text}"),
    "ja": ("Japanese (日本語)", "ja", "ja-JP", "{author}さん：{text}"),
    "ko": ("Korean (한국어)", "ko", "ko-KR", "{author}님: {text}"),
}


def detect_language(text: str) -> str:
    """Pick zh/ja/ko/en from the script used in the text."""
    has_han = False
    for ch in text:
        if "\u3040" <= ch <= "\u30ff":  # hiragana / katakana
            return "ja"
        if "\uac00" <= ch <= "\ud7a3" or "\u1100" <= ch <= "\u11ff" or "\u3130" <= ch <= "\u318f":  # Hangul
            return "ko"
        if "\u4e00" <= ch <= "\u9fff":
            has_han = True
    return "zh" if has_han else "en"


def matches_language(text: str, lang: str) -> bool:
    """True if the text is written in `lang` (always True for auto-detect)."""
    if lang not in LANGUAGES or lang == "auto":
        return True
    if lang == "en" and not re.search(r"[A-Za-z]", text):
        return False  # numbers / punctuation / other scripts aren't English
    return detect_language(text) == lang


def resolve_language(lang: str, text: str) -> str:
    return detect_language(text) if lang not in LANGUAGES or lang == "auto" else lang


def format_message(author: str, text: str, lang: str = "auto") -> str:
    """Build the spoken sentence in the chosen language."""
    code = resolve_language(lang, text)
    return LANGUAGES[code][3].format(author=author, text=text)


# Message types that are paid events (gifts, Super Chats, memberships) across platforms.
PAID_TYPES = {
    "superChatEvent", "superStickerEvent", "superchat", "gift",
    "newSponsorEvent", "memberMilestoneChatEvent", "membershipGiftingEvent", "giftMembershipReceivedEvent",
}
_ANNOUNCE = {
    "superchat": {
        "zh": "{author}的醒目留言：{text}",
        "en": "Super Chat from {author}: {text}",
        "ja": "{author}さんからスーパーチャット：{text}",
        "ko": "{author}님의 슈퍼챗: {text}",
    },
    "gift": {
        "zh": "感谢{author}送出{text}",
        "en": "{author} sent {text}",
        "ja": "{author}さんから{text}",
        "ko": "{author}님이 {text} 선물",
    },
    "member": {
        "zh": "{author}：{text}",
        "en": "{author}: {text}",
        "ja": "{author}さん：{text}",
        "ko": "{author}님: {text}",
    },
    "enter": {
        "zh": "欢迎{author}进入直播间",
        "en": "{author} joined",
        "ja": "{author}さんが入室しました",
        "ko": "{author}님이 입장했습니다",
    },
}


def is_paid(msg: dict) -> bool:
    return msg.get("type", "") in PAID_TYPES and not msg.get("free")


def is_gift(msg: dict) -> bool:
    return msg.get("type") == "gift"


def announcement_text(text: str) -> str:
    """Make a paid-event line speakable: drop tag words / brackets, emoji markers and the × sign."""
    text = re.sub(r"\b(Super Chat|Super Sticker|SC)\b", " ", text)
    text = re.sub(r"[\[\]【】]", " ", text)
    text = re.sub(r"🎁|💎|🧧", " ", text)
    text = re.sub(r"\s*×\s*(\d+)", r" \1", text)
    return re.sub(r"\s+", " ", text).strip()


def format_announcement(msg_type: str, author: str, text: str, lang: str = "auto") -> str:
    """Spoken sentence for a gift / Super Chat, e.g. "Super Chat from Bob: $5 hello"."""
    code = resolve_language(lang, text)
    if msg_type == "gift":
        kind = "gift"
    elif msg_type in ("membershipGiftingEvent", "newSponsorEvent", "memberMilestoneChatEvent",
                      "giftMembershipReceivedEvent"):
        kind = "member"
    else:
        kind = "superchat"
    return _ANNOUNCE[kind][code].format(author=author, text=announcement_text(text))


def format_join(author: str, lang: str = "auto") -> str:
    """Spoken line for a viewer entering the room, e.g. "Bob joined"."""
    code = resolve_language(lang, author)
    return _ANNOUNCE["enter"][code].format(author=author)


def _pick_voice(engine, lang: str):
    tag = LANGUAGES[lang][2].lower()
    for v in engine.getProperty("voices"):
        langs = [str(l).lower().replace("_", "-") for l in (v.languages or [])]
        vid = v.id.upper().replace("_", "-")
        if tag in langs or f"-{tag.upper()}-" in vid:
            return v.id
    return None


_SVSF_ASYNC = 1
_SVSF_PURGE = 2
_stop_event = threading.Event()


def _speak_pyttsx3(text: str, rate: int, volume: float, lang: str) -> bool:
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voice = _pick_voice(engine, lang)
        driver = getattr(engine.proxy, "_driver", None)
        sapi = getattr(driver, "_tts", None)
        if sapi is not None and hasattr(sapi, "WaitUntilDone"):
            # engine.setProperty() only queues the change until runAndWait(), which this
            # path doesn't use, so set the voice / rate / volume on the driver directly.
            if voice:
                driver.setProperty("voice", voice)
            driver.setProperty("rate", rate)
            driver.setProperty("volume", volume)
            # Speak asynchronously so stop_speaking() can cut it off mid-sentence
            # (pyttsx3's runAndWait can't be interrupted from another thread).
            sapi.Speak(text, _SVSF_ASYNC)
            while not sapi.WaitUntilDone(100):
                if _stop_event.is_set():
                    sapi.Speak("", _SVSF_ASYNC | _SVSF_PURGE)
                    break
            return True
        if voice:
            engine.setProperty("voice", voice)
        engine.setProperty("rate", rate)
        engine.setProperty("volume", volume)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return True
    except Exception:
        log.exception("pyttsx3 error")
        return False


def _speak_gtts(text: str, lang: str) -> bytes | None:
    """Return MP3 bytes for the text via gTTS."""
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=LANGUAGES[lang][1])
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def available_voices() -> dict[str, bool]:
    """Which languages have an installed offline (pyttsx3) voice."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        return {k: _pick_voice(engine, k) is not None for k in LANGUAGES if k != "auto"}
    except Exception:
        return {}


def speak(text: str, rate: int = 150, volume: float = 1.0, lang: str = "auto") -> bytes | None:
    """
    Speak text.
    - pyttsx3: queued and played on this PC's speakers, returns None.
    - gTTS: returns MP3 bytes for Streamlit's st.audio().
    """
    code = resolve_language(lang, text)
    if TTS_USE_GTTS:
        return _speak_gtts(text, code)
    _enqueue(text, rate, volume, code)
    return None


def speak_async(text: str, rate: int = 150, volume: float = 1.0, lang: str = "auto", priority: bool = False):
    """Queue text for offline playback (pyttsx3 only; gTTS needs the browser player)."""
    if not TTS_USE_GTTS:
        _enqueue(text, rate, volume, resolve_language(lang, text), priority)


# pyttsx3 shares one engine per process and fails with "run loop already started"
# if two threads speak at once, so all speech goes through a single worker.
# Two lanes: gifts / Super Chats ("priority") are always spoken before normal chat.
_MAX_QUEUE = TTS_QUEUE_LIMIT
_MAX_PRIORITY_QUEUE = TTS_PRIORITY_QUEUE_LIMIT
_priority_q: "collections.deque[tuple[str, int, float, str]]" = collections.deque()
_normal_q: "collections.deque[tuple[str, int, float, str]]" = collections.deque()
_cond = threading.Condition()
_worker: threading.Thread | None = None


def _enqueue(text: str, rate: int, volume: float, lang: str, priority: bool = False):
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_worker_loop, name="tts-worker", daemon=True)
            _worker.start()
    with _cond:
        lane, limit = (_priority_q, _MAX_PRIORITY_QUEUE) if priority else (_normal_q, _MAX_QUEUE)
        while len(lane) >= limit:  # chat is faster than speech: drop the oldest
            lane.popleft()
            log.warning("TTS %s queue full; dropped oldest message", "priority" if priority else "normal")
        lane.append((text, rate, volume, lang))
        _cond.notify()


def _next_item() -> tuple[str, int, float, str]:
    with _cond:
        while not _priority_q and not _normal_q:
            _cond.wait()
        _stop_event.clear()  # under _cond, so a stop pressed after this pop still applies
        return (_priority_q or _normal_q).popleft()


def _worker_loop():
    try:
        import pythoncom  # SAPI needs COM initialised on this thread
        pythoncom.CoInitialize()
    except Exception:
        pass
    while True:
        text, rate, volume, lang = _next_item()
        if not _speak_pyttsx3(text, rate, volume, lang):
            log.warning("pyttsx3 failed to speak: %r", text[:60])


def pending_count() -> int:
    with _cond:
        return len(_priority_q) + len(_normal_q)


def clear_queue():
    with _cond:
        _priority_q.clear()
        _normal_q.clear()


def stop_speaking(clear: bool = True) -> int:
    """Cut off the message being read now; with clear=True also drop everything queued.
    Returns how many queued messages were dropped."""
    with _cond:
        dropped = 0
        if clear:
            dropped = len(_priority_q) + len(_normal_q)
            _priority_q.clear()
            _normal_q.clear()
        _stop_event.set()
    return dropped
