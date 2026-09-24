# walldrift — plan

A random wallpaper changer for Linux Mint (Cinnamon) that pulls **popular wallpapers from online sources**, filtered by topics you choose. It ships as a **Cinnamon applet**: install it from System Settings, add it to the panel, done.

Name: `walldrift`. Applet UUID: `walldrift@markovic-nikola`.

## Goals

- **Zero setup.** Install from System Settings > Applets > Download and add it to the panel. No terminal, no pipx, no timer to install, no config file to write.
- Rotate the wallpaper at random on a timer, at login, on unlock, and on demand.
- Get images from Wallhaven, Unsplash and Pexels, with topics set in the applet's settings.
- Keep a downloaded queue, so changing the wallpaper is instant and still works offline.
- Favorite an image (keep a copy) or ban it (never show it again).
- No dependencies beyond what Mint ships: the Python 3 standard library and PyGObject.

## Sources

| Source | "Popular" endpoint | Topic filter | Auth | Limits | Obligations |
|---|---|---|---|---|---|
| Wallhaven | `/api/v1/search?sorting=toplist&topRange=1M` (also `views`, `favorites`) | `q=<tag>`, `categories`, `atleast=3840x2160`, `ratios` | none (key only for NSFW) | 45 requests/min | none |
| Unsplash | `/topics/{slug}/photos?order_by=popular`, or `/photos?order_by=popular` with no topic | topic slug, or `/search/photos?query=` as a fallback | `Client-ID <access key>` (free) | **50 requests/hour** in demo mode | Call `links.download_location` for each download, and credit the photographer. |
| Pexels | `/v1/curated` with no topic | `/v1/search?query=&orientation=landscape&size=large` | `Authorization: <key>` (free) | 200 requests/hour, 20,000/month | Credit the photographer and Pexels. |

Wallhaven's response format was checked against the live API: search results carry `id`, `url`, `path`, `dimension_x`, `dimension_y`, `purity` and `file_type`, and `meta.last_page`. The Unsplash limit and its `order_by=popular` option come from its documentation. The Pexels limits and endpoints still need to be checked against its documentation.

One list request returns 24 to 80 candidates. The candidate lists are cached, so Unsplash's hourly limit is enough.

## Settings

All settings live in the applet's `settings-schema.json`, and Cinnamon renders them as a native settings window (right-click the applet > Configure). **That schema is the only place defaults are written.** The backend has no defaults table of its own.

| Page | Setting | Widget | Default |
|---|---|---|---|
| General | Change every N minutes | spinbutton | 30 |
| | Change at login / on unlock | switches | on / off |
| | Topics (comma-separated; empty = top images overall) | entry | empty |
| | Minimum resolution | combobox: *auto (largest monitor)*, 1920x1080 … 5120x2880 | auto |
| | Favorites folder | filechooser (folder) | `~/Pictures/Wallpapers` |
| | Cache limit (MB), images downloaded ahead | spinbuttons | 1024, 3 |
| Sources | Per source: enabled, weight, topics override (empty = use General) | switch, spinbutton, entry | Wallhaven on, others off until a key is set |
| | Wallhaven: sorting, top range, categories (general / anime / people) | comboboxes, switches | toplist, 1M, general |
| | Unsplash access key, Pexels API key, Wallhaven API key (optional) | entries | empty |

Keys are flat (`interval-minutes`, `wallhaven-sorting`, …). The backend maps `<source>-<option>` keys to that source's options, so a new source only adds schema entries and a `Source` subclass.

"Auto" minimum resolution is resolved by the backend from each monitor's **native mode** (CinnamonDesktop's RandR bindings), using the largest monitor by area, as landscape. It deliberately ignores the framebuffer size, because fractional scaling inflates it. For example, a 2560×1440 panel rendered at 4096×2304 would otherwise rule out ordinary 4K images.

**No keyboard shortcut settings.** Setting up keybindings is manual work. The panel icon covers everything: left-click opens the menu, middle-click changes the wallpaper.

API keys are stored in Cinnamon's settings file in plain text, as every Spices applet's settings are. They reach the backend on stdin, never in `argv` (which other users can see in `ps`). They can move to libsecret later.

## Architecture

```
Cinnamon ──loads at login──► applet.js  (CJS, runs inside Cinnamon: keep it thin and async)
                               │  AppletSettings, one-minute tick, lock/unlock signal,
                               │  panel menu, middle-click, notifications
                               │
                               │  Gio.Subprocess: /usr/bin/python3 -m walldrift <command>
                               │  stdin: settings as JSON        stdout: result as JSON (first line)
                               ▼
                             backend  (Python, its own process)
                               picker ─► Source.search ─► filter ─► download ─► queue ─► setter (Gio.Settings)
                               (weighted)  (per site)     (size,     (+ Unsplash         (unique file
                                                           seen,       ping)              per image)
                                                           banned)
```

