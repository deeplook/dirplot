# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- SVG tooltips now show the original byte count when `--log` is active, not the
  log-transformed layout value. `Node.original_size` is populated by `apply_log_sizes`
  for both file and directory nodes and is used by the SVG renderer for `data-size`.

### Added

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
- `--format png|svg` CLI option; format is also auto-detected from the `--output` file extension.
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
