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
    config = make_config(sources={"wallhaven": options}, min_resolution="3840x2160")
    [source] = sources.build(config, http)
    assert isinstance(source, Wallhaven)
    return source


def test_search_builds_query_and_parses_results() -> None:
    http = FakeHttp([BODY])
    page = wallhaven(http, categories=["general", "people"]).search("nature", 2)

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


def test_no_topic_and_non_toplist_sorting() -> None:
    http = FakeHttp([BODY])
    wallhaven(http, sorting="views").search(None, 1)
    params = http.requests[0][1]
    assert "q" not in params
    assert "topRange" not in params


@pytest.mark.parametrize(
    "options",
    [
        {"sorting": "new"},
        {"top_range": "2w"},
        {"categories": []},
        {"categories": ["cats"]},
        {"x": 1},
    ],
)
def test_invalid_options(options: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        wallhaven(FakeHttp(), **options)


def test_build_skips_unknown_and_disabled_sources() -> None:
    config = make_config(sources={"wallhaven": {"enabled": False}, "nope": {}})
    with pytest.raises(ConfigError, match="no sources are enabled"):
        sources.build(config, FakeHttp())