**Backend protocol.** Commands: `next`, `fav`, `ban`, `info`, `refill`. Each reads the settings JSON from stdin, and prints one JSON line as soon as its result is known: `{"image": {...} | null, "queued": n, "conflicts": [{"message", "settings_module"}]}`. The image carries its page URL, author, source, size, favorite flag and `shown_at`. `next` prints that line right after setting the wallpaper, then keeps running to refill the queue, so the menu updates without waiting for downloads. Errors are that one line too, `{"error": "..."}`, and the applet shows them as a notification. Logs go to stderr, which Cinnamon sends to `~/.xsession-errors`. A too-old Python gets the same error line, from a version check that runs before anything else is imported. Run by hand with no stdin, the backend uses the schema's defaults, which is how development and tests drive it.

**Applet responsibilities** (nothing heavy: all network, disk and SQLite work stays in the backend process, so a bug there can never freeze the desktop):
- **Timer:** a one-minute tick that runs `next` once `interval` has passed since the last change. Using wall-clock time means a laptop that slept through its change time gets one promptly after resume. The tick pauses while the screen is locked.
- **Login and unlock:** runs `next` on load, and on the screensaver's `ActiveChanged` D-Bus signal, when those switches are on.
- **Menu:** a credit line for the current image ("Photo by X on Unsplash", or the Wallhaven page), Next, Favorite, Ban and Open page. Open page uses `Gio.AppInfo.launch_default_for_uri`.
- **Middle-click** on the icon changes the wallpaper.
- **Notifications** for errors, without repeating the same one every tick, and once per session for each conflict, with a button that opens the right System Settings page.
- **One backend call at a time**, until its answer arrives. A request made meanwhile runs right after.
- **Retries:** a failed change waits a full interval before the timer tries again.

**Locks.** The backend uses two `flock`s: `show` (pick and set the wallpaper, fast) and `refill` (downloads, taken without waiting). A change is never stuck behind another run's downloads. Two runs fetching the same image each write their own part file, and the database keeps the first record.

## Layout

The repo mirrors the Spices layout, so submitting is a copy of one folder.

```
walldrift@markovic-nikola/            # copied as-is into linuxmint/cinnamon-spices-applets
  info.json                           # {"author": "markovic-nikola"}
  README.md                           # user docs, shown on the Spices site
  screenshot.png
  files/walldrift@markovic-nikola/    # installed to ~/.local/share/cinnamon/applets/
    metadata.json                     # uuid, name, description, version, url, cinnamon-version, max-instances: 1
    applet.js
    settings-schema.json              # every setting and its default
    icon.png
    walldrift/                        # the Python backend
      __main__.py                     # Python version check, then cli.main
      cli.py                          # commands
      protocol.py                     # the one JSON answer line (old-Python safe)
      config.py                       # validates settings; defaults come from settings-schema.json
      setter.py                       # sets the wallpaper, finds conflicts, reads native monitor modes
      errors.py  http.py  models.py  picker.py  queue.py  store.py
      sources/  base.py  wallhaven.py  unsplash.py  pexels.py
tests/                                # backend tests (pytest)
scripts/dev-install.sh                # symlinks the applet into ~/.local/share/cinnamon/applets and reloads it
pyproject.toml                        # dev tooling only: ruff, mypy, pytest config and a dev dependency group
README.md                             # contributor docs; links to the applet README
```

- **Version and homepage** live only in `metadata.json`. The backend reads them from the file next to its package, for the User-Agent. This replaces reading them from installed package metadata, since nothing is pip-installed any more.
- **Files:** the database stays in `~/.local/share/walldrift/` (favorites and bans are durable), downloaded images in `~/.cache/walldrift/images/`.
- **Dev loop:** `scripts/dev-install.sh` symlinks the applet into place and reloads it with `org.Cinnamon.ReloadXlet(uuid, "APPLET")` over D-Bus. Run it again after each change. Logs show up in Looking Glass (`lg`) and `~/.xsession-errors`.

**Source interface.** Each source implements only what differs between sites:

```python
class Source(ABC):
    name: ClassVar[str]                 # its settings are "<name>-*" in settings-schema.json
    def search(self, topic: str | None, page: int) -> SearchPage: ...   # candidates + last_page
    def on_download(self, c: Candidate) -> None: ...   # no-op except Unsplash
```

Retries, rate limiting, resolution filtering, deduplication, bans, caching and credits are written once and shared by every source.

**How one image is picked:**
1. Choose a source by weight.
2. Choose a topic from that source's topics, or none.
3. Use a cached candidate list if it's fresh; otherwise request a random page from the top results.
4. Drop candidates that are too small, already shown or banned.
5. Download one image into the queue.

## Tech stack

