# dirplot

[![CI](https://github.com/deeplook/dirplot/actions/workflows/ci.yml/badge.svg)](https://github.com/deeplook/dirplot/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Python](https://img.shields.io/pypi/pyversions/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Downloads](https://img.shields.io/pypi/dm/dirplot.svg)](https://pepy.tech/project/dirplot)
[![License](https://img.shields.io/pypi/l/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/deeplook)

**dirplot** creates static nested treemap images for directory trees. It can display them in the system image viewer (default, works everywhere) or inline inside the terminal using the [iTerm2 inline image protocol](https://iterm2.com/documentation-images.html) or the [Kitty graphics protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/) — detected automatically at runtime.

Each rectangle represents a file; its **area** is proportional to the file size and its **colour** is determined by the file extension. Directories are shown as labelled, nested containers, mirroring the actual hierarchy.

![dirplot output](https://raw.githubusercontent.com/deeplook/dirplot/main/docs/dirplot.png)

## Installation

```bash
# As a standalone tool (recommended)
uv tool install dirplot

# Into the current environment
pip install dirplot
```

### From GitHub

```bash
# As a standalone tool
uv tool install git+https://github.com/deeplook/dirplot

# Into the current environment
pip install git+https://github.com/deeplook/dirplot
```

## Usage

```bash
# Use it before installing it
uvx dirplot --help

# Show dirplot for the current directory (opens image in system viewer)
dirplot .

# Save to a file without displaying
dirplot . --output dirplot.png --no-show

# Display inline (protocol auto-detected: iTerm2, Kitty, Ghostty)
dirplot . --inline

# Exclude directories
dirplot . --exclude .venv --exclude .git

# Use a different colormap and larger directory labels
dirplot . --colormap Set2 --font-size 18

# Render at a fixed resolution instead of terminal size
dirplot . --size 1920x1080 --output dirplot.png --no-show

# Don't apply cushion shading — makes tiles look flat
dirplot . --no-cushion
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--output` | `-o` | — | Save PNG to this path |
| `--show/--no-show` | | `--show` | Display the image after rendering |
| `--inline` | | off | Display in terminal (protocol auto-detected) |
| `--legend/--no-legend` | | `--no-legend` | Show file-extension colour legend |
| `--font-size` | `-s` | `12` | Directory label font size in pixels |
| `--colormap` | `-c` | `tab20` | Matplotlib colormap for unknown extensions |
| `--exclude` | `-e` | — | Path to exclude (repeatable) |
| `--size` | | terminal size | Output dimensions as `WIDTHxHEIGHT` (e.g. `1920x1080`) |
| `--header/--no-header` | | `--header` | Print info lines before rendering |
| `--cushion/--no-cushion` | | `--cushion` | Apply van Wijk cushion shading for a raised 3-D look |

## Inline Display

The `--inline` flag renders the image directly in the terminal. The protocol is auto-detected at runtime: terminals that support the [Kitty graphics protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/) use APC chunks (`ESC_G…`); all others fall back to the [iTerm2 inline image protocol](https://iterm2.com/documentation-images.html) (`ESC]1337;File=…`).

| Terminal | Platform | Protocol |
|---|---|---|
| [iTerm2](https://iterm2.com/) | macOS | iTerm2 |
| [WezTerm](https://wezfurlong.org/wezterm/) | macOS, Linux, Windows | iTerm2 |
| [Warp](https://www.warp.dev/) | macOS, Linux | iTerm2 |
| [Hyper](https://hyper.is/) | macOS, Linux, Windows | iTerm2 |
| [Kitty](https://sw.kovidgoyal.net/kitty/) | macOS, Linux | Kitty |
| [Ghostty](https://ghostty.org/) | macOS, Linux | Kitty |

The default mode (`--show`, no `--inline`) opens the PNG in the system viewer (`open` on macOS, `xdg-open` on Linux) and works in any terminal.

> **Note:** `--inline` does not work in AI coding assistants such as Claude Code, Cursor, or GitHub Copilot Chat. These tools intercept terminal output as plain text and do not implement any graphics protocol, so the escape sequences are either stripped or displayed as garbage. Use the default `--show` mode (system viewer) or `--output` to save the PNG to a file instead.

## How It Works

1. Scans the directory tree, collecting each file's path, extension, and size in bytes.
2. Computes a squarified dirplot layout recursively — directories allocate space for their children.
3. Renders to a PNG via Pillow (PIL) at the exact pixel dimensions of the current terminal window (detected via `TIOCGWINSZ`), or at a custom size when `--size` is given.
4. Displays via the system image viewer (`open` / `xdg-open`) or inline via an auto-detected terminal graphics protocol (iTerm2 or Kitty).

Extension colours come from the [GitHub Linguist](https://github.com/github/linguist) language colour table (~500 known extensions). Unknown extensions fall back to an MD5-stable colour derived from the chosen `--colormap`. File label text is automatically black or white depending on the background luminance.

## Development

```bash
git clone https://github.com/deeplook/dirplot
cd dirplot
make test
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

## Platform Support

This tool has been developed and tested on macOS. Linux should work, and Windows support is untested. Feedback and bug reports from Linux and Windows users are very welcome — please open an issue on GitHub.

## License

[MIT](LICENSE)
