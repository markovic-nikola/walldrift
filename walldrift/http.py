"""One shared HTTP client: user agent, timeouts, retries with backoff, per-host throttling."""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from . import HOMEPAGE, __version__
from .errors import HttpError

log = logging.getLogger(__name__)

USER_AGENT = f"walldrift/{__version__}" + (f" (+{HOMEPAGE})" if HOMEPAGE else "")
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER_S = 60
"""A server asking us to wait longer than this fails the request instead of blocking."""
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
_CHUNK = 64 * 1024

Opener = Callable[..., Any]


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float = 20.0,
        retries: int = 3,
        backoff: float = 2.0,
        opener: Opener = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._timeout = timeout
        self._retries = retries
        self._backoff = backoff
        self._opener = opener
        self._sleep = sleep
        self._clock = clock
        self._min_interval: dict[str, float] = {}
        self._last_request: dict[str, float] = {}

    def throttle(self, host: str, min_interval: float) -> None:
        """Keeps at least min_interval seconds between requests to host."""
        self._min_interval[host] = min_interval

    def get_json(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        with self._open(url, headers) as response:
            return json.load(response)

    def download(self, url: str, dest: Path, headers: Mapping[str, str] | None = None) -> str:
        """Saves url to dest and returns its Content-Type."""
        with self._open(url, headers) as response, dest.open("wb") as f:
            written = 0
            while chunk := response.read(_CHUNK):
                written += len(chunk)
                if written > MAX_DOWNLOAD_BYTES:
                    raise HttpError(f"{url} is larger than {MAX_DOWNLOAD_BYTES // 2**20} MB")
                f.write(chunk)
            content_type: str = response.headers.get_content_type()
            return content_type

    def _open(self, url: str, headers: Mapping[str, str] | None) -> Any:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        host = urllib.parse.urlsplit(url).hostname or ""
        for attempt in range(self._retries + 1):
            self._wait_turn(host)
            try:
                return self._opener(request, timeout=self._timeout)
            except urllib.error.HTTPError as e:
                e.close()
                retry_after = _retry_after(e)
                if e.code not in RETRY_STATUSES or attempt == self._retries:
                    raise HttpError(f"{url}: HTTP {e.code} {e.reason}") from e
                if retry_after is not None and retry_after > MAX_RETRY_AFTER_S:
                    raise HttpError(f"{url}: rate limited for {retry_after:.0f}s") from e
                reason = f"HTTP {e.code}"
                delay = retry_after if retry_after is not None else self._backoff * 2**attempt
            except (urllib.error.URLError, TimeoutError) as e:
                reason = str(getattr(e, "reason", e))
                if attempt == self._retries:
                    raise HttpError(f"{url}: {reason}") from e
                delay = self._backoff * 2**attempt
            log.info("%s: %s; retrying in %.0fs", host, reason, delay)
            self._sleep(delay)
        raise AssertionError("unreachable")

    def _wait_turn(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            wait = last + self._min_interval.get(host, 0.0) - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()


def _retry_after(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None  # an HTTP date; rare enough to treat as "no hint"
