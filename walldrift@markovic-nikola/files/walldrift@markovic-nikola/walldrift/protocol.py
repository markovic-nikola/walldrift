"""The one JSON line each backend command prints for the applet.

Must import on old Pythons too: __main__ uses it to report that Python is too old.
"""

from __future__ import annotations

import json
import sys
from typing import Any

_sent = False


def emit(result: dict[str, Any]) -> None:
    """Prints the command's result. Only the first call per process counts."""
    global _sent
    if not _sent:
        _sent = True
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()


def fail(message: str) -> int:
    emit({"error": message})
    return 1
