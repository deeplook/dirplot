# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`dirplot hg` command** — replay Mercurial changeset history as an animated
  treemap, identical in interface to `dirplot git`. Supports `--animate`,
  `--max-commits`, `--last`, `--total-duration`, `--frame-duration`, `--fade-out`,
  `--dark`/`--light`, `--workers`, `--crf`, `--codec`, and all other animation flags.
  The `@rev` suffix on the repo path passes a revset directly to `hg log`.
  Requires `hg` on `PATH`. Only local repositories are supported — there is no
  `hg://` URI scheme because there is no Mercurial equivalent of GitHub.
  ```bash
  dirplot hg /path/to/repo --output history.png --animate
  dirplot hg /path/to/repo@tip --output history.png
  dirplot hg /path/to/repo --animate --last 30d --output history.mp4
  ```

## [0.4.1] - 2026-04-03

### Added

- **`--last PERIOD`** for `dirplot git` — filter commits by a relative time period instead
  of (or in addition to) `--max-commits`. Accepts a number followed by a unit:
  `m` (minutes), `h` (hours), `d` (days), `w` (weeks), `mo` (months = 30 days).
  For GitHub URLs, uses `git clone --shallow-since` for an efficient date-bounded shallow
  clone. `--last` and `--max-commits` may be combined (date filter + count cap both apply).
  ```bash
  dirplot git . -o history.mp4 --animate --last 30d
  dirplot git . -o history.mp4 --animate --last 24h
  dirplot git github://owner/repo -o history.mp4 --animate --last 2w --max-commits 10
  ```

- **`dirplot demo` command** — new subcommand that runs a curated set of example commands
  and saves outputs to a folder. Useful for first-time walkthroughs or verifying that
  everything works in a given environment. Accepts `--output` (default: `demo/`),
  `--github-url` (default: `https://github.com/deeplook/dirplot`), and
  `--interactive` / `-i` to step through and confirm each command individually. Output
  uses rich formatting with colour, section rules, and status indicators.
  ```bash
  dirplot demo                             # run all examples, save to ./demo/
  dirplot demo --output ~/dp-demo --interactive
  ```

- **`--fade-out` for animated output** — appends a fade-out sequence at the end of
  animations produced by `dirplot git --animate`, `dirplot watch --animate`, and
  `dirplot replay`. Four flags control the effect:
  - `--fade-out` / `--no-fade-out` — enable/disable (default: off)
  - `--fade-out-duration SECS` — total fade length in seconds (default: 1.0)
  - `--fade-out-frames N` — number of blend steps; defaults to 4 per second of duration
    so longer fades are automatically finer-grained
  - `--fade-out-color COLOR` — target colour: `auto` (black in dark mode, white in light
    mode), `transparent` (PNG/APNG only; fades to fully transparent), any CSS colour
    name, or hex code (e.g. `"#1a1a2e"`)
  ```bash
  dirplot git . -o history.png --animate --fade-out
  dirplot git . -o history.mp4 --animate --fade-out --fade-out-duration 2.0
  dirplot git . -o history.png --animate --fade-out --fade-out-color transparent
  ```

- **`--dark` / `--light` mode** for all treemap commands — controls background and border
  colours. Dark mode (default) uses a near-black canvas with white directory labels; light
  mode uses a white canvas with black labels. Available on `map`, `git`, `watch`, and
  `replay`.
  ```bash
  dirplot map . --light
  dirplot git . -o history.mp4 --animate --light
  ```

- **Metadata in MP4/MOV output** — `dirplot git`, `dirplot watch`, and `dirplot replay`
  now embed the same dirplot metadata (date, software version, OS, Python version,
  executed command) into MP4/MOV files that was previously only written to PNG and SVG.
  `dirplot read-meta` reads it back via `ffprobe`.