| Layer | Choice |
|---|---|
| Delivery | Cinnamon Spices applet, targeting Cinnamon 6.0+ (Mint 22, LMDE 6) |
| Applet | CJS (Cinnamon's GJS), `AppletSettings`, `Gio.Subprocess` |
| Backend | Python ≥ 3.11 on the system `/usr/bin/python3`; standard library + PyGObject only |
| HTTP | `urllib.request` + `json`, sequential; no `requests`, no async |
| Storage | `sqlite3`, WAL mode; an `flock` stops two backend runs from racing |
| Setter | `Gio.Settings`; monitor modes from `CinnamonDesktop.RRScreen`; both imported lazily |
| Config | JSON on stdin, validated by `config.py` |
| Pillow | not used; added as an optional import only if we crop or hash images |
| Dev | `python3 -m venv --system-site-packages .venv`, `pip install --group dev`; `pytest`, `ruff`, `mypy --strict`; `node --check` for `applet.js` syntax |

**Why this shape (2026-09-24):**
- **Python over Rust, Go or an all-JS applet:** best GObject integration, a standard library that covers everything we need, and the same stack as Mint's own tools. An all-JS version would run downloads and storage inside Cinnamon's process.
- **The applet as the product:** pipx + a systemd timer needed a manual `install-timer` step after installing, and left a broken timer behind after `pipx uninstall`. Changing language wouldn't fix that, since nothing runs at install time for any user-level package. Cinnamon already loads applets at login, so the applet owns scheduling. It also gives us the settings window, panel controls and login/unlock hooks for free.
- **A `.deb`** (units in `/usr/lib/systemd/user/`, enabled with `dh_installsystemduser`) stays an option for later, for people who prefer apt.

## Phases

1. **Backend MVP — done** (`0ca9140`): the Wallhaven source, store, queue, picker, Cinnamon setter and CLI, with tests.
2. **The applet** (in progress): the backend in the Spices layout, `settings-schema.json` and the stdin JSON protocol, and `applet.js` (timer, login/unlock, menu, middle-click, notifications), plus `scripts/dev-install.sh`. The systemd timer, TOML config and pipx packaging are removed.
3. **All three sources:** Unsplash and Pexels, with keys in settings, the `download_location` ping and credit lines in the menu.
4. **Publish:** icon, screenshot, user README, translations (`po/`, via `cinnamon-spices-makepot`), then a PR to `linuxmint/cinnamon-spices-applets`.
5. **Later:** libsecret for API keys, local folders as a source, perceptual-hash duplicate detection, a `.deb`.

## Things to handle

- **Spices rules:**
  - Settings go only through Cinnamon's xlet settings: no GSettings schemas of our own, and no editing Cinnamon's JSON files. The backend never touches that file; it gets values on stdin.
  - No compiled code, and no downloading or running code from outside Spices.
  - System dependencies must be installable through apt. We need only `python3` and `python3-gi`, which Mint always ships.
- **Never block Cinnamon:** all file and process I/O in `applet.js` is async, and the backend runs in its own process.
- **Python version:** if `/usr/bin/python3` is older than 3.11, show a clear notification instead of failing silently.
- **Conflicts:** the `cinnamon-dynamic-wallpaper` extension and the built-in slideshow overwrite the wallpaper. Warn once per session, saying what to turn off and where, with a button that opens that settings page. Don't turn them off ourselves.
- **Filenames:** Cinnamon doesn't reload an image saved under the same filename, so every image gets its own file.
- **Unsplash:** its terms require calling `download_location` for each download; not doing it can get the key revoked.
- **Favorites:** never delete them when trimming the cache.

## Decisions

- **Delivery:** a Cinnamon Spices applet (see Tech stack for why).
- **Settings:** `settings-schema.json` holds every setting and default. The applet passes values to the backend on stdin.
- **Controls:** the panel menu and middle-click, with no keyboard shortcut settings (setting them up is manual work). The CLI remains for development and tests.
- **Audience:** built for personal use, but published as open source on the terms below.

## Open source and licensing

- **Our code:** GPL-3.0-or-later, which matches the Mint and Cinnamon ecosystem.
- **No API keys in the repo, ever.** Each user registers their own free Unsplash and Pexels keys and enters them in the applet's settings.
- **No images in the repo or any package.** The applet downloads images only to the user's own cache, for personal use as a desktop background. It never re-hosts or redistributes them.
- **Unsplash:** call `download_location` for each download, credit the photographer ("Photo by X on Unsplash", with links), don't suggest Unsplash endorses the app, and keep "Unsplash" out of the app name.
- **Pexels:** credit the photographer and Pexels, with a link back.
- **Wallhaven:** images belong to their uploaders or artists; keep links back to the source page. Respect the 45 requests/minute limit.
- **Every request:** send an honest User-Agent (`walldrift/<version> (+repo URL)`) and back off on HTTP 429 responses.
- **Name:** `walldrift`. It avoids the `mint*` prefix Mint uses for its own tools (mintupdate, mintinstall), so it won't look like an official Mint tool.
- **SFW only by default.** Wallhaven NSFW content stays out of scope unless a user adds their own key and opts in.
