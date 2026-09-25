"""Validates the applet's settings. Their defaults live in settings-schema.json, not here."""

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import unquote, urlsplit

from . import APPLET_DIR, UUID
from .errors import ConfigError

SCHEMA_PATH = APPLET_DIR / "settings-schema.json"

# Every source has "<name>-enabled", "-weight", "-topics" and "-api-key" settings.
# Any other "<name>-..." setting is passed to the source as one of its own options.
_SHARED_SOURCE_KEYS = ("enabled", "weight", "topics", "api-key")

T = TypeVar("T")
Screen = Callable[[], tuple[int, int]]


@dataclass(frozen=True)
class SourceConfig:
    name: str
    enabled: bool
    weight: float
    topics: tuple[str, ...]
    options: dict[str, Any]
    api_key: str | None = None


@dataclass(frozen=True)
class Config:
    min_width: int
    min_height: int
    cache_limit_bytes: int
    queue_size: int
    favorites_dir: Path
    sources: tuple[SourceConfig, ...]


def _xdg(var: str, fallback: str) -> Path:
    # Named after the applet's UUID, as Spices asks; never inside the applet folder itself.
    return Path(os.environ.get(var) or Path.home() / fallback) / UUID


def state_dir() -> Path:
    """Durable state: the database with history, favorites and bans, and the locks."""
    return _xdg("XDG_STATE_HOME", ".local/state")


def cache_dir() -> Path:
    """Downloaded images; safe to delete."""
    return _xdg("XDG_CACHE_HOME", ".cache")


def defaults(schema_path: Path = SCHEMA_PATH) -> dict[str, Any]:
    schema = json.loads(schema_path.read_text())
    return {key: entry["default"] for key, entry in schema.items() if "default" in entry}


def load(text: str | None, screen: Screen) -> Config:
    """The applet's settings JSON over the schema's defaults; empty text means all defaults."""
    values = defaults()
    if text and text.strip():
        try:
            given = json.loads(text)
        except json.JSONDecodeError as e:
            raise ConfigError(f"the settings are not valid JSON: {e}") from e
        values.update(_typed(given, dict, "settings"))
    return parse(values, screen)


def parse(values: Mapping[str, Any], screen: Screen) -> Config:
    """screen gives the resolution that "auto" means."""
    resolution = values["min-resolution"]
    width, height = screen() if resolution == "auto" else parse_resolution(resolution)
    topics = parse_topics(values["topics"], "topics")
    return Config(
        min_width=width,
        min_height=height,
        cache_limit_bytes=_positive_int(values["cache-limit-mb"], "cache-limit-mb") * 2**20,
        queue_size=_positive_int(values["queue-size"], "queue-size"),
        favorites_dir=_directory(values["favorites-dir"], "favorites-dir"),
        sources=tuple(
            _parse_source(key.removesuffix("-enabled"), values, topics)
            for key in values
            if key.endswith("-enabled")
        ),
    )


def parse_resolution(value: object) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", _typed(value, str, "min-resolution"))
    if not match:
        raise ConfigError(f'min-resolution must look like "3840x2160", not {value!r}')
    return int(match[1]), int(match[2])


def parse_topics(value: object, name: str) -> tuple[str, ...]:
    """ "nature, space ,minimal" -> ("nature", "space", "minimal")."""
    return tuple(t.strip() for t in _typed(value, str, name).split(",") if t.strip())


def _parse_source(
    name: str, values: Mapping[str, Any], global_topics: tuple[str, ...]
) -> SourceConfig:
    prefix = f"{name}-"
    own = {key.removeprefix(prefix): v for key, v in values.items() if key.startswith(prefix)}
    missing = [f"{prefix}{key}" for key in _SHARED_SOURCE_KEYS if key not in own]
    if missing:
        raise ConfigError(f"settings are missing {', '.join(missing)}")
    weight = own.pop("weight")
    if isinstance(weight, bool) or not isinstance(weight, int | float) or weight <= 0:
        raise ConfigError(f"{prefix}weight must be a positive number")
    return SourceConfig(
        name=name,
        enabled=_typed(own.pop("enabled"), bool, f"{prefix}enabled"),
        weight=float(weight),
        topics=parse_topics(own.pop("topics"), f"{prefix}topics") or global_topics,
        api_key=_typed(own.pop("api-key"), str, f"{prefix}api-key").strip() or None,
        options=own,
    )


def _typed(value: object, kind: type[T], name: str) -> T:
    if not isinstance(value, kind):
        raise ConfigError(f"{name} must be a {kind.__name__}, not {value!r}")
    return value


def _positive_int(value: object, name: str) -> int:
    # Cinnamon's spinbuttons may store whole numbers as floats.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{name} must be a positive whole number, not {value!r}")
    return value


def _directory(value: object, name: str) -> Path:
    text = _typed(value, str, name)
    if text.startswith("file://"):
        text = unquote(urlsplit(text).path)
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"{name} must be a full path, not {text!r}")
    return path
