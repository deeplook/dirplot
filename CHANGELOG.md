# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

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
