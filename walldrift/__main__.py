"""Command line: walldrift next | fav | ban | info | open | refill | install-timer."""

import argparse
import fcntl
import logging
import shutil
import sys
import webbrowser
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path

from . import __version__, config, setter, sources, systemd
from .errors import HttpError, WalldriftError
from .http import HttpClient
from .models import Image
from .queue import Queue
from .store import Store

log = logging.getLogger("walldrift")


class App:
    """What the commands share, built on first use."""

    @cached_property
    def config(self) -> config.Config:
        return config.load()

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
            raise WalldriftError("no wallpaper has been shown yet; run: walldrift next")
        return image

    @contextmanager
    def lock(self, wait: bool = True) -> Iterator[bool]:
        """Keeps the timer and a keyboard shortcut from changing the queue at the same time."""
        path = config.data_dir() / "lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            yield True


def cmd_next(app: App, args: argparse.Namespace) -> None:
    for problem in setter.conflicts():
        log.warning("%s", problem)
    with app.lock():
        image = app.queue.pop()
        if image is None or image.path is None:
            raise WalldriftError(
                "no wallpaper available: the queue is empty and nothing downloaded"
            )
        setter.set_wallpaper(image.path)
        app.store.mark_shown(image.key)
    # The new wallpaper is already up; topping up the queue can fail or wait for the next run.
    with app.lock(wait=False) as locked:
        if locked:
            try:
                app.queue.refill()
            except HttpError as e:
                log.warning("could not refill the queue: %s", e)
            app.queue.evict()


def cmd_refill(app: App, args: argparse.Namespace) -> None:
    with app.lock():
        added = app.queue.refill()
        app.queue.evict()
    print(f"Added {added}; {app.store.queued_count()} ready.")


def cmd_fav(app: App, args: argparse.Namespace) -> None:
    image = app.current()
    if image.path is None or not image.path.exists():
        raise WalldriftError("the current wallpaper's file is gone from the cache")
    app.config.favorites_dir.mkdir(parents=True, exist_ok=True)
    saved = Path(shutil.copy2(image.path, app.config.favorites_dir / image.path.name))
    app.store.set_favorite(image.key)
    print(f"Saved {saved}")


def cmd_ban(app: App, args: argparse.Namespace) -> None:
    image = app.current()
    app.store.ban(image.key)
    cmd_next(app, args)
    if image.path:
        image.path.unlink(missing_ok=True)


def cmd_info(app: App, args: argparse.Namespace) -> None:
    image = app.current()
    c = image.candidate
    rows = [
        ("Page", c.page_url),
        ("By", f"{c.author} ({c.author_url})" if c.author else None),
        ("Source", c.source),
        ("Size", f"{c.width}x{c.height}"),
        ("File", str(image.path) if image.path else None),
        ("Favorite", "yes" if image.favorite else "no"),
        ("Queue", f"{app.store.queued_count()} ready"),
    ]
    for label, value in rows:
        if value:
            print(f"{label + ':':<10}{value}")


def cmd_open(app: App, args: argparse.Namespace) -> None:
    url = app.current().candidate.page_url
    if not webbrowser.open(url):
        raise WalldriftError(f"could not open a browser; the page is {url}")


def cmd_install_timer(app: App, args: argparse.Namespace) -> None:
    if args.remove:
        systemd.remove()
        print("Timer removed.")
    else:
        directory = systemd.install(app.config.interval_s)
        print(f"Timer installed in {directory}; interval {app.config.interval_s}s.")


Command = Callable[[App, argparse.Namespace], None]
COMMANDS: dict[str, tuple[Command, str]] = {
    "next": (cmd_next, "show the next wallpaper"),
    "fav": (cmd_fav, "copy the current wallpaper to favorites_dir"),
    "ban": (cmd_ban, "never show the current wallpaper again, and move on"),
    "info": (cmd_info, "show where the current wallpaper came from"),
    "open": (cmd_open, "open the current wallpaper's page in a browser"),
    "refill": (cmd_refill, "download images until the queue is full"),
    "install-timer": (cmd_install_timer, "change the wallpaper on a timer (systemd user unit)"),
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="walldrift", description="Random popular wallpapers for Cinnamon."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v for progress, -vv for debug"
    )
    commands = p.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for name, (func, help_text) in COMMANDS.items():
        commands.add_parser(name, help=help_text, description=help_text).set_defaults(func=func)
    commands.choices["install-timer"].add_argument(
        "--remove", action="store_true", help="uninstall it"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    level = [logging.WARNING, logging.INFO, logging.DEBUG][min(args.verbose, 2)]
    logging.basicConfig(level=level, format="walldrift: %(message)s")
    try:
        args.func(App(), args)
    except WalldriftError as e:
        log.error("%s", e)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
