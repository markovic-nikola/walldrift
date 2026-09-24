import logging

from ..config import Config
from ..errors import ConfigError
from ..http import HttpClient
from .base import Source
from .wallhaven import Wallhaven

log = logging.getLogger(__name__)

REGISTRY: dict[str, type[Source]] = {cls.name: cls for cls in (Wallhaven,)}


def build(config: Config, http: HttpClient) -> list[Source]:
    """Creates the enabled sources named in the config."""
    sources: list[Source] = []
    for source_config in config.sources:
        cls = REGISTRY.get(source_config.name)
        if cls is None:
            log.warning("unknown source %r in config; ignoring it", source_config.name)
        elif source_config.enabled:
            sources.append(cls(source_config, http, (config.min_width, config.min_height)))
    if not sources:
        raise ConfigError(f"no sources are enabled; available: {', '.join(REGISTRY)}")
    return sources
