"""Chooses the next image to download: source by weight, then topic, then a random top page."""

import logging
import random
from collections.abc import Sequence

from .models import Candidate
from .sources.base import Source
from .store import Store

log = logging.getLogger(__name__)

TOP_PAGES = 10
"""Only the first pages of each popular list count as "popular"."""
CANDIDATE_TTL_S = 12 * 3600
ATTEMPTS = 5


def pick(
    sources: Sequence[Source], store: Store, rng: random.Random
) -> tuple[Source, Candidate] | None:
    for _ in range(ATTEMPTS):
        source = rng.choices(sources, weights=[s.weight for s in sources])[0]
        topic = rng.choice(source.topics) if source.topics else None
        candidates = _candidates(source, topic, store, rng)
        known = store.known_keys(c.key for c in candidates)
        fresh = [c for c in candidates if c.key not in known and c.fits(*source.min_size)]
        if fresh:
            return source, rng.choice(fresh)
        log.debug("no new images from %s (topic %r)", source.name, topic)
    return None


def _candidates(
    source: Source, topic: str | None, store: Store, rng: random.Random
) -> list[Candidate]:
    pages = min(store.last_page(source.name, topic) or 1, TOP_PAGES)
    page = rng.randint(1, pages)
    cached = store.candidates(source.name, topic, page, CANDIDATE_TTL_S)
    if cached is not None:
        return cached
    result = source.search(topic, page)
    store.save_candidates(source.name, topic, page, result)
    return result.candidates
