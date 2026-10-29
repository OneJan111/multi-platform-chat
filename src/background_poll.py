"""Single-flight network polling without accessing Streamlit from worker threads."""
from __future__ import annotations

from concurrent.futures import Future
from copy import deepcopy
import threading
import time
from typing import Callable, Generic, TypeVar

from src import user_login

T = TypeVar("T")


def _start_fetch(fetch: Callable[[], T], name: str) -> Future[T]:
    logins = deepcopy(user_login.current())
    future: Future[T] = Future()

    def run() -> None:
        try:
            with user_login.using(logins):
                result = fetch()
        except Exception as exc:
            future.set_exception(exc)
        else:
            future.set_result(result)

    threading.Thread(target=run, name=name, daemon=True).start()
    return future


class BackgroundTask(Generic[T]):
    """One bounded, explicitly submitted job; results are consumed on the UI thread."""

    def __init__(self) -> None:
        self._future: Future[T] | None = None
        self._discard = False

    @property
    def busy(self) -> bool:
        return self._future is not None

    def submit(self, fetch: Callable[[], T], *, name: str) -> bool:
        if self.busy:
            return False
        self._discard = False
        self._future = _start_fetch(fetch, name)
        return True

    def invalidate(self) -> None:
        self._discard = True

    def take(self) -> tuple[bool, T | None]:
        if self._future is None or not self._future.done():
            return False, None
        future, self._future = self._future, None
        result = future.result()
        return (False, None) if self._discard else (True, result)


class BackgroundPoll(Generic[T]):
    def __init__(self) -> None:
        self._future: Future[T] | None = None
        self._key: object = None
        self._started = 0.0

    def invalidate(self) -> None:
        self._key = object()

    def poll(
        self, key: object, interval: float, fetch: Callable[[], T]
    ) -> tuple[bool, T | None]:
        if self._future is not None:
            if not self._future.done():
                return False, None
            future, self._future = self._future, None
            if self._key == key:
                return True, future.result()
            # Observe failures even when the source changed while it was in flight.
            future.result()
        if self._started and time.monotonic() - self._started < interval:
            return False, None
        self._key = key
        self._started = time.monotonic()
        self._future = _start_fetch(fetch, "browser-network-poll")
        return False, None
