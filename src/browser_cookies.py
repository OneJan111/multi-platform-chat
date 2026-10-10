"""Read login cookies for Bilibili / YouTube from a locally installed browser."""
from __future__ import annotations

import requests

from src import user_login
from src.config import BILIBILI_LOGIN_INFO_URL, BILIBILI_WEB_ORIGIN

try:
    import browser_cookie3
    BROWSER_COOKIE_LIB_OK = True
except ImportError:
    BROWSER_COOKIE_LIB_OK = False

BROWSERS = {"Firefox": "firefox", "Chrome": "chrome", "Edge": "edge"}
SITES = {"Bilibili": "bilibili.com", "YouTube": "youtube.com", "MissEvan": "missevan.com"}

BILIBILI_LOGIN_COOKIES = ("SESSDATA", "bili_jct", "buvid3", "DedeUserID")
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
    # When the browser has the cookie DB locked, browser_cookie3 falls back to a Windows
    # shadow copy via WMI, which needs COM initialised on this (Streamlit worker) thread.
    com = _co_initialize()
    try:
        jar = loader(domain_name=domain)
    except Exception as exc:
        raise CookieReadError(_friendly_error(browser, exc)) from exc
    finally:
        if com:
            com.CoUninitialize()

    cookies: dict[str, str] = {}
    # Prefer cookies set on the root domain (e.g. ".bilibili.com") over subdomains.
    for cookie in sorted(jar, key=lambda c: c.domain.lstrip(".") == domain):
        if cookie.domain.lstrip(".").endswith(domain):
            cookies[cookie.name] = cookie.value
    return cookies


def parse_cookie_text(text: str, domain: str) -> dict[str, str]:
    """Parse pasted/exported cookies for `domain`.

    Accepts a Netscape cookies.txt export, a JSON export (list of {name, value, domain}
    objects, e.g. Cookie-Editor), or a raw "name=value; name2=value2" Cookie header.
    """
    text = (text or "").strip().lstrip("\ufeff")
    if not text:
        return {}

    def _matches(cookie_domain: str) -> bool:
        cookie_domain = (cookie_domain or "").lstrip(".").lower()
        return not cookie_domain or cookie_domain == domain or cookie_domain.endswith("." + domain)

    if text[0] in "[{":
        import json

        try:
            data = json.loads(text)
        except ValueError as exc:
            raise CookieReadError(f"Couldn't parse the JSON cookie export: {exc}") from exc
        items = data.get("cookies", []) if isinstance(data, dict) else data
        return {
            str(c["name"]): str(c.get("value", ""))
            for c in items
            if isinstance(c, dict) and "name" in c and _matches(c.get("domain", ""))
        }

    lines = [ln for ln in text.splitlines() if ln.strip()]
    tab_rows = [ln.split("\t") for ln in lines if not ln.startswith("#") or ln.startswith("#HttpOnly_")]
    if any(len(row) >= 7 for row in tab_rows):
        cookies: dict[str, str] = {}
        for row in tab_rows:
            if len(row) < 7:
                continue
            host = row[0].removeprefix("#HttpOnly_")
            if _matches(host):
                cookies[row[5]] = row[6].strip()
        return cookies

    header = " ".join(lines)
    if header.lower().startswith("cookie:"):
        header = header[7:]
    cookies = {}
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            cookies[name.strip()] = value.strip()
    return cookies


def detect_site(text: str) -> str | None:
    """The SITES label pasted cookies belong to, or None when it isn't clear."""
    try:
        found = {label: parse_cookie_text(text, domain) for label, domain in SITES.items()}
    except CookieReadError:
        return None
    filled = [label for label, cookies in found.items() if cookies]
    if not filled:
        return None
    if len(filled) < len(found) or any(found[label] != found[filled[0]] for label in filled):
        # The export names its domains.
        if len(filled) == 1:
            return filled[0]
        logins = {"Bilibili": "SESSDATA", "YouTube": "SAPISID"}
        with_login = [label for label in filled if logins.get(label, "") in found[label]]
        return with_login[0] if len(with_login) == 1 else None
    # A plain Cookie header has no domains: go by the cookie names.
    names = set(found[filled[0]])
    if names & {"SESSDATA", "bili_jct", "DedeUserID"}:
        return "Bilibili"
    if names & set(YOUTUBE_LOGIN_COOKIES):
        return "YouTube"
    return None


def _co_initialize():
    """Initialise COM for the current thread; return pythoncom to uninitialise later, or None."""
    try:
        import pythoncom
        pythoncom.CoInitialize()
        return pythoncom
    except Exception:
        return None


def _friendly_error(browser: str, exc: Exception) -> str:
    name = type(exc).__name__
    if name == "ShadowCopyFailure" or "x_wmi" in name:
        return (
            f"{browser.title()} has its cookie database locked and the shadow-copy fallback failed "
            f"({exc}). Close the browser completely and retry."
        )
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
    if "profile" in str(exc).lower() and "find" in str(exc).lower():
        return (
            f"{browser.title()} isn't installed (or has no profile) on the computer running this app. "
            "If the app runs on a server, export the cookies from your own browser and use "
            "📋 Paste / upload cookies instead."
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
            BILIBILI_LOGIN_INFO_URL,
            cookies={k: cookies[k] for k in BILIBILI_LOGIN_COOKIES if k in cookies},
            headers={"User-Agent": "Mozilla/5.0", "Referer": BILIBILI_WEB_ORIGIN},
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
    """Use these Bilibili cookies for the current user only. Returns the cookie names kept."""
    kept = {name: cookies[name] for name in BILIBILI_LOGIN_COOKIES if cookies.get(name)}
    user_login.set_site("bilibili", kept)
    return list(kept)


def clear_login(site: str) -> bool:
    """Forget the current user's login for `site` ("youtube"/"bilibili"/"missevan")."""
    return user_login.clear_site(site)
