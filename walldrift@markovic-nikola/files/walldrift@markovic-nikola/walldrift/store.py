"""SQLite index of every image seen, plus cached candidate lists."""

import json
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, fields
from pathlib import Path

from .models import Candidate, Image, SearchPage

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    key         TEXT PRIMARY KEY,           -- "<source>:<id>"
    source      TEXT NOT NULL,
    id          TEXT NOT NULL,
    page_url    TEXT NOT NULL,
    image_url   TEXT NOT NULL,
    width       INTEGER NOT NULL,
    height      INTEGER NOT NULL,
    author      TEXT,
    author_url  TEXT,
    path        TEXT,                       -- file in the cache; NULL once evicted or banned
    size        INTEGER NOT NULL DEFAULT 0,
    queued_at   REAL NOT NULL,
    shown_at    REAL,                       -- NULL while waiting in the queue
    favorite    INTEGER NOT NULL DEFAULT 0,
    banned      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS images_shown_at ON images (shown_at);

CREATE TABLE IF NOT EXISTS candidate_lists (
    source      TEXT NOT NULL,
    topic       TEXT NOT NULL,              -- "" for no topic
    page        INTEGER NOT NULL,
    fetched_at  REAL NOT NULL,
    last_page   INTEGER NOT NULL,
    candidates  TEXT NOT NULL,              -- JSON list of Candidate fields
    PRIMARY KEY (source, topic, page)
);
"""

_CANDIDATE_COLUMNS = tuple(f.name for f in fields(Candidate))
_QUEUED = "path IS NOT NULL AND shown_at IS NULL AND NOT banned"
_SHOWN = "path IS NOT NULL AND shown_at IS NOT NULL AND NOT banned"


class Store:
    def __init__(self, path: Path | str, clock: Callable[[], float] = time.time) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._clock = clock
        self._db.execute("PRAGMA journal_mode=WAL")
        if self._db.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            self._db.executescript(SCHEMA)
            self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self._db.close()

    # Images

    def known_keys(self, keys: Iterable[str]) -> set[str]:
        """Which of these images were ever queued, shown or banned."""
        keys = list(keys)
        if not keys:
            return set()
        rows = self._db.execute(
            f"SELECT key FROM images WHERE key IN ({','.join('?' * len(keys))})", keys
        )
        return {row["key"] for row in rows}

    def add(self, candidate: Candidate, path: Path, size: int) -> None:
        columns = ("key", *_CANDIDATE_COLUMNS, "path", "size", "queued_at")
        values = (candidate.key, *asdict(candidate).values(), str(path), size, self._clock())
        # Two backend runs may fetch the same image; the first one to finish records it.
        placeholders = ",".join("?" * len(columns))
        self._db.execute(
            f"INSERT OR IGNORE INTO images ({','.join(columns)}) VALUES ({placeholders})", values
        )

    def get(self, key: str) -> Image | None:
        return self._one("key = ?", (key,))

    def next_queued(self) -> Image | None:
        return self._one(f"{_QUEUED} ORDER BY queued_at", ())

    def queued_count(self) -> int:
        count: int = self._db.execute(f"SELECT COUNT(*) FROM images WHERE {_QUEUED}").fetchone()[0]
        return count

    def current(self) -> Image | None:
        """The image shown most recently."""
        return self._one(f"{_SHOWN} ORDER BY shown_at DESC", ())

    def shown_in_random_order(self, exclude: str | None) -> list[Image]:
        """Previously shown images still in the cache, for when nothing new can be fetched."""
        rows = self._db.execute(
            f"SELECT * FROM images WHERE {_SHOWN} AND key IS NOT ? ORDER BY random()", (exclude,)
        )
        return [_image(row) for row in rows]

    def evictable(self) -> list[Image]:
        """Shown images still in the cache, least recently shown first, never the current one."""
        current = self.current()
        rows = self._db.execute(
            f"SELECT * FROM images WHERE {_SHOWN} AND key IS NOT ? ORDER BY shown_at",
            (current.key if current else None,),
        )
        return [_image(row) for row in rows]

    def cache_bytes(self) -> int:
        total: int = self._db.execute(
            "SELECT COALESCE(SUM(size), 0) FROM images WHERE path IS NOT NULL"
        ).fetchone()[0]
        return total

    def cached_paths(self) -> set[Path]:
        """Every file the database still counts as in the cache."""
        rows = self._db.execute("SELECT path FROM images WHERE path IS NOT NULL")
        return {Path(row["path"]) for row in rows}

    def mark_shown(self, key: str) -> None:
        self._update(key, shown_at=self._clock())

    def set_favorite(self, key: str) -> None:
        self._update(key, favorite=1)

    def ban(self, key: str) -> None:
        self._update(key, banned=1, path=None)

    def forget_file(self, key: str) -> None:
        self._update(key, path=None)

    def forget(self, key: str) -> None:
        """Removes the image entirely, so it can be picked again if it suits later settings."""
        self._db.execute("DELETE FROM images WHERE key = ?", (key,))

    # Candidate lists

    def candidates(
        self, source: str, topic: str | None, page: int, max_age_s: float
    ) -> list[Candidate] | None:
        """A cached candidate list, or None when it is missing or older than max_age_s."""
        row = self._db.execute(
            "SELECT candidates FROM candidate_lists"
            " WHERE source = ? AND topic = ? AND page = ? AND fetched_at >= ?",
            (source, topic or "", page, self._clock() - max_age_s),
        ).fetchone()
        return [Candidate(**item) for item in json.loads(row["candidates"])] if row else None

    def save_candidates(
        self, source: str, topic: str | None, page: int, result: SearchPage
    ) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO candidate_lists VALUES (?, ?, ?, ?, ?, ?)",
            (
                source,
                topic or "",
                page,
                self._clock(),
                result.last_page,
                json.dumps([asdict(c) for c in result.candidates]),
            ),
        )

    def last_page(self, source: str, topic: str | None) -> int | None:
        """How many result pages the source reported the last time it was asked."""
        row = self._db.execute(
            "SELECT last_page FROM candidate_lists WHERE source = ? AND topic = ?"
            " ORDER BY fetched_at DESC LIMIT 1",
            (source, topic or ""),
        ).fetchone()
        return int(row["last_page"]) if row else None

    def _one(self, where: str, params: tuple[object, ...]) -> Image | None:
        row = self._db.execute(f"SELECT * FROM images WHERE {where} LIMIT 1", params).fetchone()
        return _image(row) if row else None

    def _update(self, key: str, **values: object) -> None:
        assignments = ", ".join(f"{column} = ?" for column in values)
        self._db.execute(f"UPDATE images SET {assignments} WHERE key = ?", (*values.values(), key))


def _image(row: sqlite3.Row) -> Image:
    return Image(
        candidate=Candidate(**{column: row[column] for column in _CANDIDATE_COLUMNS}),
        path=Path(row["path"]) if row["path"] else None,
        size=row["size"],
        shown_at=row["shown_at"],
        favorite=bool(row["favorite"]),
        banned=bool(row["banned"]),
    )
