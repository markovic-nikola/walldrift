"""Backend commands for the applet: next | fav | ban | info | refill.

Each command reads the applet's settings as JSON on stdin (none means the schema's defaults) and
prints exactly one JSON line on stdout: a result, or {"error": "..."}. Logs go to stderr, which
Cinnamon sends to ~/.xsession-errors.
"""

import argparse
import fcntl
import logging
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from functools import cached_property
from typing import Any

from . import __version__, config, setter, sources
from .errors import HttpError, WalldriftError
from .http import HttpClient
from .models import Image
from .protocol import emit, fail
from .queue import Queue
from .store import Store

log = logging.getLogger("walldrift")


class App:
    """What the commands share, built on first use."""

    def __init__(self, settings_json: str | None) -> None:
        self._settings_json = settings_json

    @cached_property
    def config(self) -> config.Config:
        return config.load(self._settings_json, setter.largest_monitor)

    @cached_property
    def store(self) -> Store:
        return Store(config.data_dir() / "walldrift.db")

    @cached_property
    def queue(self) -> Queue:
        http = HttpClient()
        return Queue(
            self.config,
            self.store,
            http,
            sources.build(self.config, http),
            config.cache_dir() / "images",
        )

    def current(self) -> Image:
        image = self.store.current()
        if image is None:
            raise WalldriftError("No wallpaper has been shown yet.")
        return image

    @contextmanager
    def lock(self, name: str, wait: bool = True) -> Iterator[bool]:
        """Serializes backend runs: "show" guards changing the wallpaper, "refill" downloading.

        They are separate so a change is never stuck behind another run's downloads.
        """
        path = config.data_dir() / f"{name}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            yield True

    def result(self, image: Image | None, conflicts: list[setter.Conflict] | None = None) -> None:
        emit(
            {
                "image": _image_json(image) if image else None,
                "queued": self.store.queued_count(),
                "conflicts": [asdict(c) for c in conflicts or []],
            }
        )


def cmd_next(app: App) -> None:
    conflicts = setter.conflicts()
    with app.lock("show"):
        image = app.queue.pop()
        if image is None or image.path is None:
            raise WalldriftError(
                "No wallpaper available yet: nothing is downloaded and nothing could be fetched. "
                "Check the internet connection."
            )
        setter.set_wallpaper(image.path)
        app.store.mark_shown(image.key)
    app.result(app.store.get(image.key), conflicts)
    # The applet already has its answer; topping up the queue can fail or wait for the next run.
    with app.lock("refill", wait=False) as locked:
        if locked:
            try:
                app.queue.refill()
            except HttpError as e:
                log.warning("could not refill the queue: %s", e)
            app.queue.evict()


def cmd_refill(app: App) -> None:
    with app.lock("refill"):
        app.queue.refill()
        app.queue.evict()
    app.result(app.store.current())


def cmd_fav(app: App) -> None:
    image = app.current()
    if image.path is None or not image.path.exists():
        raise WalldriftError("The current wallpaper's file is no longer in the cache.")
    app.config.favorites_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image.path, app.config.favorites_dir / image.path.name)
    app.store.set_favorite(image.key)
    app.result(app.store.get(image.key))


def cmd_ban(app: App) -> None:
    image = app.current()
    app.store.ban(image.key)
    cmd_next(app)
    if image.path:
        image.path.unlink(missing_ok=True)


def cmd_info(app: App) -> None:
    app.result(app.store.current(), setter.conflicts())


COMMANDS: dict[str, tuple[Callable[[App], None], str]] = {
    "next": (cmd_next, "show the next wallpaper"),
    "fav": (cmd_fav, "copy the current wallpaper to the favorites folder"),
    "ban": (cmd_ban, "never show the current wallpaper again, and move on"),
    "info": (cmd_info, "describe the current wallpaper"),
    "refill": (cmd_refill, "download images until the queue is full"),
}


def _image_json(image: Image) -> dict[str, Any]:
    return {
        **asdict(image.candidate),
        "path": str(image.path) if image.path else None,
        "favorite": image.favorite,
        "shown_at": image.shown_at,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="walldrift", description="The walldrift applet's backend.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("-v", "--verbose", action="count", default=0, help="-v progress, -vv debug")
    commands = p.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for name, (_, help_text) in COMMANDS.items():
        commands.add_parser(name, help=help_text, description=help_text)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    level = [logging.WARNING, logging.INFO, logging.DEBUG][min(args.verbose, 2)]
    logging.basicConfig(level=level, format="walldrift: %(message)s")
    settings_json = None if sys.stdin.isatty() else sys.stdin.read()
    try:
        COMMANDS[args.command][0](App(settings_json))
    except WalldriftError as e:
        log.error("%s", e)
        return fail(str(e))
    except Exception as e:
        log.exception("unexpected error")
        return fail(f"Unexpected error ({type(e).__name__}); details are in ~/.xsession-errors.")
    return 0
