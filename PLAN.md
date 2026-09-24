# walldrift — plan

A random wallpaper changer for Linux Mint (Cinnamon) that pulls **popular wallpapers from online sources**, filtered by topics you configure.

Name: `walldrift` (free on PyPI; not an apt package name).

## Goals

- Rotate the wallpaper at random on a timer, and on demand.
- Get images from Wallhaven, Unsplash and Pexels, with topics set in a config file.
- Keep a downloaded queue, so changing the wallpaper is instant and still works offline.
- Favorite an image (keep a copy) or ban it (never show it again).
- No pip dependencies: only the Python 3 standard library and PyGObject, which Mint ships.

## Sources

| Source | "Popular" endpoint | Topic filter | Auth | Limits | Obligations |
|---|---|---|---|---|---|
| Wallhaven | `/api/v1/search?sorting=toplist&topRange=1M` (also `views`, `favorites`) | `q=<tag>`, `categories`, `atleast=3840x2160`, `ratios` | none (key only for NSFW) | 45 requests/min | none |
| Unsplash | `/topics/{slug}/photos?order_by=popular`, or `/photos?order_by=popular` with no topic | topic slug, or `/search/photos?query=` as a fallback | `Client-ID <access key>` (free) | **50 requests/hour** in demo mode | Call `links.download_location` for each download, and credit the photographer. |
| Pexels | `/v1/curated` with no topic | `/v1/search?query=&orientation=landscape&size=large` | `Authorization: <key>` (free) | 200 requests/hour, 20,000/month | Credit the photographer and Pexels. |

Wallhaven's response format was checked against the live API: it returns `id`, `url`, `path`, `resolution`, `ratio`, `file_size`, `file_type`, `favorites` and `purity`. The Unsplash limit and its `order_by=popular` option come from its documentation. The Pexels limits and endpoints still need to be checked against its documentation.

One list request returns 24 to 80 candidates. The candidate lists are cached, so Unsplash's hourly limit is enough.

## Configuration

`~/.config/walldrift/config.toml`, read with the standard-library `tomllib`:

```toml
interval = "30m"
min_resolution = "3840x2160"   # skip anything smaller than the largest monitor
cache_limit_mb = 1024
favorites_dir = "~/Pictures/Wallpapers"

# Global topics. An empty list means "top images overall".
# Each source turns a topic into its own filter (tag, topic slug or search query).
topics = ["nature", "space", "minimal"]

[sources.wallhaven]
enabled = true
weight = 2                 # relative chance this source is picked
sorting = "toplist"        # toplist | views | favorites
top_range = "1M"           # 1d 3d 1w 1M 3M 6M 1y
categories = ["general"]   # general | anime | people
# topics = ["cyberpunk"]   # optional per-source override of the global topics

[sources.unsplash]
enabled = true
weight = 1

[sources.pexels]
enabled = true
weight = 1
```

API keys go in a separate file, `~/.config/walldrift/secrets.toml` with permissions 0600, so the main config can be shared or added to dotfiles. They can move to libsecret later.

## Architecture

```
config ──► source picker ──► Source.search(topic) ──► candidate filter ──► downloader ──► queue (cache)
           (weighted)        (plugin per site)         (resolution,         (+ Unsplash      │
                                                        seen, banned)        download ping)  ▼
                                                                          setter (gsettings) ◄── CLI / timer
```

```
walldrift/
  __main__.py      # CLI: next | fav | ban | info | open | refill | install-timer
  config.py        # loads config + secrets, fills in defaults, XDG paths
  errors.py        # WalldriftError and subclasses, shown to the user as one line
  http.py          # one shared HTTP client: user agent, timeouts, retry and backoff, per-host throttling
  models.py        # Candidate(source, id, page_url, image_url, width, height, author, author_url)
  sources/
    base.py        # Source base class + option validation
    wallhaven.py
    unsplash.py
    pexels.py
  store.py         # SQLite index: images, shown_at, favorite, banned, cached candidate lists
  picker.py        # steps 1-4 below: source by weight, topic, random top page, filtering
  queue.py         # keeps N images downloaded ahead; evicts least-recently-shown images above the cache limit
  setter.py        # Cinnamon backend: gsettings picture-uri (unique filename per image), conflict checks
  systemd.py       # writes the user timer from `interval` (walldrift install-timer)
tests/
```