- **Automatic `gh` CLI credential fallback** — if `--github-token` and `GITHUB_TOKEN`
  are both absent, dirplot silently runs `gh auth token`. Users authenticated with the
  [GitHub CLI](https://cli.github.com/) (`gh auth login`) can access private repositories
  with no extra configuration. Token resolution order: `--github-token` →
  `$GITHUB_TOKEN` → `gh auth token`.

### Changed

- `--fade-out-frames` defaults dynamically to `round(fade_out_duration × 4)` rather than
  a fixed 4, so a 2-second fade automatically uses 8 frames and a 0.5-second fade uses 2.

### Fixed

- **`--total-duration` overshooting the target length** — when many commits fell within
  a burst (closely-spaced timestamps), their proportional frame durations would each be
  raised to the 200 ms floor, inflating the total well beyond the requested duration
  (e.g. 34 s instead of 30 s). The floor is still applied for readability, but the
  non-floored frames are now scaled down to compensate so the sum always matches
  `--total-duration` exactly.

### Docs

- Added `## dirplot read-meta` section to `docs/CLI.md` (previously undocumented).
- Documented external tool requirements: `git` (required by `dirplot git`), `ffmpeg`
  (required for MP4 output), `ffprobe` (required by `read-meta` on MP4 files) — in both
  `README.md` and `docs/CLI.md`.

## [0.4.0] - 2026-03-28

### Added

- **MP4 video output** — all three animation commands (`watch --animate`, `git --animate`,
  `replay`) now write MP4 video when the output path ends in `.mp4` or `.mov`. Quality is
  controlled via `--crf` (Constant Rate Factor: 0 = lossless, 51 = worst, default 23) and
  `--codec` (`libx264` H.264 or `libx265` H.265). MP4 files are typically 10–100× smaller
  than equivalent APNGs. Requires `ffmpeg` on PATH.
  ```bash
  dirplot git . -o history.mp4 --animate
  dirplot git . -o history.mp4 --animate --crf 18 --codec libx265
  dirplot replay events.jsonl -o replay.mp4 --total-duration 30
  dirplot watch . -o treemap.mp4 --animate
  ```
- **`@ref` suffix for `dirplot git`**: local repository paths now accept an optional
  `@ref` suffix to target a specific branch, tag, or commit SHA without needing
  `--range` (e.g. `dirplot git .@my-branch -o out.apng --animate`). `--range` takes
  precedence when both are provided.
- **`dirplot git` subcommand** — replays a git repository's commit history as an
  animated treemap. Each commit becomes one frame; changed tiles receive the same
  colour-coded highlight borders as `watch --animate` (green = created, blue = modified,
  red = deleted). The commit SHA and local timestamp are shown in the root tile header,
  and a progress bar at the top of each frame advances as the animation plays.
  ```bash
  # Animate all commits, write APNG
  dirplot git . --output history.apng --animate --exclude .git

  # Last 50 commits on main, 30-second animation with time-proportional frame durations
  dirplot git . --output history.apng --animate \
    --range main~50..main --total-duration 30

  # Live-updating static PNG (last frame wins; useful with an auto-refreshing viewer)
  dirplot git /path/to/repo --output treemap.png --max-commits 100
  ```
- **`--range`** (`-r`): git revision range passed directly to `git log`
  (e.g. `main~50..main`, `v1.0..HEAD`). Defaults to the full history of the current branch.
- **`--max-commits`** (`-n`): cap the number of commits processed.
- **`--frame-duration`**: fixed frame display time in ms when `--total-duration` is not set
  (default: 1000 ms).
- **`--total-duration`**: target total animation length in seconds. Frame durations are
  scaled proportionally to the real elapsed time between commits, so quiet periods in
  development history map to longer pauses and burst activity to rapid flips. A 200 ms
  floor prevents very fast commits from being invisible; durations are capped at 65 535 ms
  (APNG uint16 limit). A summary line reports the actual range:
  `Proportional timing: 200–7553 ms/frame (total ~30.1s)`.
- **`--workers`** (`-w`): number of parallel render workers in animate mode (default: all
  CPU cores). Rendering is memory-bandwidth bound, so 4–8 workers is typically optimal;
  use this flag to tune for your hardware.
- **Time-proportional progress bar**: a 2 px bar at the top of each frame advances in
  proportion to animation time consumed, not frame count — so a burst of closely-spaced
  commits produces only a small movement while a long quiet period advances it visibly.
  With fixed `--frame-duration` the bar is linear as before.

- **Debounced watch** (`--debounce SECONDS`, default `0.5`): the `watch` subcommand now
  collects rapid file-system event bursts and regenerates the treemap once per quiet
  period instead of on every raw event. A `git checkout` touching 100 files triggers
  exactly one render after the activity settles. Pass `--debounce 0` to restore the
  old immediate-fire behaviour.
  ```bash
  dirplot watch . --output treemap.png                      # 500 ms debounce (default)
  dirplot watch . --output treemap.png --debounce 1.0       # 1 s quiet window
  dirplot watch . --output treemap.png --debounce 0         # immediate, as before
  ```
- **Event log** (`--event-log FILE`): on Ctrl-C exit, all raw file-system events
  recorded during the session are written as newline-delimited JSON (JSONL) to the
  given file. Each line has `timestamp`, `type`, `path`, and `dest_path` fields.
  The log is written only if there are events to record.
  ```bash
  dirplot watch src --output treemap.png --event-log events.jsonl
  # Ctrl-C, then:
  cat events.jsonl | python3 -m json.tool
  ```
- **File-change highlights** (`--animate`): each APNG frame now draws colour-coded
  borders around tiles that changed since the previous frame — green for created,
  blue for modified, red for deleted, orange for moved. Deleted files are highlighted
  retroactively on the *previous* frame (since the tile no longer exists in the current
  one), so the animation clearly shows both the disappearance and the appearance of files.
  Moved files appear as a deletion at the old path and a creation at the new path.
- **Graceful finalization**: Ctrl-C now flushes any pending debounced render before
  stopping the observer, so the output file always reflects the final state of the
  watched tree. A second Ctrl-C during APNG writing is ignored so the file can finish
  being written.
- **Tree comment stripping**: trailing `# comments` in `tree` output are now ignored
  by the path-list parser, so annotated tree listings (e.g. `├── config.json  # app config`)
  are parsed correctly. Filenames containing `#` without a leading space are preserved.
- **`scripts/apng_frames.py`**: utility script to list frame durations, dimensions, and
  offsets in an APNG file.
- **`scripts/watch_events.py`**: utility script to watch directories and log filesystem
  events to a CSV file (or stdout) in real time using watchdog.
- **`--depth` for `watch`**: the `watch` subcommand now accepts `--depth N` to limit
  recursion depth, matching the behaviour of `dirplot map`.
  ```bash
  dirplot watch . --output treemap.png --depth 3
  ```
- **`dirplot replay` subcommand** — replays a JSONL filesystem event log (as produced
  by `dirplot watch --event-log`) as an animated treemap APNG. Events are grouped into
  time buckets (one frame per bucket, default 60 s), with colour-coded highlight borders
  matching `watch --animate`. Only files referenced in the event log appear in the
  treemap; the common ancestor of all paths is used as the tree root. Frame durations
  can be uniform (`--frame-duration`, default 500 ms) or proportional to the real time
  gaps between buckets (`--total-duration`). Frames are rendered in parallel.
  ```bash
  # Replay an event log with 60-second buckets, 30-second total animation
  dirplot replay events.jsonl --output replay.apng --total-duration 30

  # Smaller buckets for fine-grained activity, fixed frame duration
  dirplot replay events.jsonl --output replay.apng --bucket 10 --frame-duration 200
  ```

- **`dirplot git` accepts GitHub URLs** — pass a `github://owner/repo[@branch]` or
  `https://github.com/owner/repo` URL directly to `dirplot git`. dirplot clones the
  repository into a temporary directory (shallow when `--max-commits` is set, full
  otherwise), runs the full history pipeline locally, and removes the clone on exit.
  No permanent local copy is created.
  ```bash
  # Animate the last 50 commits of a GitHub repo — no local clone needed
  dirplot git github://owner/repo --output history.png --animate --max-commits 50

  # Specific branch
  dirplot git github://owner/repo@main --output history.png --animate --max-commits 50
  ```
- **Total commit count shown** — `dirplot git` now reports the total number of commits
  available alongside the number being animated, so you can gauge how much history
  exists before committing to a longer run:
  ```
  Replaying 20 of 147 commit(s) (increase --max-commits to process more) ...
  ```
  For GitHub URLs the count is fetched with a single cheap API request (one commit
  object + `Link` header). For local repos `git rev-list --count HEAD` is used.
- **`--github-token`** (`$GITHUB_TOKEN`): added to `dirplot git` for private GitHub
  repos or to raise the API rate limit when fetching the total commit count.

### Changed

- **`libarchive-c` is now an optional dependency.** Install it with
  `pip install 'dirplot[libarchive]'` (plus the system library:
  `brew install libarchive` / `apt install libarchive-dev`) to enable
  `.iso`, `.cpio`, `.rpm`, `.cab`, `.lha`, `.xar`, `.pkg`, `.dmg`, `.a`, `.ar`,
  and `.tar.zst` / `.tzst` support. The base install works without it; a clear
  error is shown if you try to open one of these formats without the extra.

- **`--animate` writes the APNG once on exit** instead of reading and rewriting the
  entire file on every render. Frames are accumulated as raw PNG bytes in memory and
  flushed as a single multi-frame APNG when the watcher stops (Ctrl-C). This removes
  an O(N²) disk-I/O pattern where frame K required reading a K-frame APNG just to
  append one more frame. Status output during a session now reads `Captured frame N`;
  the final `Wrote N-frame APNG → …` line confirms the file was written on exit.

### Fixed

- **Initial scan progress**: the `watch` subcommand now prints `Scanning <roots> …`
  before the first render and starts the filesystem observer only after the initial
  treemap has been generated, avoiding spurious events during the first scan.
- **`--animate` race condition**: the debounce timer thread was marked as daemon,
  causing an in-progress render to be killed when the main thread exited after
  `observer.join()`. The timer is no longer a daemon thread; `flush()` joins any
  in-flight render before stopping.
- **`--animate` Pillow APNG regression**: passing `pnginfo` alongside `save_all=True`
  caused Pillow to silently write a static PNG instead of an APNG. The `pnginfo`
  argument is now omitted from multi-frame saves (cross-process timing metadata is
  no longer needed since frames are held in memory for the lifetime of the process).
- **APNG frame duration overflow**: restoring the inter-session frame duration from
  stored metadata could produce a value exceeding 65 535 ms — the maximum expressible
  by APNG's uint16 `delay_num` field when `delay_den = 1000` — causing Pillow to raise
  `cannot write duration`. Durations are now capped at 65 535 ms (≈ 65 s).

- **Path-list input from `tree` / `find`** (`--paths-from FILE` or stdin pipe): the `map`
  subcommand now accepts a list of paths produced by `tree` or `find` — either piped via
  stdin or read from a file with `--paths-from`. Format is auto-detected: `tree` output
  (detected by `├──` / `└──` box-drawing characters) or `find` output (one path per line).
  Handles `tree -s` / `tree -h` (size columns), `tree -f` (full embedded paths), and the
  default indented name format. Ancestor/descendant duplicates are collapsed automatically
  so only the minimal set of roots is passed to the scanner.
  ```bash
  # Implicit stdin — no flag needed
  tree src/        | dirplot map
  tree -s src/     | dirplot map        # with file sizes in tree output
  find . -name "*.py" | dirplot map

  # Explicit file
  tree src/ > paths.txt && dirplot map --paths-from paths.txt

  # Explicit stdin
  tree src/ | dirplot map --paths-from -
  ```
  Positional path arguments and path-list input are mutually exclusive — combining them
  exits with a clear error. Only local paths are supported (remote backends such as
  `docker://`, `s3://`, `ssh://` remain positional-arg only).

- **`dirplot watch` accepts multiple directories**: the `watch` subcommand now takes
  one or more positional path arguments and schedules a filesystem observer for each,
  regenerating the treemap from all roots on every change.
  ```bash
  dirplot watch src tests --output treemap.png
  ```
- **`dirplot map` accepts multiple file paths as roots**: previously, multi-root mode
  required every argument to be a directory. Individual files can now be passed as roots;
  each is treated as a leaf node and displayed under the common parent directory.
  ```bash
  dirplot map src/main.py src/util.py --no-show
  ```
- **stdout output** (`--output -`): passing `-` as the output path writes the PNG or SVG
  bytes to stdout, enabling piping to other tools. Header and progress lines are
  automatically redirected to stderr to keep the binary stream clean.
  ```bash
  dirplot map . --output - --no-show | convert - -resize 50% small.png
  dirplot map . --output - --format svg --no-show > treemap.svg
  ```

## [0.3.3] - 2026-03-14

### Added

- **Breadcrumbs mode** (`--breadcrumbs/--no-breadcrumbs`, `-b/-B`, on by default): directories
  that form a single-child chain (one subdirectory, no files) are collapsed into a single tile
  whose header shows the full path separated by ` / ` (e.g. `src / dirplot / fonts`). When the
  label is too wide, middle segments are replaced with `…` (`src / … / fonts`). The root tile
  is never collapsed. Disable with `-B` or `--no-breadcrumbs`.
- **Tree depth in root label**: the root tile header now includes `depth: N` alongside the
  file, directory, and size summary (e.g. `myproject — 124 files, 18 dirs, 4.0 MB (…), depth: 6`).
  The depth reflects the original tree structure and is invariant to whether breadcrumbs mode
  is active.

## [0.3.2] - 2026-03-13

### Added

- **`dirplot watch`** subcommand — watches a directory and regenerates the treemap
  on every file-system change using watchdog (FSEvents on macOS, inotify on Linux,
  kqueue on BSD). Requires `watchdog`, now a core dependency.
  ```bash
  dirplot watch . --output treemap.png
  dirplot watch . --output treemap.png --animate   # APNG, one frame per change
  ```
- **Vertical file labels**: file tiles that are at least twice as tall as wide now
  display their label rotated 90° CCW, letting the text span the full tile height
  instead of being squeezed into the narrow width.
- **Scan and render timing** shown in header output:
  `Found 1,414 files … [2.3s]` and `Saved dirplot to out.png  [0.4s]`.
- **Multiple local roots**: `dirplot map src tests` accepts two or more local
  directory paths, finds their common parent, and shows only those subtrees.
- **`--subtree` / `-s`** option (repeatable) — allowlist complement to `--exclude`:
  keep only the named direct children of the root after scanning. Supports nested
  paths such as `--subtree src/dirplot/fonts`.

### Fixed

- `--exclude` on pod and Docker backends now prunes entire subtrees — previously only
  the exact path was matched, so all children leaked through.
- Clearer error for distroless pods: exit code 126 from `kubectl exec` now surfaces as
  an actionable message explaining that the container has no shell or `find` utility.
- Adaptive file-label font size is now computed with a single `textbbox` measurement
  (one call per tile) instead of stepping down one pixel at a time — eliminates an
  O(font_size × n_tiles) bottleneck that caused near-blocking on large trees such as
  `.venv` directories.

### Changed

- `-s` short alias reassigned from `--font-size` to `--subtree`. `--font-size` still
  works as before; it just no longer has a single-letter alias.

## [0.3.1] - 2026-03-11

### Added

- `github://` URI now accepts an optional subpath after the repository name, letting
  you scan a subdirectory directly:
  - `github://owner/repo/sub/path` — subpath on the default branch
  - `github://owner/repo@ref/sub/path` — subpath on a specific branch, tag, or commit SHA
  - `https://github.com/owner/repo/tree/branch/sub/path` — full GitHub URL form
  - Tags and commit SHAs are supported wherever a branch ref was previously accepted
    (e.g. `github://torvalds/linux@v6.12`), as the GitHub trees API accepts any git ref.
- `--legend N` replaces the old boolean `--legend/--no-legend` flag. It now shows a
  **file-count legend** — a sorted list of the top N extensions by number of files,
  with a coloured swatch and the file count for each entry:
  - Pass `--legend` alone to use the default of 20 entries.
  - Pass `--legend 10` for a custom limit.
  - Omit the flag entirely to show no legend.
  - The number of rows is also capped automatically so the box never overflows the
    image, based on available vertical space and the current `--font-size`.
  - Extensions with the same count are sorted alphabetically as a tiebreaker.
  - When the total number of extensions exceeds the limit, a `(+N more)` line is
    appended at the bottom of the box.

- The root tile header now includes a summary of the scanned tree after an em-dash
  separator: `myproject — 124 files, 18 dirs, 4.0 MB (4,231,680 bytes)`.
  Applies to both PNG and SVG output. The label is truncated with `…` when the tile
  is too narrow to fit the full string.

- Greatly expanded archive format support via the new `libarchive-c` core dependency
  (wraps the system libarchive C library):
  - **New formats**: `.iso`, `.cpio`, `.xar`, `.pkg`, `.dmg`, `.img`, `.rpm`, `.cab`,
    `.lha`, `.lzh`, `.a`, `.ar`, `.tar.zst`, `.tzst`
  - **New ZIP aliases**: `.nupkg` (NuGet), `.vsix` (VS Code extension), `.ipa` (iOS app),
    `.aab` (Android App Bundle)
  - `.tar.zst` / `.tzst` routed through libarchive for consistent behaviour across all
    supported Python versions (stdlib `tarfile` only gained zstd support in 3.12).
  - `libarchive-c>=5.0` added as a core dependency alongside `py7zr` and `rarfile`.
    Requires the system libarchive library:
    `brew install libarchive` / `apt install libarchive-dev`.
  - See [ARCHIVES.md](docs/ARCHIVES.md) for the full format table, platform notes, and
    intentionally unsupported formats (`.deb`, UDIF `.dmg`).
- Encrypted archive handling:
  - `--password` CLI option passes a passphrase upfront.
  - If an archive turns out to be encrypted and no password was given, dirplot prompts
    interactively (`Password:` hidden-input prompt) and retries — no need to re-run with a flag.
  - A wrong password exits cleanly with `Error: incorrect password.`
  - `PasswordRequired` exception exported from `dirplot.archives` for programmatic use.
  - **Encryption behaviour by format** (since dirplot reads metadata only, never extracts):
    - ZIP and 7z: central directory / file list is unencrypted by default → readable without
      a password even for encrypted archives.
    - RAR with header encryption (`-hp`): listing is hidden without password;
      wrong password raises `PasswordRequired`.

### Fixed

- `--version` moved back to the top-level `dirplot` command (was accidentally scoped
  to `dirplot map` after the CLI was restructured into subcommands).

## [0.3.0] - 2026-03-10

### Added

- Kubernetes pod scanning via `pod://pod-name/path` syntax — uses `kubectl exec` and
  `find` to build the tree without copying files out of the pod. Works on any running
  pod that has a POSIX shell and `find` (GNU or BusyBox). No extra dependency; only
  `kubectl` is required.
  - Namespace can be specified inline (`pod://pod-name@namespace:/path`) or via
    `--k8s-namespace`.
  - Container can be selected for multi-container pods via `--k8s-container`.
  - `-xdev` is intentionally omitted so mounted volumes (emptyDir, PVC, etc.) within
    the scanned path are traversed — the common case in k8s where images declare
    `VOLUME` entries that are always mounted on a separate filesystem.
  - Automatically falls back to a portable `sh` + `stat` loop on BusyBox/Alpine pods.
- Docker container scanning via `docker://container:/path` syntax — uses `docker exec`
  and `find` to build the tree without copying files out of the container. Works on any
  running container that has a POSIX shell and `find` (GNU or BusyBox). No extra
  dependency; only the `docker` CLI is required.
  - Automatically detects BusyBox `find` (Alpine-based images) and falls back to a
    portable `sh` + `stat` loop when GNU `-printf` is unavailable.
  - Virtual filesystems (`/proc`, `/sys`, `/dev`) are skipped via `-xdev`.
  - Supports `--exclude`, `--depth`, `--log`, and all other standard options.
  - `Dockerfile` and `.dockerignore` added so the project itself can be used as a
    scan target.
- SVG output format via `--format svg` or by saving to a `.svg`-suffixed path with `--output`.
  The output is a fully self-contained, interactive SVG file:
  - **CSS hover highlight** — file tiles brighten and gain a soft glow; directory headers
    brighten on mouse-over (`.tile` / `.dir-tile` classes, no JavaScript needed).
  - **Floating tooltip panel** — a JavaScript-driven semi-transparent panel tracks the cursor
    and shows the file or directory name, human-readable size, and file-type / item count.
    No external scripts or stylesheets — the panel logic is embedded in the SVG itself.
  - **Van Wijk cushion shading** — approximated via a single diagonal `linearGradient`
    overlay (`gradientUnits="objectBoundingBox"`), defined once and shared across all tiles.
    Matches the ×1.20 highlight / ×0.80 shadow range of the PNG renderer.
    Disabled with `--no-cushion`.
- `--format png|svg` CLI option; format is also auto-detected from the `--output` file
   extension.
- `create_treemap_svg()` added to the public Python API (`from dirplot import create_treemap_svg`).
- `drawsvg>=2.4` added as a core dependency.
- Rename the treemap command to `map` (dirplot map <root>).
- Add `termsize` subcommand and restructure CLI as multi-command app.
- Add `--depht` parameter to limit the scanning of large file trees.
- Support for SSH remote directory scanning (`pip install dirplot[ssh]`).
- Support for AWS S3 buckets in the cloud (`pip install dirplot[s3]`).
- Support for local archive files, .zip, tgz, .tar.xz, .rar, .7z, etc.
- Include example archives for 17 different extentions for testing.
- Comprehensive documentation.
- `github://owner/repo[@branch]` URI scheme for GitHub repository scanning. The old
  `github:owner/repo` shorthand has been removed.
- File tiles now have a 1-px dark outline (60/255 below fill colour per channel) so
  adjacent same-coloured tiles — e.g. a directory full of extension-less files — are
  always visually distinct rather than blending into a single flat block.

### Changed

- `docs/REMOTE-ACCESS.md` renamed to `docs/EXAMPLES.md`; Docker and Kubernetes pod
  sections added; images with captions added for all remote backends.

### Fixed

- SVG tooltips now show the original byte count when `--log` is active, not the
  log-transformed layout value. `Node.original_size` is populated by `apply_log_sizes`
  for both file and directory nodes and is used by the SVG renderer for `data-size`.
- GitHub error messages are now clear and actionable.

## [0.2.0] - 2026-03-09

### Added

- Support for Windows, incl. full test suite

### Fixed

- Improved README, Makefile

## [0.1.2] - 2026-03-06

### Fixed

- Partly incorrect `uvx install dirplot` command
- Wrong version number in `uv.lock`

## [0.1.1] - 2026-03-06

### Fixed

- Typing complaints
- Improved README with better install/run commands

## [0.1.0] - 2026-03-06

### Added

- Nested squarified treemap rendered as a PNG at the exact pixel dimensions of the terminal window.
- Inline terminal display via iTerm2 and Kitty graphics protocols, auto-detected at runtime; supports iTerm2, WezTerm, Warp, Hyper, Kitty, and Ghostty.
- System-viewer fallback (`open` / `xdg-open`) as the default display mode.
- File-extension colours from the GitHub Linguist palette (~500 known extensions); unknown extensions fall back to a stable MD5-derived colour from the chosen colormap.
- Van Wijk quadratic cushion shading giving each tile a raised 3-D look (`--cushion`, on by default).
- Bundled JetBrains Mono fonts for crisp directory labels at any size.
- CLI options: `--output`, `--show/--no-show`, `--inline`, `--legend`, `--font-size`, `--colormap`, `--exclude`, `--size`, `--header/--no-header`, `--cushion/--no-cushion`, `--log`.
- Full test suite (65 tests), strict mypy, ruff linting, pre-commit hooks, and CI on Python 3.10–3.13.
