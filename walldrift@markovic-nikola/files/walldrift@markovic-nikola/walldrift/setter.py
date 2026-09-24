"""Cinnamon backend: sets the wallpaper, finds conflicts and reads the monitors."""

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SetterError

BACKGROUND_SCHEMA = "org.cinnamon.desktop.background"
SLIDESHOW_SCHEMA = "org.cinnamon.desktop.background.slideshow"
CINNAMON_SCHEMA = "org.cinnamon"
CONFLICTING_EXTENSIONS = ("cinnamon-dynamic-wallpaper@",)


@dataclass(frozen=True)
class Conflict:
    """Something that would overwrite our wallpaper, and the settings page that turns it off."""

    message: str
    settings_module: str
    """A cinnamon-settings module name, e.g. "extensions"."""


def set_wallpaper(path: Path) -> None:
    Gio = _gi("Gio")
    _settings(BACKGROUND_SCHEMA).set_string("picture-uri", path.as_uri())
    Gio.Settings.sync()


def conflicts() -> list[Conflict]:
    found = []
    if _settings(SLIDESHOW_SCHEMA).get_boolean("slideshow-enabled"):
        found.append(
            _conflict("Cinnamon's background slideshow", "Backgrounds > Settings", "backgrounds")
        )
    for extension in _settings(CINNAMON_SCHEMA).get_strv("enabled-extensions"):
        if extension.startswith(CONFLICTING_EXTENSIONS):
            found.append(_conflict(f"The {extension} extension", "Extensions", "extensions"))
    return found


def largest_monitor() -> tuple[int, int]:
    """The largest monitor's native mode, as landscape (width >= height).

    Uses the panel's real mode, not the framebuffer size, which fractional scaling inflates.
    """
    Gdk = _gi("Gdk", "3.0")
    CinnamonDesktop = _gi("CinnamonDesktop", "3.0")
    screen = Gdk.Screen.get_default()
    if screen is None:
        raise SetterError("no display found; choose a minimum resolution in the settings")
    # Keep a reference: the outputs belong to rr_screen and are freed along with it.
    rr_screen = CinnamonDesktop.RRScreen.new(screen)
    sizes = [
        (mode.get_width(), mode.get_height())
        for output in rr_screen.list_outputs()
        if (mode := output.get_current_mode())
    ]
    if not sizes:
        raise SetterError("no active monitor found; choose a minimum resolution in the settings")
    width, height = max(sizes, key=lambda size: size[0] * size[1])
    return max(width, height), min(width, height)


def _conflict(what: str, where: str, settings_module: str) -> Conflict:
    return Conflict(
        f"{what} will replace walldrift's wallpaper. Turn it off in System Settings > {where}.",
        settings_module,
    )


def _settings(schema: str) -> Any:
    Gio = _gi("Gio")
    # Gio.Settings.new() aborts the process on an unknown schema, so check first.
    schemas = Gio.SettingsSchemaSource.get_default()
    if schemas is None or schemas.lookup(schema, True) is None:
        raise SetterError(f"GSettings schema {schema} not found; walldrift needs Cinnamon")
    return Gio.Settings.new(schema)


def _gi(namespace: str, version: str | None = None) -> Any:
    """Imports a GObject library lazily, so the rest of the backend runs without one."""
    try:
        import gi

        if version:
            gi.require_version(namespace, version)
        return importlib.import_module(f"gi.repository.{namespace}")
    except (ImportError, ValueError) as e:
        raise SetterError(f"{namespace} {version or ''} is missing; install python3-gi") from e
