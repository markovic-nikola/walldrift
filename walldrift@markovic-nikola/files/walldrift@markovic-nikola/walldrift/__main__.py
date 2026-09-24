import sys

from .protocol import fail

MIN_PYTHON = (3, 11)

if sys.version_info < MIN_PYTHON:
    needed = ".".join(map(str, MIN_PYTHON))
    sys.exit(
        fail(f"walldrift needs Python {needed} or newer; this system has {sys.version.split()[0]}.")
    )

from .cli import main  # noqa: E402 - only safe to import after the version check

sys.exit(main())
