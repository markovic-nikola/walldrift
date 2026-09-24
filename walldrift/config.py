"""Loads config.toml and secrets.toml and fills in defaults."""

import logging
import os
import re
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from .errors import ConfigError

log = logging.getLogger(__name__)

APP = "walldrift"

DEFAULTS: dict[str, Any] = {
    "interval": "30m",
    "min_resolution": "1920x1080",
    "cache_limit_mb": 1024,
    "queue_size": 3,
    "favorites_dir": "~/Pictures/Wallpapers",
    "topics": [],
    "sources": {"wallhaven": {}},
}

MIN_INTERVAL_S = 60
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_DURATION_PART = re.compile(r"(\d+)([smhd])")

T = TypeVar("T")


@dataclass(frozen=True)
class SourceConfig:
    name: str
    enabled: bool
    weight: float
    topics: tuple[str, ...]
    options: dict[str, Any]
    """Source-specific settings, checked by the source itself."""
    api_key: str | None = None


@dataclass(frozen=True)
class Config:
    interval_s: int
    min_width: int
    min_height: int
    cache_limit_bytes: int
    queue_size: int
    favorites_dir: Path
    sources: tuple[SourceConfig, ...]


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


def xdg_config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def config_dir() -> Path:
    return xdg_config_home() / APP


def data_dir() -> Path:
    """Durable state: the database with favorites and bans."""
    return _xdg("XDG_DATA_HOME", ".local/share") / APP


def cache_dir() -> Path:
    """Downloaded images; safe to delete."""
    return _xdg("XDG_CACHE_HOME", ".cache") / APP


def load(path: Path | None = None, secrets_path: Path | None = None) -> Config:
    base = config_dir()
    raw = _read_toml(path or base / "config.toml")
    secrets = _read_secrets(secrets_path or base / "secrets.toml")
    return parse(raw, secrets)


def parse(raw: dict[str, Any], secrets: dict[str, Any]) -> Config:
    unknown = raw.keys() - DEFAULTS.keys()
    if unknown:
        raise ConfigError(f"unknown settings: {', '.join(sorted(unknown))}")
    merged = {**DEFAULTS, **raw}

    width, height = parse_resolution(merged["min_resolution"])
    topics = _str_tuple(merged["topics"], "topics")
    source_tables = _typed(merged["sources"], dict, "sources")
    return Config(
        interval_s=parse_duration(merged["interval"]),
        min_width=width,
        min_height=height,
        cache_limit_bytes=_positive_int(merged["cache_limit_mb"], "cache_limit_mb") * 1024 * 1024,
        queue_size=_positive_int(merged["queue_size"], "queue_size"),
        favorites_dir=Path(_typed(merged["favorites_dir"], str, "favorites_dir")).expanduser(),
        sources=tuple(
            _parse_source(name, table, topics, secrets.get(name, {}))
            for name, table in {**DEFAULTS["sources"], **source_tables}.items()
        ),
    )


def parse_duration(value: object) -> int:
    """Turns "30m", "1h30m" or "90s" into seconds."""
    text = _typed(value, str, "interval").replace(" ", "")
    parts = _DURATION_PART.findall(text)
    if not parts or "".join(n + u for n, u in parts) != text:
        raise ConfigError(f'interval must look like "30m" or "1h30m", not {value!r}')
    seconds = sum(int(n) * _DURATION_UNITS[u] for n, u in parts)
    if seconds < MIN_INTERVAL_S:
        raise ConfigError(f"interval must be at least {MIN_INTERVAL_S}s")
    return seconds


def parse_resolution(value: object) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", _typed(value, str, "min_resolution"))
    if not match:
        raise ConfigError(f'min_resolution must look like "3840x2160", not {value!r}')
    return int(match[1]), int(match[2])


def _parse_source(
    name: str, table: object, global_topics: tuple[str, ...], secrets: object
) -> SourceConfig:
    where = f"sources.{name}"
    options = dict(_typed(table, dict, where))
    weight = options.pop("weight", 1)
    if isinstance(weight, bool) or not isinstance(weight, int | float) or weight <= 0:
        raise ConfigError(f"{where}.weight must be a positive number")
    topics = options.pop("topics", None)
    return SourceConfig(
        name=name,
        enabled=_typed(options.pop("enabled", True), bool, f"{where}.enabled"),
        weight=float(weight),
        topics=global_topics if topics is None else _str_tuple(topics, f"{where}.topics"),
        options=options,
        api_key=_typed(secrets, dict, f"secrets {name}").get("api_key"),
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e


def _read_secrets(path: Path) -> dict[str, Any]:
    secrets = _read_toml(path)
    if secrets and path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        log.warning("%s is readable by other users; run: chmod 600 %s", path, path)
    return secrets


def _typed(value: object, kind: type[T], name: str) -> T:
    if not isinstance(value, kind):
        raise ConfigError(f"{name} must be a {kind.__name__}, not {value!r}")
    return value


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{name} must be a positive whole number, not {value!r}")
    return value


def _str_tuple(value: object, name: str) -> tuple[str, ...]:
    items = _typed(value, list, name)
    if not all(isinstance(item, str) and item for item in items):
        raise ConfigError(f"{name} must be a list of non-empty strings")
    return tuple(items)
