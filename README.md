# walldrift

A Cinnamon applet that sets random popular wallpapers from online sources, filtered by topics you
choose. User documentation: [walldrift@markovic-nikola/README.md](walldrift@markovic-nikola/README.md).
Design and roadmap: [PLAN.md](PLAN.md).

Status: early. Wallhaven is the only source so far; Unsplash and Pexels are next.

## How it's built

- `applet.js` runs inside Cinnamon. It keeps time, draws the menu and shows notifications.
- `walldrift/` is a Python backend (standard library + PyGObject) that the applet runs as
  `/usr/bin/python3 -m walldrift <command>`. It gets the settings as JSON on stdin and answers
  with one JSON line on stdout.
- `settings-schema.json` defines every setting and its default. Cinnamon draws the settings
  window from it.

The `walldrift@markovic-nikola/` folder has the layout Cinnamon Spices expects, so publishing is a
copy of that folder.

## Develop

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --group dev
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/mypy
```

Try the applet from this checkout:

```bash
scripts/dev-install.sh
```

It links the applet into `~/.local/share/cinnamon/applets/` and reloads it. Run it again after each
change. Applet logs appear in Looking Glass (`Alt+F2`, `lg`) and in `~/.xsession-errors`, along
with the backend's.

Run a backend command by hand from the applet folder. With no stdin it uses the default settings:

```bash
cd walldrift@markovic-nikola/files/walldrift@markovic-nikola && python3 -m walldrift -v info
```

## License

GPL-3.0-or-later. Images belong to their creators; walldrift never redistributes them.
