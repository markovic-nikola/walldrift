from dataclasses import dataclass
from pathlib import Path

MAX_CROP = 0.27
"""The most of an image that zooming it to fill the screen may cut away.

A little over a quarter, so near-4:3 camera photos (e.g. 8160x6144) still pass on a 16:9 screen,
while 5:4 (30%) and portrait images don't.
"""


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
        """Big enough for the screen, and shaped close enough to it that zooming crops little.

        This rules out portrait images and very wide panoramas on a landscape screen.
        """
        if self.width < min_width or self.height < min_height:
            return False
        image_ratio, screen_ratio = self.width / self.height, min_width / min_height
        return min(image_ratio, screen_ratio) / max(image_ratio, screen_ratio) >= 1 - MAX_CROP


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
