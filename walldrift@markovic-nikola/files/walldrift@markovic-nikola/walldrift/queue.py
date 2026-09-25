"""Keeps images downloaded ahead of time and trims the cache."""

import logging
import os
import random
import re
from collections.abc import Sequence
from pathlib import Path

from .config import Config
from .errors import HttpError
from .http import HttpClient
from .models import Candidate, Image
from .picker import pick
from .sources.base import Source
from .store import Store

log = logging.getLogger(__name__)

EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class Queue:
    def __init__(
        self,
        config: Config,
        store: Store,
        http: HttpClient,
        sources: Sequence[Source],
        images_dir: Path,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._http = http
        self._sources = sources
        self._images_dir = images_dir
        self._rng = rng or random.Random()

    def pop(self) -> Image | None:
        """The next image to show: queued if possible, else fetched now, else an old one."""
        image = self._next_fitting()
        if image is None:
            try:
                if self.fetch_one():
                    image = self._next_fitting()
            except HttpError as e:
                log.warning("could not fetch a new image: %s", e)
        if image is None:
            current = self._store.current()
            shown = self._store.shown_in_random_order(exclude=current.key if current else None)
            image = next((i for i in shown if self._fits(i)), None)
        return image

    def _fits(self, image: Image) -> bool:
        return image.candidate.fits(self._config.min_width, self._config.min_height)

    def _next_fitting(self) -> Image | None:
        """The oldest queued image that suits the current settings, dropping any that don't.

        Images queued before a setting changed (e.g. a higher minimum resolution) may not.
        """
        while (image := self._store.next_queued()) is not None:
            if self._fits(image):
                return image
            log.info("dropping %s: it no longer fits the screen settings", image.key)
            if image.path:
                image.path.unlink(missing_ok=True)
            self._store.forget(image.key)
        return None

    def refill(self) -> int:
        """Downloads until queue_size images are waiting; returns how many were added."""
        added = 0
        while self._store.queued_count() < self._config.queue_size and self.fetch_one():
            added += 1
        return added

    def fetch_one(self) -> bool:
        picked = pick(self._sources, self._store, self._rng)
        if picked is None:
            log.info("every source is out of new images for now")
            return False
        source, candidate = picked
        path = self._download(candidate)
        source.on_download(candidate)
        self._store.add(candidate, path, path.stat().st_size)
        log.info("queued %s", candidate.page_url)
        return True

    def evict(self) -> int:
        """Deletes the least recently shown files until the cache fits its limit."""
        total = self._store.cache_bytes()
        removed = 0
        for image in self._store.evictable():
            if total <= self._config.cache_limit_bytes:
                break
            if image.path:
                image.path.unlink(missing_ok=True)
            self._store.forget_file(image.key)
            total -= image.size
            removed += 1
        return removed

    def _download(self, candidate: Candidate) -> Path:
        self._images_dir.mkdir(parents=True, exist_ok=True)
        # One file per image, so Cinnamon always sees a new path and reloads it.
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", f"{candidate.source}-{candidate.id}")
        # Another backend run may be fetching the same image; each writes its own part file.
        part = self._images_dir / f"{stem}.{os.getpid()}.part"
        try:
            content_type = self._http.download(candidate.image_url, part)
            extension = EXTENSIONS.get(content_type)
            if extension is None:
                raise HttpError(f"{candidate.image_url} is {content_type}, not a supported image")
            return part.replace(self._images_dir / f"{stem}{extension}")
        finally:
            part.unlink(missing_ok=True)
