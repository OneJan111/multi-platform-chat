"""Read login cookies for Bilibili / YouTube from a locally installed browser."""
from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import set_key

try:
    import browser_cookie3
    BROWSER_COOKIE_LIB_OK = True
except ImportError:
    BROWSER_COOKIE_LIB_OK = False

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

BROWSERS = {"Firefox": "firefox", "Chrome": "chrome", "Edge": "edge"}
SITES = {"Bilibili": "bilibili.com", "YouTube": "youtube.com", "MissEvan": "missevan.com"}

BILIBILI_ENV_KEYS = {
    "SESSDATA": "BILIBILI_SESSDATA",
    "bili_jct": "BILIBILI_BILI_JCT",
    "buvid3": "BILIBILI_BUVID3",
    "DedeUserID": "BILIBILI_DEDEUSERID",
}
YOUTUBE_LOGIN_COOKIES = ("SID", "HSID", "SSID", "APISID", "SAPISID", "LOGIN_INFO")


class CookieReadError(Exception):
    pass


def read_cookies(browser: str, domain: str) -> dict[str, str]:
    """Return {name: value} for cookies of `domain` stored in `browser`."""
    if not BROWSER_COOKIE_LIB_OK:
        raise CookieReadError("browser-cookie3 is not installed (pip install browser-cookie3).")
    loader = getattr(browser_cookie3, browser, None)
    if loader is None:
        raise CookieReadError(f"Unsupported browser: {browser}")
    try:
        jar = loader(domain_name=domain)
    except Exception as exc:
        raise CookieReadError(_friendly_error(browser, exc)) from exc

    cookies: dict[str, str] = {}
    # Prefer cookies set on the root domain (e.g. ".bilibili.com") over subdomains.
    for cookie in sorted(jar, key=lambda c: c.domain.lstrip(".") == domain):
        if cookie.domain.lstrip(".").endswith(domain):
            cookies[cookie.name] = cookie.value
    return cookies


def _friendly_error(browser: str, exc: Exception) -> str:
    name = type(exc).__name__
    if name == "RequiresAdminError":
        return (
            f"{browser.title()} uses app-bound cookie encryption; reading it requires running "
            "the app as administrator. Try Firefox, or restart Streamlit from an elevated terminal."
        )
    if "decrypt" in str(exc).lower() or "key" in str(exc).lower():
        return (
            f"Could not decrypt {browser.title()} cookies ({exc}). Close the browser completely "
            "and retry, or use Firefox."
        )
    if "permission" in str(exc).lower() or "locked" in str(exc).lower():
        return f"{browser.title()} cookie database is locked. Close the browser and retry."
    return f"{name}: {exc}"


def mask(value: str) -> str:
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]} ({len(value)} chars)"


def verify_bilibili_login(cookies: dict[str, str]) -> dict:
    """Ask Bilibili who these cookies belong to. Returns {"is_login", "uname", "mid"}."""
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/nav",
            cookies={k: cookies[k] for k in BILIBILI_ENV_KEYS if k in cookies},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"},
            timeout=5,
        )
        data = resp.json().get("data") or {}
        return {
            "is_login": bool(data.get("isLogin")),
            "uname": data.get("uname", ""),
            "mid": data.get("mid", 0),
        }
    except Exception as exc:
        return {"is_login": False, "uname": "", "mid": 0, "error": str(exc)}


def save_bilibili_credentials(cookies: dict[str, str]) -> list[str]:
    """Write Bilibili cookies to .env and the current process environment."""
    ENV_FILE.touch(exist_ok=True)
    saved = []
    for cookie_name, env_key in BILIBILI_ENV_KEYS.items():
        value = cookies.get(cookie_name)
        if value:
            set_key(str(ENV_FILE), env_key, value)
            os.environ[env_key] = value
            saved.append(env_key)
    return saved
