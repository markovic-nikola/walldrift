from pathlib import Path

import pytest

from walldrift import config
from walldrift.errors import ConfigError

from .conftest import SCREEN, make_config


def test_defaults_come_from_the_schema() -> None:
    c = make_config()
    assert (c.min_width, c.min_height) == SCREEN  # "auto"
    assert c.queue_size == 3
    assert c.cache_limit_bytes == 1024 * 2**20
    assert c.favorites_dir == Path.home() / "Pictures/Wallpapers"
    [wallhaven] = c.sources
    assert (wallhaven.name, wallhaven.enabled, wallhaven.weight) == ("wallhaven", True, 1.0)
    assert wallhaven.topics == ()
    assert wallhaven.api_key is None
    assert wallhaven.options == {
        "sorting": "toplist",
        "top-range": "1M",
        "general": True,
        "anime": False,
        "people": False,
    }


def test_load_without_settings_uses_defaults() -> None:
    assert config.load(None, lambda: SCREEN) == make_config()
    assert config.load("  ", lambda: SCREEN) == make_config()


def test_load_merges_given_settings() -> None:
    c = config.load('{"queue-size": 7, "topics": "space"}', lambda: SCREEN)
    assert c.queue_size == 7
    assert c.sources[0].topics == ("space",)


def test_explicit_resolution_skips_screen_detection() -> None:
    def no_screen() -> tuple[int, int]:
        raise AssertionError("should not be called")

    c = config.parse({**config.defaults(), "min-resolution": "3840x2160"}, no_screen)
    assert (c.min_width, c.min_height) == (3840, 2160)


def test_topics_are_comma_separated_and_sources_can_override() -> None:
    c = make_config({"topics": " nature, space ,, minimal ", "wallhaven-topics": ""})
    assert c.sources[0].topics == ("nature", "space", "minimal")
    c = make_config({"topics": "nature", "wallhaven-topics": "cyberpunk"})
    assert c.sources[0].topics == ("cyberpunk",)


def test_api_key_is_trimmed() -> None:
    assert make_config({"wallhaven-api-key": "  k  "}).sources[0].api_key == "k"


def test_spinbutton_floats_are_accepted() -> None:
    assert make_config({"queue-size": 4.0}).queue_size == 4


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/data/walls", Path("/data/walls")),
        ("file:///data/my%20walls", Path("/data/my walls")),
        ("~/Walls", Path.home() / "Walls"),
    ],
)
def test_favorites_dir_forms(value: str, expected: Path) -> None:
    assert make_config({"favorites-dir": value}).favorites_dir == expected


@pytest.mark.parametrize(
    "overrides",
    [
        {"min-resolution": "big"},
        {"queue-size": 0},
        {"queue-size": 2.5},
        {"cache-limit-mb": True},
        {"topics": ["nature"]},
        {"favorites-dir": "relative/path"},
        {"wallhaven-weight": 0},
        {"wallhaven-enabled": "yes"},
    ],
)
def test_invalid_settings(overrides: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        make_config(overrides)


def test_source_missing_a_shared_setting() -> None:
    values = config.defaults()
    del values["wallhaven-weight"]
    with pytest.raises(ConfigError, match="wallhaven-weight"):
        config.parse(values, lambda: SCREEN)


def test_bad_json() -> None:
    with pytest.raises(ConfigError, match="not valid JSON"):
        config.load("{", lambda: SCREEN)
