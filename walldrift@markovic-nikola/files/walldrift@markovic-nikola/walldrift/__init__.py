"""The walldrift applet's backend: picks, downloads and sets wallpapers."""

import json
from pathlib import Path

APPLET_DIR = Path(__file__).resolve().parent.parent
"""The applet folder, which holds metadata.json and settings-schema.json."""

# metadata.json is the one place these are written.
_metadata = json.loads((APPLET_DIR / "metadata.json").read_text())
__version__: str = _metadata["version"]
HOMEPAGE: str = _metadata["url"]
