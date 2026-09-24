from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from ..config import SourceConfig
from ..errors import ConfigError
from ..http import HttpClient
from ..models import Candidate, SearchPage


class Source(ABC):
    """A site that offers wallpapers. Subclasses implement only what differs between sites.

    A source's own options are its "<name>-<option>" settings in settings-schema.json.
    """

    name: ClassVar[str]

    def __init__(self, config: SourceConfig, http: HttpClient, min_size: tuple[int, int]) -> None:
        self.config = config
        self.http = http
        self.min_size = min_size

    @property
    def weight(self) -> float:
        return self.config.weight

    @property
    def topics(self) -> tuple[str, ...]:
        return self.config.topics

    @abstractmethod
    def search(self, topic: str | None, page: int) -> SearchPage:
        """Returns one page of popular images, filtered by topic when one is given."""

    def on_download(self, candidate: Candidate) -> None:  # noqa: B027 - optional hook
        """Called after each download. Most sources need nothing here."""

    def _choice(self, key: str, allowed: Sequence[str]) -> str:
        value = self.config.options[key]
        if value not in allowed:
            raise ConfigError(f"{self.name}-{key} must be one of: {', '.join(allowed)}")
        return str(value)

    def _flag(self, key: str) -> bool:
        value = self.config.options[key]
        if not isinstance(value, bool):
            raise ConfigError(f"{self.name}-{key} must be true or false")
        return value
