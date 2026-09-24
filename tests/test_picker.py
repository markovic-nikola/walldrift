import random
from pathlib import Path

from walldrift.picker import TOP_PAGES, pick
from walldrift.store import Store

from .conftest import FakeSource, candidate


def test_picks_random_page_once_page_count_is_known(store: Store) -> None:
    pages = [[candidate(p * 100 + n) for n in range(3)] for p in range(TOP_PAGES + 5)]
    source = FakeSource(pages, topics=("space",))
    rng = random.Random(0)
    for _ in range(20):
        picked = pick([source], store, rng)
        assert picked is not None
        store.add(picked[1], Path("/x"), 1)
    assert source.searches[0] == ("space", 1)
    assert {page for _, page in source.searches} <= set(range(1, TOP_PAGES + 1))
    assert len({page for _, page in source.searches}) > 1


def test_returns_none_when_everything_is_known(store: Store) -> None:
    source = FakeSource([[candidate(1)]])
    store.add(candidate(1), Path("/x"), 1)
    assert pick([source], store, random.Random(0)) is None
