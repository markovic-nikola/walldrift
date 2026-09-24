import pytest

from walldrift import sources
from walldrift.errors import ConfigError
from walldrift.sources.wallhaven import Wallhaven

from .conftest import FakeHttp, make_config

ITEM = {
    "id": "w5x99p",
    "url": "https://wallhaven.cc/w/w5x99p",
    "path": "https://w.wallhaven.cc/full/w5/wallhaven-w5x99p.jpg",
    "dimension_x": 6144,
    "dimension_y": 3710,
    "purity": "sfw",
}
BODY = {"data": [ITEM, {**ITEM, "id": "nsfw", "purity": "nsfw"}], "meta": {"last_page": 7}}


def wallhaven(http: FakeHttp, **options: object) -> Wallhaven:
    settings = {f"wallhaven-{key}": value for key, value in options.items()}
    [source] = sources.build(make_config({**settings, "min-resolution": "3840x2160"}), http)
    assert isinstance(source, Wallhaven)
    return source


def test_search_builds_query_and_parses_results() -> None:
    http = FakeHttp([BODY])
    page = wallhaven(http, people=True).search("nature", 2)

    url, params, headers = http.requests[0]
    assert url == "https://wallhaven.cc/api/v1/search"
    assert params == {
        "sorting": "toplist",
        "topRange": "1M",
        "categories": "101",
        "purity": "100",
        "atleast": "3840x2160",
        "page": "2",
        "q": "nature",
    }
    assert headers == {}
    assert page.last_page == 7
    [c] = page.candidates  # the non-SFW item is dropped
    assert (c.key, c.width, c.height) == ("wallhaven:w5x99p", 6144, 3710)
    assert c.image_url == ITEM["path"]


def test_no_topic_non_toplist_sorting_and_api_key() -> None:
    http = FakeHttp([BODY])
    wallhaven(http, sorting="views", **{"api-key": "k"}).search(None, 1)
    _, params, headers = http.requests[0]
    assert "q" not in params
    assert "topRange" not in params
    assert headers == {"X-API-Key": "k"}


@pytest.mark.parametrize(
    "options",
    [
        {"sorting": "new"},
        {"top-range": "2w"},
        {"general": False},
        {"anime": "yes"},
    ],
)
def test_invalid_options(options: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        wallhaven(FakeHttp(), **options)


def test_build_needs_an_enabled_source() -> None:
    with pytest.raises(ConfigError, match="no sources are enabled"):
        sources.build(make_config({"wallhaven-enabled": False}), FakeHttp())
