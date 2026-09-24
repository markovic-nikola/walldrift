"""Writes and enables the systemd user timer, using the interval from the config."""

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .config import APP, xdg_config_home
from .errors import WalldriftError

SERVICE_FILE = f"{APP}.service"
TIMER_FILE = f"{APP}.timer"

SERVICE = """\
[Unit]
Description=Change the desktop wallpaper (walldrift)

[Service]
Type=oneshot
ExecStart={command} next
"""

TIMER = """\
[Unit]
Description=Change the desktop wallpaper periodically (walldrift)

[Timer]
OnActiveSec={seconds}s
OnUnitActiveSec={seconds}s

[Install]
WantedBy=timers.target
"""


def unit_dir() -> Path:
    return xdg_config_home() / "systemd" / "user"


def units(interval_s: int, command: str) -> dict[str, str]:
    return {
        SERVICE_FILE: SERVICE.format(command=command),
        TIMER_FILE: TIMER.format(seconds=interval_s),
    }


def command() -> str:
    """How the service should run walldrift: the installed script, or this interpreter."""
    script = Path(sys.argv[0])
    if script.name == APP:
        return shlex.quote(str(script.resolve()))
    return shlex.join([sys.executable, "-m", APP])


def install(interval_s: int) -> Path:
    directory = unit_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for filename, text in units(interval_s, command()).items():
        (directory / filename).write_text(text)
    _systemctl("daemon-reload")
    _systemctl("enable", TIMER_FILE)
    _systemctl("restart", TIMER_FILE)  # picks up a changed interval
    return directory


def remove() -> None:
    directory = unit_dir()
    if (directory / TIMER_FILE).exists():
        _systemctl("disable", "--now", TIMER_FILE)
    for filename in (SERVICE_FILE, TIMER_FILE):
        (directory / filename).unlink(missing_ok=True)
    _systemctl("daemon-reload")


def _systemctl(*args: str) -> None:
    if shutil.which("systemctl") is None:
        raise WalldriftError("systemctl not found; the timer needs systemd")
    result = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise WalldriftError(f"systemctl --user {' '.join(args)}: {result.stderr.strip()}")
