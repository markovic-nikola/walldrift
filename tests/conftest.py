from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from walldrift import config
from walldrift.http import HttpClient
from walldrift.models import Candidate, SearchPage
from walldrift.sources.base import Source
from walldrift.store import Store


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        self.now += 1  # every call is a distinct moment, so ordering is stable
        return self.now


class FakeHttp(HttpClient):
    """Answers get_json from a list of bodies and writes fixed bytes on download."""

    def __init__(self, bodies: list[Any] | None = None, content_type: str = "image/jpeg") -> None:
        super().__init__()
        self.bodies = list(bodies or [])
        self.content_type = content_type
        self.requests: list[tuple[str, dict[str, str], dict[str, str]]] = []
        self.downloads: list[str] = []

    def get_json(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        self.requests.append((url, dict(params or {}), dict(headers or {})))
        return self.bodies.pop(0)

    def download(self, url: str, dest: Path, headers: Mapping[str, str] | None = None) -> str:
        self.downloads.append(url)
        dest.write_bytes(b"x" * 100)
        return self.content_type


def candidate(n: int, source: str = "fake", width: int = 3840, height: int = 2160) -> Candidate:
    return Candidate(
        source=source,
        id=f"id{n}",
        page_url=f"https://example.com/{n}",
        image_url=f"https://example.com/{n}.jpg",
        width=width,
        height=height,
    )


class FakeSource(Source):
    name = "fake"

    def __init__(self, pages: list[list[Candidate]], topics: tuple[str, ...] = ()) -> None:
        cfg = config.SourceConfig(name="fake", enabled=True, weight=1, topics=topics, options={})
        super().__init__(cfg, FakeHttp(), (1920, 1080))
        self.pages = pages
        self.searches: list[tuple[str | None, int]] = []
        self.downloaded: list[Candidate] = []

    def search(self, topic: str | None, page: int) -> SearchPage:
        self.searches.append((topic, page))
        return SearchPage(self.pages[page - 1], last_page=len(self.pages))

    def on_download(self, c: Candidate) -> None:
        self.downloaded.append(c)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock: Clock) -> Store:
    return Store(":memory:", clock=clock)


SCREEN = (2560, 1440)


def make_config(overrides: dict[str, Any] | None = None) -> config.Config:
    """The schema's defaults with some settings changed; "auto" resolution means SCREEN."""
    return config.parse({**config.defaults(), **(overrides or {})}, lambda: SCREEN)