Files: the database lives in `~/.local/share/walldrift/` (favorites and bans are durable), downloaded images in `~/.cache/walldrift/images/`.

**Source interface.** Each source implements only what differs between sites:

```python
class Source(ABC):
    name: ClassVar[str]
    OPTIONS: ClassVar[dict[str, Any]]   # source-specific config keys and defaults
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

Decided 2026-09-24, after weighing Rust, Go and an all-CJS applet. Python won on desktop integration (GObject), the standard library covering everything we need, and Mint's own tools using the same stack.

| Layer | Choice |
|---|---|
| Language | Python ≥ 3.11 (`tomllib`), so Mint 22+ only |
| HTTP | `urllib.request` + `json`, sequential; no `requests`, no async |
| Storage | `sqlite3`, WAL mode; an `flock` stops the timer and a shortcut from racing |
| Setter | `Gio.Settings` via the system's PyGObject, imported lazily |
| Scheduling | systemd user timer + oneshot service, generated from `interval`; an optional long-running `watch` mode (D-Bus unlock signal) comes in phase 3 |
| CLI | `argparse` |
| Applet (phase 3) | CJS, calling the CLI |
| Pillow | not in the MVP; added as an optional import if we crop or hash images |
| Install | `pipx install --system-site-packages` (a venv can't see `python3-gi` otherwise); `.deb` or Cinnamon Spices later |
| Dev | `python3 -m venv --system-site-packages .venv`; `pytest`, `ruff`, `mypy --strict`; build with `hatchling` |

## Phases

1. **MVP:** config, the Wallhaven source, the store, the queue, the Cinnamon setter, the CLI, and the systemd timer.
2. **All three sources:** Unsplash and Pexels, per-source topics, and a credit line in `walldrift info`.
3. **Desktop integration:** a Cinnamon panel applet (Next, Favorite, Ban, open the source page, credits), and a change at login or unlock.
4. **Later:** a settings window for editing topics and sources, local folders as a source, and perceptual-hash duplicate detection.

## Things to handle

- Turn off the `cinnamon-dynamic-wallpaper` extension and the built-in slideshow, or they will overwrite the wallpaper.
- Cinnamon doesn't reload an image saved under the same filename, so every change needs a new file path.
- Unsplash's terms require calling `download_location` for each download; not doing it can get the key revoked.
- Never delete favorites when trimming the cache.

## Decisions

- **Topics** are set in the config file (see Configuration). A settings window can edit them in phase 4.
- **Controls:** the CLI plus a systemd timer come first. The applet (phase 3) is a thin JavaScript layer that calls the CLI. Until then, Cinnamon keyboard shortcuts can run `next`, `fav` and `ban`.
- **Audience:** built for personal use, but published as open source on the terms below.

## Open source and licensing

- **Our code:** GPL-3.0-or-later, which matches the Mint and Cinnamon ecosystem, where the applet will run.
- **No API keys in the repo, ever.** Each user registers their own free Unsplash and Pexels keys and puts them in `secrets.toml`. Add `secrets.toml` to `.gitignore`.
- **No images in the repo or any package.** The tool downloads images only to the user's own cache, for personal use as a desktop background. It never re-hosts or redistributes them.
- **Unsplash:** call `download_location` for each download, credit the photographer ("Photo by X on Unsplash", with links), don't suggest Unsplash endorses the app, and keep "Unsplash" out of the app name.
- **Pexels:** credit the photographer and Pexels, with a link back.
- **Wallhaven:** images belong to their uploaders or artists; keep links back to the source page. Respect the 45 requests/minute limit.
- **Every request:** send an honest User-Agent (`<app>/<version> (+repo URL)`) and back off on HTTP 429 responses.
- **Name:** `walldrift`. It avoids the `mint*` prefix Mint uses for its own tools (mintupdate, mintinstall), so it won't look like an official Mint tool.
- **SFW only by default.** Wallhaven NSFW content stays out of scope unless a user adds their own key and opts in.
