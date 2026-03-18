# dirplot

[![CI](https://github.com/deeplook/dirplot/actions/workflows/ci.yml/badge.svg)](https://github.com/deeplook/dirplot/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Python](https://img.shields.io/pypi/pyversions/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Downloads](https://img.shields.io/pypi/dm/dirplot.svg)](https://pepy.tech/project/dirplot)
[![License](https://img.shields.io/pypi/l/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/deeplook)

**dirplot** creates static nested treemap images for directory trees. It can display them in the system image viewer (default, works everywhere) or inline inside the terminal using the [iTerm2 inline image protocol](https://iterm2.com/documentation-images.html) or the [Kitty graphics protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/) — detected automatically at runtime.

![dirplot output](https://raw.githubusercontent.com/deeplook/dirplot/main/docs/dirplot.png)

## Features

- Directories are shown as labelled, nested containers, mirroring the actual hierarchy.
- Squarified treemap layout — rectangles are as square as possible for easy reading.
- File area proportional to file size; colour determined by file extension.
- ~500 known extensions mapped to colours from the [GitHub Linguist](https://github.com/github/linguist) table; unknown extensions get an MD5-stable colour from any Matplotlib colormap.
- Label colour (black/white) chosen automatically based on background luminance.
- Output resolution matches the current terminal window pixel size (via `TIOCGWINSZ`), or a custom `WIDTHxHEIGHT`.
- Van Wijk cushion shading gives tiles a raised 3-D appearance (optional).
- **SVG output** (`--format svg` or `--output file.svg`) produces a fully self-contained interactive file: CSS hover highlight, a JavaScript floating tooltip panel, and cushion shading via a gradient — no external dependencies.
- Display via system image viewer or inline in the terminal (iTerm2 and Kitty protocols, auto-detected).
- Save output to a PNG or SVG file with `--output`, or pipe bytes to stdout with `--output -` (header lines go to stderr automatically).
- Exclude paths with `--exclude` (repeatable), or focus on specific subtrees with `--subtree` / `-s` (allowlist complement, supports nested paths like `src/dirplot/fonts`).
- Pass multiple local paths (`dirplot map src tests`) to scan each independently and display them under their common parent, ignoring all other siblings. Individual files are also accepted as roots (`dirplot map main.py util.py`).
- **Pipe `tree` or `find` output directly**: `tree src/ | dirplot map` and `find . -name "*.py" | dirplot map` are both supported. The format is auto-detected (`tree -s`, `tree -f`, and plain `find` output all work). Use `--paths-from FILE` to read from a file instead of stdin.
- **Live watch mode** (`dirplot watch`) — monitors one or more directories and regenerates the treemap automatically. Rapid bursts of events (e.g. `git checkout`) are debounced into a single render after a configurable quiet period (`--debounce`, default 0.5 s). With `--animate`, each render is captured as a frame and the complete APNG is written on Ctrl-C exit; changed tiles receive colour-coded highlight borders (green = created, blue = modified, red = deleted, orange = moved). All events can be logged to a JSONL file with `--event-log`.
- Works on macOS, Linux, and Windows; WSL2 fully supported.
- Scan remote hosts over SSH (`pip install "dirplot[ssh]"`), AWS S3 buckets (`pip install "dirplot[s3]"`), any public/private GitHub repository (including specific branch, tag, commit SHA, or subdirectory), **running Docker containers**, or **Kubernetes pods** — all without extra dependencies beyond the respective CLI/SDK. See [EXAMPLES.md](docs/EXAMPLES.md).
- Optional **file-count legend** (`--legend`) — a corner overlay listing the top extensions by number of files, with coloured swatches and counts, automatically sized to fit the image.
- **Breadcrumbs mode** (on by default) — single-child directory chains are collapsed into one tile with a `foo / bar / baz` header label. Middle segments are replaced with `…` when the tile is too narrow. Disable with `-B` / `--no-breadcrumbs`.
- **Tree depth** shown in the root tile header alongside the file count and total size (e.g. `myproject — 124 files, 18 dirs, 4.0 MB (…), depth: 6`).
- **Wide archive support** — reads zip, tar (gz/bz2/xz/zst), 7z, rar, and all ZIP-based formats (jar, whl, apk, nupkg, vsix, ipa, …) as virtual directory trees without unpacking. Encrypted archives are handled gracefully: metadata-only reads work without a password for most formats; a password can be supplied with `--password` or entered interactively when needed. Additional formats (iso, cpio, rpm, cab, lha/lzh, xar/pkg, a/ar, tar.zst) require the optional `libarchive` extra: `pip install 'dirplot[libarchive]'`.

## How It Works

1. Scans the directory tree, collecting each file's path, extension, and size in bytes.
2. Computes a squarified dirplot layout recursively — directories allocate space for their children.
3. Renders to a PNG via Pillow (PIL) at the exact pixel dimensions of the current terminal window (detected via `TIOCGWINSZ`), or at a custom size when `--size` is given.
4. Displays via the system image viewer (`open` / `xdg-open`) or inline via an auto-detected terminal graphics protocol (iTerm2 or Kitty).

Extension colours come from the [GitHub Linguist](https://github.com/github/linguist) language colour table (~500 known extensions). Unknown extensions fall back to an MD5-stable colour derived from the chosen `--colormap`. File label text is automatically black or white depending on the background luminance.

## Installation

> **Note:** The recommended install methods below use [uv](https://docs.astral.sh/uv/). See the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it yet. Alternatively, use `pip install dirplot` to install without uv.

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

## Platform Support

This tool has been developed and tested on macOS and is CI-tested on Linux and Windows (Python 3.10+). The default `--show` mode works on all platforms. The `--inline` mode requires a terminal emulator that supports the iTerm2 or Kitty graphics protocol; on Windows, only [WezTerm](https://wezfurlong.org/wezterm/) currently qualifies. WSL2 is treated as Linux and has full support. Feedback and bug reports are welcome — please open an issue on GitHub.

## Usage

```bash
# Use it before installing it
uvx dirplot --help

# Show dirplot for the current directory (opens image in system viewer)
dirplot map .

# Show current terminal size in characters and pixels
dirplot termsize

# Save to a file without displaying
dirplot map . --output dirplot.png --no-show

# Display inline (protocol auto-detected: iTerm2, Kitty, Ghostty)
dirplot map . --inline

# Exclude directories
dirplot map . --exclude .venv --exclude .git

# Map two specific subtrees under their common parent
dirplot map src tests

# Map individual files under their common parent
dirplot map src/main.py src/util.py

# Pipe tree or find output — format is auto-detected
tree src/            | dirplot map
tree -s src/         | dirplot map        # tree with file sizes
find . -name "*.py"  | dirplot map
find . -type d       | dirplot map        # directories only

# Read a saved path list from a file
tree src/ > paths.txt && dirplot map --paths-from paths.txt

# Focus on named subtrees of a root (allowlist; supports nested paths)
dirplot map . --subtree src --subtree tests
dirplot map . --subtree src/dirplot/fonts

# Use a different colormap and larger directory labels
dirplot map . --colormap Set2 --font-size 18

# Render at a fixed resolution instead of terminal size
dirplot map . --size 1920x1080 --output dirplot.png --no-show

# Don't apply cushion shading — makes tiles look flat
dirplot map . --no-cushion

# Show a file-count legend (top 20 extensions by default)
dirplot map . --legend

# Show a file-count legend limited to 10 entries
dirplot map . --legend 10

# Disable breadcrumbs (show full nested hierarchy instead of collapsed chains)
dirplot map . -B

# Save as an interactive SVG (hover highlight + floating tooltip)
dirplot map . --output treemap.svg --no-show

# Force SVG format explicitly
dirplot map . --format svg --output treemap.svg --no-show

# Write PNG bytes to stdout (pipe to another tool)
dirplot map . --output - --no-show | convert - -resize 50% small.png

# Write SVG to stdout
dirplot map . --output - --format svg --no-show > treemap.svg

# Watch a directory and regenerate the treemap on every change (500 ms debounce)
dirplot watch . --output treemap.png

# Watch multiple directories simultaneously
dirplot watch src tests --output treemap.png

# Longer quiet window — useful for slow build systems or noisy editors
dirplot watch . --output treemap.png --debounce 1.0

# Disable debounce — regenerate immediately on every raw event (old behaviour)
dirplot watch . --output treemap.png --debounce 0

# Record all file-system events to a JSONL file; written on Ctrl-C exit
dirplot watch src --output treemap.png --event-log events.jsonl

# Watch and build an animated APNG — one frame per debounced render, written on Ctrl-C
dirplot watch . --output treemap.png --animate
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--paths-from` | | — | File containing a path list (`tree` or `find` output); use `-` for stdin |
| `--output` | `-o` | — | Save to this path (PNG or SVG); use `-` to write to stdout |
| `--format` | `-f` | auto | Output format: `png` or `svg`. Auto-detected from `--output` extension |
| `--show/--no-show` | | `--show` | Display the image after rendering |
| `--inline` | | off | Display in terminal (protocol auto-detected; PNG only) |
| `--legend [N]` | | off | Show file-count legend; `N` sets max entries (default: 20) |
| `--font-size` | | `12` | Directory label font size in pixels |
| `--colormap` | `-c` | `tab20` | Matplotlib colormap for unknown extensions |
| `--exclude` | `-e` | — | Path to exclude (repeatable) |
| `--subtree` | `-s` | — | Show only this subtree of the root (repeatable); supports nested paths like `src/dirplot/fonts` |
| `--size` | | terminal size | Output dimensions as `WIDTHxHEIGHT` (e.g. `1920x1080`) |
| `--header/--no-header` | | `--header` | Print info lines before rendering |
| `--cushion/--no-cushion` | | `--cushion` | Apply van Wijk cushion shading for a raised 3-D look |
| `--log/--no-log` | | `--no-log` | Use log of file sizes for layout, making small files more visible |
| `--breadcrumbs/--no-breadcrumbs` | `-b`/`-B` | `--breadcrumbs` | Collapse single-child directory chains into `foo / bar / baz` labels |
| `--password` | | — | Password for encrypted archives; prompted interactively if not supplied and needed |
| `--github-token` | | `$GITHUB_TOKEN` | GitHub personal access token for private repos or higher rate limits |

### `watch` options

These options are specific to the `watch` subcommand.

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | required | Output file (`.png` or `.svg`) updated on each change |
| `--debounce` | `0.5` | Seconds of quiet after the last event before regenerating; `0` disables |
| `--event-log` | — | Write all raw events as JSONL to this file on Ctrl-C exit |
| `--animate` / `--no-animate` | off | Capture one frame per debounced render; write the complete APNG on Ctrl-C exit |
| `--log` / `--no-log` | off | Use log of file sizes for layout |
| `--size` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum recursion depth |
| `--exclude` / `-e` | — | Path to exclude (repeatable) |
| `--colormap` / `-c` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion` / `--no-cushion` | on | Van Wijk cushion shading |

## Inline Display

The `--inline` flag renders the image directly in the terminal. The protocol is auto-detected at runtime: terminals that support the [Kitty graphics protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/) use APC chunks (`ESC_G…`); all others fall back to the [iTerm2 inline image protocol](https://iterm2.com/documentation-images.html) (`ESC]1337;File=…`).

| Terminal | Platform | Protocol |
|---|---|---|
| [iTerm2](https://iterm2.com/) | macOS | iTerm2 |
| [WezTerm](https://wezfurlong.org/wezterm/) | macOS, Linux, Windows | Kitty & iTerm2 |
| [Warp](https://www.warp.dev/) | macOS, Linux | iTerm2 |
| [Hyper](https://hyper.is/) | macOS, Linux, Windows | iTerm2 |
| [Kitty](https://sw.kovidgoyal.net/kitty/) | macOS, Linux | Kitty |
| [Ghostty](https://ghostty.org/) | macOS, Linux | Kitty |

The default mode (`--show`, no `--inline`) opens the PNG in the system viewer (`open` on macOS, `xdg-open` on Linux, system default on Windows) and works in any terminal.

> **Windows note:** Common Windows shells (PowerShell, cmd, Git Bash) and terminal emulators (Windows Terminal, ConEmu) do not support any inline image protocol. `--inline` will silently produce no output in these environments. [WezTerm](https://wezfurlong.org/wezterm/) is currently the only mainstream Windows terminal emulator that supports inline image rendering (via the Kitty graphics protocol). WSL2 is treated as Linux and has full support.

> **Tip:** In terminals that support inline images (iTerm2, WezTerm, Kitty, etc.), the rendered image can often be dragged directly out of the terminal window and dropped into another application or saved to the desktop — no `--output` needed. This drag-and-drop behaviour is not guaranteed across all terminals.

> **Note:** `--inline` does not work in AI coding assistants such as Claude Code, Cursor, or GitHub Copilot Chat. These tools intercept terminal output as plain text and do not implement any graphics protocol, so the escape sequences are either stripped or displayed as garbage. Use the default `--show` mode (system viewer) or `--output` to save the PNG to a file instead. Or use [Pi](https://pi.dev) where it is easily added as an extension.

## Archives

dirplot can read local archive files without unpacking them — zip, tar (gz/bz2/xz/zst), 7z, rar, and all ZIP-based formats (jar, whl, apk, nupkg, vsix, ipa). See [ARCHIVES.md](docs/ARCHIVES.md) for the full list, dependencies, and platform notes.

Formats handled by libarchive (iso, cpio, rpm, cab, lha, xar, pkg, dmg, a/ar, tar.zst) require the optional extra and the system libarchive library:

```bash
pip install 'dirplot[libarchive]'          # Python wrapper
brew install libarchive                    # macOS
# apt install libarchive-dev              # Debian/Ubuntu
```

```bash
dirplot map project.zip
dirplot map release.tar.gz --depth 2
dirplot map app.jar
dirplot map image.iso                      # requires dirplot[libarchive]
```

## Remote Access

dirplot can scan SSH hosts, AWS S3 buckets, GitHub repositories, running Docker containers, and Kubernetes pods. See [EXAMPLES.md](docs/EXAMPLES.md) for full details.

```bash
pip install "dirplot[ssh]"   # SSH via paramiko
pip install "dirplot[s3]"    # AWS S3 via boto3
                             # GitHub: no extra dependency needed
                             # Docker: only the docker CLI required
                             # Kubernetes: only kubectl required
```

```bash
dirplot map ssh://alice@prod.example.com/var/www
dirplot map s3://noaa-ghcn-pds --no-sign
dirplot map github://pallets/flask
dirplot map github://torvalds/linux@v6.12/Documentation
dirplot map docker://my-container:/app
dirplot map pod://my-pod:/app
dirplot map pod://my-pod@staging:/app
```

### GitHub authentication

Public repositories work without a token but are subject to GitHub's unauthenticated rate limit of **60 requests/hour**. A personal access token raises this to **5,000 requests/hour** and is required for private repositories.

Pass a token via the `--github-token` flag or the `GITHUB_TOKEN` environment variable:

```bash
# via flag
dirplot map github://my-org/private-repo --github-token ghp_…

# via environment variable (also picked up automatically by the CLI)
export GITHUB_TOKEN=ghp_…
dirplot map github://my-org/private-repo
```

To create a token: GitHub → Settings → Developer settings → Personal access tokens → Generate new token (see [GitHub's guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)). For read-only treemap access the `public_repo` scope (or no scope for public repos) is sufficient; add `repo` for private repositories.

## Python API

> **Note:** The programmatic Python API is still evolving and may change between releases without notice. Pin a specific version if you depend on it. The CLI interface is stable.

The public API is small — `build_tree`, `create_treemap`, `create_treemap_svg`, and the display helpers:

```python
from pathlib import Path
from dirplot import build_tree, create_treemap, create_treemap_svg

root = build_tree(Path("/path/to/project"))

# PNG — returns a BytesIO containing PNG bytes
buf = create_treemap(root, width_px=1920, height_px=1080, colormap="tab20", cushion=True)
Path("treemap.png").write_bytes(buf.read())

# SVG — returns a BytesIO containing UTF-8 SVG bytes
# Includes CSS hover highlight, a JS floating tooltip, and cushion gradient shading.
buf = create_treemap_svg(root, width_px=1920, height_px=1080, cushion=True)
Path("treemap.svg").write_bytes(buf.read())
```

To open a PNG in the system image viewer or display it inline in the terminal:

```python
from dirplot.display import display_window, display_inline

buf.seek(0)
display_window(buf)   # system viewer (works everywhere)

buf.seek(0)
display_inline(buf)   # inline in terminal (iTerm2 / Kitty / WezTerm)
```

In a Jupyter notebook, PNG output renders automatically via PIL:

```python
from PIL import Image
buf = create_treemap(root, width_px=1280, height_px=720)
Image.open(buf)  # Jupyter renders PIL images automatically via _repr_png_()
```

## Development

```bash
git clone https://github.com/deeplook/dirplot
cd dirplot
make test
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

## License

[MIT](LICENSE)
