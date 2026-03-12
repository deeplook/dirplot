# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Multiple local roots**: `dirplot map bar baz` accepts two or more local directory
  paths. dirplot finds their common parent, scans each path independently, and assembles
  a synthetic wrapper tree that contains only the requested subtrees — siblings are
  excluded entirely.
- **`--subtree` / `-s`** option (repeatable) — an allowlist complement to `--exclude`:
  after scanning the root, keep only the named direct children. Supports nested paths
  such as `--subtree src/dirplot/fonts`, which produces a synthetic `src → dirplot`
  chain containing only the `fonts` subtree. Useful when it is easier to name what you
  want than to enumerate what you don't.

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
