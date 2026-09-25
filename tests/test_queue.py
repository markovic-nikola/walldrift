import os
import random
import time
from pathlib import Path

import pytest

from walldrift.errors import HttpError
from walldrift.models import Candidate
from walldrift.queue import ORPHAN_AGE, Queue
from walldrift.store import Store

from .conftest import FakeHttp, FakeSource, candidate, make_config


def make_queue(
    store: Store,
    tmp_path: Path,
    pages: list[list[Candidate]],
    http: FakeHttp | None = None,
    settings: dict[str, object] | None = None,
) -> tuple[Queue, FakeSource]:
    source = FakeSource(pages)
    queue = Queue(
        make_config(settings), store, http or FakeHttp(), [source], tmp_path, random.Random(1)
    )
    return queue, source


def test_refill_downloads_until_full(store: Store, tmp_path: Path) -> None:
    queue, source = make_queue(
        store, tmp_path, [[candidate(n) for n in range(5)]], settings={"queue-size": 3}
    )
    assert queue.refill() == 3
    assert store.queued_count() == 3
    assert len(source.downloaded) == 3
    assert len(source.searches) == 1  # the candidate list is cached
    assert sorted(p.suffix for p in tmp_path.iterdir()) == [".jpg"] * 3


def test_small_and_known_images_are_skipped(store: Store, tmp_path: Path) -> None:
    pages = [[candidate(1, width=800, height=600), candidate(2), candidate(3)]]
    queue, _ = make_queue(store, tmp_path, pages, settings={"queue-size": 5})
    assert queue.refill() == 2
    assert store.known_keys(["fake:id1"]) == set()


def test_pop_fetches_when_queue_is_empty(store: Store, tmp_path: Path) -> None:
    queue, _ = make_queue(store, tmp_path, [[candidate(1)]])
    image = queue.pop()
    assert image is not None and image.key == "fake:id1"


def test_pop_falls_back_to_a_shown_image_when_offline(store: Store, tmp_path: Path) -> None:
    store.add(candidate(0, width=2160, height=3840), tmp_path / "tall.jpg", 10)  # never reshown
    store.mark_shown("fake:id0")
    for n in (1, 2):
        store.add(candidate(n), tmp_path / f"{n}.jpg", 10)
        store.mark_shown(f"fake:id{n}")
    queue, source = make_queue(store, tmp_path, [])

    def offline(topic: str | None, page: int) -> None:
        raise HttpError("offline")

    source.search = offline  # type: ignore[assignment,method-assign]
    image = queue.pop()
    assert image is not None and image.key == "fake:id1"  # not the current one


def test_unsupported_type_leaves_no_file(store: Store, tmp_path: Path) -> None:
    queue, _ = make_queue(store, tmp_path, [[candidate(1)]], FakeHttp(content_type="text/html"))
    with pytest.raises(HttpError, match="not a supported image"):
        queue.fetch_one()
    assert list(tmp_path.iterdir()) == []
    assert store.queued_count() == 0


def test_evict_removes_oldest_shown_files(store: Store, tmp_path: Path) -> None:
    mb = 1024 * 1024
    for n in (1, 2, 3):
        path = tmp_path / f"{n}.jpg"
        path.write_bytes(b"x")
        store.add(candidate(n), path, mb)
        store.mark_shown(f"fake:id{n}")
    queue, _ = make_queue(store, tmp_path, [], settings={"cache-limit-mb": 2})
    assert queue.evict() == 1
    assert not (tmp_path / "1.jpg").exists()
    assert (tmp_path / "3.jpg").exists()
    assert store.cache_bytes() == 2 * mb


def test_evict_removes_old_files_the_database_does_not_use(store: Store, tmp_path: Path) -> None:
    old = time.time() - ORPHAN_AGE - 1
    for name in ("known.jpg", "orphan.jpg", "fake-id9.123.part", "fresh.jpg"):
        (tmp_path / name).write_bytes(b"x")
        if name != "fresh.jpg":  # may belong to a run that hasn't recorded it yet
            os.utime(tmp_path / name, (old, old))
    store.add(candidate(1), tmp_path / "known.jpg", 1)
    queue, _ = make_queue(store, tmp_path, [])
    assert queue.evict() == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fresh.jpg", "known.jpg"]


def test_pop_drops_queued_images_that_no_longer_fit(store: Store, tmp_path: Path) -> None:
    portrait = tmp_path / "tall.jpg"
    portrait.write_bytes(b"x")
    store.add(candidate(1, width=2160, height=3840), portrait, 1)
    store.add(candidate(2), tmp_path / "2.jpg", 1)
    queue, _ = make_queue(store, tmp_path, [])
    image = queue.pop()
    assert image is not None and image.key == "fake:id2"
    assert not portrait.exists()
    assert store.known_keys(["fake:id1"]) == set()  # forgotten, not banned
