"""Cinnamon backend: sets the wallpaper through GSettings."""

from pathlib import Path
from typing import Any

from .errors import SetterError

BACKGROUND_SCHEMA = "org.cinnamon.desktop.background"
SLIDESHOW_SCHEMA = "org.cinnamon.desktop.background.slideshow"
CINNAMON_SCHEMA = "org.cinnamon"
CONFLICTING_EXTENSIONS = ("cinnamon-dynamic-wallpaper@",)


def set_wallpaper(path: Path) -> None:
    from gi.repository import Gio

    _settings(BACKGROUND_SCHEMA).set_string("picture-uri", path.as_uri())
    Gio.Settings.sync()


def conflicts() -> list[str]:
    """Other things that would overwrite the wallpaper we set, and how to turn them off."""
    found = []
    if _settings(SLIDESHOW_SCHEMA).get_boolean("slideshow-enabled"):
        found.append(_conflict("Cinnamon's background slideshow", "Backgrounds > Settings"))
    for extension in _settings(CINNAMON_SCHEMA).get_strv("enabled-extensions"):
        if extension.startswith(CONFLICTING_EXTENSIONS):
            found.append(_conflict(f"the {extension} extension", "Extensions"))
    return found


def _conflict(what: str, settings_page: str) -> str:
    return (
        f"{what} will replace walldrift's wallpaper; "
        f"turn it off in System Settings > {settings_page}"
    )


def _settings(schema: str) -> Any:
    try:
        from gi.repository import Gio
    except ImportError as e:
        raise SetterError("PyGObject is missing; install python3-gi") from e
    # Gio.Settings.new() aborts the process on an unknown schema, so check first.
    schemas = Gio.SettingsSchemaSource.get_default()
    if schemas is None or schemas.lookup(schema, True) is None:
        raise SetterError(f"GSettings schema {schema} not found; walldrift needs Cinnamon")
    return Gio.Settings.new(schema)
