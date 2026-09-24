from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    """An image offered by a source, before it is downloaded."""

    source: str
    id: str
    page_url: str
    image_url: str
    width: int
    height: int
    author: str | None = None
    author_url: str | None = None

    @property
    def key(self) -> str:
        return f"{self.source}:{self.id}"

    def fits(self, min_width: int, min_height: int) -> bool:
        return self.width >= min_width and self.height >= min_height


@dataclass(frozen=True)
class SearchPage:
    candidates: list[Candidate]
    last_page: int


@dataclass(frozen=True)
class Image:
    """An image the store knows about: queued, shown, favorited or banned."""

    candidate: Candidate
    path: Path | None
    size: int
    shown_at: float | None
    favorite: bool
    banned: bool

    @property
    def key(self) -> str:
        return self.candidate.key
