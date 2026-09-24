"""Random wallpaper changer for Linux Mint (Cinnamon)."""

from importlib.metadata import metadata

# pyproject.toml is the one place these are written; read them back from the installed package.
_metadata = metadata(__name__)
_urls = dict(url.split(", ", 1) for url in _metadata.get_all("Project-URL") or [])

__version__: str = _metadata["Version"]
HOMEPAGE: str = _urls["Homepage"]
"""Sent in the User-Agent so API operators can reach us."""
