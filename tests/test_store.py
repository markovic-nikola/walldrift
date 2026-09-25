from pathlib import Path

from walldrift.models import SearchPage
from walldrift.store import Store

from .conftest import Clock, candidate


def test_queue_order_and_current(store: Store) -> None:
    for n in (1, 2):
        store.add(candidate(n), Path(f"/c/{n}.jpg"), 10)
    assert store.queued_count() == 2
    assert store.current() is None

    first = store.next_queued()
    assert first is not None and first.key == "fake:id1"
    store.mark_shown(first.key)

    assert store.queued_count() == 1
    current = store.current()
    assert current is not None and current.key == "fake:id1"
    assert current.candidate == candidate(1)


def test_known_keys(store: Store) -> None:
    store.add(candidate(1), Path("/c/1.jpg"), 10)
    assert store.known_keys(["fake:id1", "fake:id2"]) == {"fake:id1"}
    assert store.known_keys([]) == set()


def test_ban_hides_image_and_drops_file(store: Store) -> None:
    store.add(candidate(1), Path("/c/1.jpg"), 10)
    store.mark_shown("fake:id1")
    store.ban("fake:id1")
    assert store.current() is None
    assert store.cache_bytes() == 0
    assert store.known_keys(["fake:id1"]) == {"fake:id1"}


def test_evictable_excludes_current_and_queued(store: Store) -> None:
    for n in (1, 2, 3, 4):
        store.add(candidate(n), Path(f"/c/{n}.jpg"), 10)
    for n in (1, 2, 3):
        store.mark_shown(f"fake:id{n}")
    assert [i.key for i in store.evictable()] == ["fake:id1", "fake:id2"]
    assert store.cache_bytes() == 40


def test_shown_in_random_order_skips_excluded(store: Store) -> None:
    store.add(candidate(1), Path("/c/1.jpg"), 10)
    store.mark_shown("fake:id1")
    assert store.shown_in_random_order(exclude="fake:id1") == []
    assert [i.key for i in store.shown_in_random_order(exclude=None)] == ["fake:id1"]


def test_candidate_cache_expires(store: Store, clock: Clock) -> None:
    page = SearchPage([candidate(1), candidate(2)], last_page=4)
    store.save_candidates("fake", None, 1, page)
    assert store.candidates("fake", None, 1, max_age_s=60) == page.candidates
    assert store.candidates("fake", "space", 1, max_age_s=60) is None
    assert store.last_page("fake", None) == 4
    clock.now += 120
    assert store.candidates("fake", None, 1, max_age_s=60) is None


def test_reopening_keeps_data(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "db.sqlite"
    store = Store(path)
    store.add(candidate(1), Path("/c/1.jpg"), 10)
    store.close()
    assert Store(path).queued_count() == 1
