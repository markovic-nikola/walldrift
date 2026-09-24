import os
from pathlib import Path

import pytest

from walldrift import config
from walldrift.errors import ConfigError


def test_defaults() -> None:
    c = config.parse({}, {})
    assert c.interval_s == 1800
    assert (c.min_width, c.min_height) == (1920, 1080)
    assert [s.name for s in c.sources] == ["wallhaven"]
    assert c.sources[0].enabled
    assert c.favorites_dir == Path.home() / "Pictures/Wallpapers"


@pytest.mark.parametrize(
    ("text", "seconds"), [("30m", 1800), ("1h30m", 5400), ("90s", 90), ("1d", 86400)]
)
def test_parse_duration(text: str, seconds: int) -> None:
    assert config.parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["30", "m", "30x", "10s", "1h 30", 30])
def test_parse_duration_rejects(text: object) -> None:
    with pytest.raises(ConfigError):
        config.parse_duration(text)


def test_per_source_topics_override_global() -> None:
    c = config.parse(
        {
            "topics": ["nature"],
            "sources": {"wallhaven": {"topics": ["cyberpunk"], "weight": 2}, "other": {}},
        },
        {"wallhaven": {"api_key": "k"}},
    )
    wallhaven, other = c.sources
    assert wallhaven.topics == ("cyberpunk",)
    assert wallhaven.weight == 2
    assert wallhaven.api_key == "k"
    assert wallhaven.options == {}
    assert other.topics == ("nature",)


def test_source_specific_options_are_passed_through() -> None:
    c = config.parse({"sources": {"wallhaven": {"sorting": "views"}}}, {})
    assert c.sources[0].options == {"sorting": "views"}


@pytest.mark.parametrize(
    "raw",
    [
        {"unknown": 1},
        {"min_resolution": "big"},
        {"queue_size": 0},
        {"cache_limit_mb": True},
        {"topics": "nature"},
        {"sources": {"wallhaven": {"weight": 0}}},
        {"sources": {"wallhaven": {"enabled": "yes"}}},
    ],
)
def test_invalid_config(raw: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        config.parse(raw, {})


def test_load_reads_files_and_warns_on_open_secrets(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('interval = "1h"\n')
    secrets = tmp_path / "secrets.toml"
    secrets.write_text('[wallhaven]\napi_key = "k"\n')
    os.chmod(secrets, 0o644)
    c = config.load(cfg, secrets)
    assert c.interval_s == 3600
    assert c.sources[0].api_key == "k"
    assert "readable by other users" in caplog.text


def test_load_missing_files_uses_defaults(tmp_path: Path) -> None:
    assert config.load(tmp_path / "none.toml", tmp_path / "none2.toml") == config.parse({}, {})


def test_bad_toml(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("interval = ")
    with pytest.raises(ConfigError, match=r"config\.toml"):
        config.load(cfg, tmp_path / "secrets.toml")
