# walldrift

A random wallpaper changer for Linux Mint (Cinnamon) that pulls popular wallpapers from online
sources, filtered by topics you choose. It keeps a few images downloaded ahead, so changing the
wallpaper is instant and still works offline.

Status: early. Wallhaven is the only source so far; Unsplash and Pexels are next.
See [PLAN.md](PLAN.md) for the design.

## Requirements

- Linux Mint 22 or later (Cinnamon), or another Cinnamon desktop with Python 3.11+
- `python3-gi` (PyGObject), which Mint installs by default

## Install

PyGObject comes from the system, not from PyPI, so the pipx environment must see system packages:

```bash
pipx install --system-site-packages .
```

Then show a first wallpaper and start the timer:

```bash
walldrift next
walldrift install-timer
```

Turn off Cinnamon's background slideshow and any wallpaper-changing extension (such as
cinnamon-dynamic-wallpaper), or they will overwrite the wallpaper. `walldrift next` warns when it
finds one.

## Use

| Command | What it does |
|---|---|
| `walldrift next` | Show the next wallpaper |
| `walldrift fav` | Copy the current wallpaper to `favorites_dir` |
| `walldrift ban` | Never show the current wallpaper again, and move on |
| `walldrift info` | Show where the current wallpaper came from |
| `walldrift open` | Open the current wallpaper's page in a browser |
| `walldrift refill` | Download images until the queue is full |
| `walldrift install-timer [--remove]` | Change the wallpaper every `interval` |

To bind `next`, `fav` and `ban` to keys, add them under System Settings > Keyboard > Shortcuts >
Custom Shortcuts.

## Configure

Everything is optional. `~/.config/walldrift/config.toml`:

```toml
interval = "30m"              # run `walldrift install-timer` again after changing it
min_resolution = "1920x1080"  # skip anything smaller
cache_limit_mb = 1024
queue_size = 3
favorites_dir = "~/Pictures/Wallpapers"
topics = []                   # e.g. ["nature", "space"]; empty means top images overall

[sources.wallhaven]
enabled = true
weight = 1                    # relative chance this source is picked
sorting = "toplist"           # toplist | views | favorites
top_range = "1M"              # 1d 3d 1w 1M 3M 6M 1y
categories = ["general"]      # general | anime | people
# topics = ["cyberpunk"]      # overrides the global topics for this source
```

API keys go in `~/.config/walldrift/secrets.toml`, which should be `chmod 600`:

```toml
[wallhaven]
api_key = "..."   # optional
```

Files: the database (favorites, bans, history) is in `~/.local/share/walldrift/`; downloaded
images are in `~/.cache/walldrift/`.

## Develop

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/mypy walldrift
```

## Credits and license

Images belong to their creators; walldrift links back to each image's page (`walldrift info`)
and never redistributes them. walldrift is licensed under the GPL-3.0-or-later.
