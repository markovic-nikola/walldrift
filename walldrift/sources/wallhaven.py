from typing import Any, ClassVar
from urllib.parse import urlsplit

from ..config import SourceConfig
from ..http import HttpClient
from ..models import Candidate, SearchPage
from .base import Source

API_URL = "https://wallhaven.cc/api/v1/search"
REQUESTS_PER_MINUTE = 45
SORTINGS = ("toplist", "views", "favorites")
TOP_RANGES = ("1d", "3d", "1w", "1M", "3M", "6M", "1y")
CATEGORIES = ("general", "anime", "people")
SFW_ONLY = "100"  # purity bits: sfw, sketchy, nsfw


class Wallhaven(Source):
    name = "wallhaven"
    OPTIONS: ClassVar[dict[str, Any]] = {
        "sorting": "toplist",
        "top_range": "1M",
        "categories": ["general"],
    }

    def __init__(self, config: SourceConfig, http: HttpClient, min_size: tuple[int, int]) -> None:
        super().__init__(config, http, min_size)
        self._sorting = self._choice("sorting", SORTINGS)
        self._top_range = self._choice("top_range", TOP_RANGES)
        categories = self._choices("categories", CATEGORIES)
        self._category_bits = "".join("1" if c in categories else "0" for c in CATEGORIES)
        http.throttle(urlsplit(API_URL).hostname or "", 60 / REQUESTS_PER_MINUTE)

    def search(self, topic: str | None, page: int) -> SearchPage:
        width, height = self.min_size
        params = {
            "sorting": self._sorting,
            "categories": self._category_bits,
            "purity": SFW_ONLY,
            "atleast": f"{width}x{height}",
            "page": str(page),
        }
        if self._sorting == "toplist":
            params["topRange"] = self._top_range
        if topic:
            params["q"] = topic
        headers = {"X-API-Key": self.config.api_key} if self.config.api_key else None
        body = self.http.get_json(API_URL, params, headers)
        return SearchPage(
            candidates=[self._candidate(item) for item in body["data"] if item["purity"] == "sfw"],
            last_page=int(body["meta"]["last_page"]),
        )

    def _candidate(self, item: dict[str, Any]) -> Candidate:
        # Search results don't name the uploader; the page link is the credit.
        return Candidate(
            source=self.name,
            id=item["id"],
            page_url=item["url"],
            image_url=item["path"],
            width=int(item["dimension_x"]),
            height=int(item["dimension_y"]),
        )
