import io
import json
import urllib.error
from email.message import Message
from typing import Any

import pytest

from walldrift.errors import HttpError
from walldrift.http import USER_AGENT, HttpClient


class Response(io.BytesIO):
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = content_type


def http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://api.test/x", code, "err", headers, io.BytesIO())


class Opener:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: float) -> Any:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client(opener: Opener, sleeps: list[float], clock: Any = lambda: 0.0) -> HttpClient:
    return HttpClient(opener=opener, sleep=sleeps.append, clock=clock)


def test_get_json_sends_user_agent_and_params() -> None:
    opener = Opener(Response(json.dumps({"ok": True}).encode()))
    assert client(opener, []).get_json("https://api.test/x", {"q": "a b"}) == {"ok": True}
    request = opener.requests[0]
    assert request.full_url == "https://api.test/x?q=a+b"
    assert request.get_header("User-agent") == USER_AGENT


def test_retries_with_retry_after_then_backoff() -> None:
    sleeps: list[float] = []
    opener = Opener(http_error(429, "5"), http_error(503), Response(b"[]"))
    assert client(opener, sleeps).get_json("https://api.test/x") == []
    assert sleeps == [5.0, 4.0]


def test_gives_up_on_long_retry_after() -> None:
    with pytest.raises(HttpError, match="rate limited"):
        client(Opener(http_error(429, "3600")), []).get_json("https://api.test/x")


def test_client_errors_are_not_retried() -> None:
    opener = Opener(http_error(404))
    with pytest.raises(HttpError, match="404"):
        client(opener, []).get_json("https://api.test/x")
    assert len(opener.requests) == 1


def test_network_errors_fail_after_retries() -> None:
    opener = Opener(*[urllib.error.URLError("down")] * 4)
    with pytest.raises(HttpError, match="down"):
        client(opener, []).get_json("https://api.test/x")
    assert len(opener.requests) == 4


def test_throttle_spaces_requests_per_host() -> None:
    sleeps: list[float] = []
    now = iter([0.0, 0.5, 0.5])  # first request, second (check), second (record)
    http = client(Opener(Response(b"1"), Response(b"2")), sleeps, clock=lambda: next(now))
    http.throttle("api.test", 2.0)
    http.get_json("https://api.test/x")
    http.get_json("https://api.test/x")
    assert sleeps == [1.5]


def test_download_returns_content_type(tmp_path: Any) -> None:
    dest = tmp_path / "img"
    content_type = client(Opener(Response(b"data", "image/png")), []).download("https://x/y", dest)
    assert content_type == "image/png"
    assert dest.read_bytes() == b"data"
