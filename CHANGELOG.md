# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
