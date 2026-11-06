"""Windows-user-bound API key encryption, adapted from the reference secret store."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import sys


def _crypt(data: bytes, *, decrypt: bool) -> bytes:
    if sys.platform != "win32":
        raise ValueError("Saving API keys requires Windows DPAPI on this computer.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]

    def blob(value):
        buffer = ctypes.create_string_buffer(value)
        return Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, source_buffer = blob(data)
    entropy, entropy_buffer = blob(b"StreamingDashboard/transcription-api-key")
    result = Blob()
    if decrypt:
        success = crypt32.CryptUnprotectData(
            ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(result))
    else:
        success = crypt32.CryptProtectData(
            ctypes.byref(source), "transcription-api-key", ctypes.byref(entropy),
            None, None, 1, ctypes.byref(result))
    if not success:
        raise ValueError("Could not encrypt or decrypt the API key for this Windows account.")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


def protect(value: str) -> str:
    return base64.b64encode(_crypt(value.encode("utf-8"), decrypt=False)).decode("ascii")


def unprotect(value: str) -> str:
    try:
        return _crypt(base64.b64decode(value, validate=True), decrypt=True).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Saved API key cannot be read. Re-enter it on this Windows account.") from exc
