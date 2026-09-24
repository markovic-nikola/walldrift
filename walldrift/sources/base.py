from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar

from ..config import SourceConfig
from ..errors import ConfigError
from ..http import HttpClient
from ..models import Candidate, SearchPage


class Source(ABC):
    """A site that offers wallpapers. Subclasses implement only what differs between sites."""

    name: ClassVar[str]
    OPTIONS: ClassVar[dict[str, Any]] = {}
    """Source-specific config keys and their defaults."""

    def __init__(self, config: SourceConfig, http: HttpClient, min_size: tuple[int, int]) -> None:
        unknown = config.options.keys() - self.OPTIONS.keys()
        if unknown:
            raise ConfigError(f"unknown settings in sources.{self.name}: {', '.join(unknown)}")
        self.config = config
        self.http = http
        self.min_size = min_size
        self.options = {**self.OPTIONS, **config.options}

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
        value = self.options[key]
        if value not in allowed:
            raise ConfigError(f"sources.{self.name}.{key} must be one of: {', '.join(allowed)}")
        return str(value)

    def _choices(self, key: str, allowed: Sequence[str]) -> list[str]:
        values = self.options[key]
        if not isinstance(values, list) or not values or not set(values) <= set(allowed):
            raise ConfigError(
                f"sources.{self.name}.{key} must be a non-empty list of: {', '.join(allowed)}"
            )
        return values
