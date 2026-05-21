# dirplot

[![CI](https://github.com/deeplook/dirplot/actions/workflows/ci.yml/badge.svg)](https://github.com/deeplook/dirplot/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Python](https://img.shields.io/pypi/pyversions/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Downloads](https://img.shields.io/pypi/dm/dirplot.svg)](https://pepy.tech/project/dirplot)
[![License](https://img.shields.io/pypi/l/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Docs](https://img.shields.io/badge/docs-deeplook.github.io%2Fdirplot-blue)](https://deeplook.github.io/dirplot)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/deeplook)

**dirplot** creates nested treemap images for directory trees. It can display them in the system image viewer or inline in the terminal (iTerm2 and Kitty protocols, auto-detected). It also animates git history, watches live filesystems, and scans remote sources.

```bash
pip install dirplot
dirplot map .          # treemap of current directory, opens in system viewer
dirplot map . --inline # display inline in terminal (iTerm2 / Kitty / Ghostty)
```

![dirplot output](https://raw.githubusercontent.com/deeplook/dirplot/main/docs/images/dirplot.png)

## Use cases

- **Find what's eating your disk** — map `~/Downloads`, `~/.cache`, or `node_modules` across a monorepo to spot the culprits at a glance.
- **Inspect before you install** — visualise a Python wheel, JAR, or RPM without unpacking it.
- **Understand a codebase instantly** — map a legacy project or a large GitHub repo to grasp its structure before reading a single line.
- **Compare releases** — diff two archive versions or two git tags to see exactly what grew, shrank, or disappeared.
- **Scan remote filesystems** — map an SSH host, S3 bucket, Docker container, or Kubernetes pod without copying anything locally.
- **AI & data exploration** — map a vector database, model weights directory, or agent memory folder (`~/.claude/projects/`).
- **Sysadmin at a glance** — map `/var/log` to see which services generate the most logs, or scan a container image's filesystem layers.
- **Animate history** — watch a repository or live filesystem evolve over time as a timelapse.

## Features

- Squarified treemap layout; file area proportional to size; per-extension colours (GitHub Linguist palette for known types, configurable Matplotlib colormap for the rest).
- PNG, animated PNG (APNG), MP4, and MOV output for single frames and animations; interactive SVG for static maps; renders at terminal pixel size or a custom `WIDTHxHEIGHT`.
- **Inline terminal display** — renders directly into iTerm2, Kitty, Ghostty, WezTerm, and Warp without opening a separate window; protocol auto-detected.
- **Animate git history** (`dirplot git`), **Mercurial history** (`dirplot hg`), and **replay filesystem event logs** (`dirplot replay`) — output APNG, MP4, or MOV. **Watch live filesystems** (`dirplot watch`) with optional snapshot and event logging.
- **Scan metrics** (`dirplot metrics`) — file/dir counts, total size, depth, top extensions by count or size, largest files and directories with percentage of total; JSON output supported.
- **Compare two trees** (`dirplot diff`) — treemap diff of any two sources (local dirs, GitHub repos, archives, S3, SSH, Docker, K8s, or two commits/tags); `dirplot diff .` shows uncommitted changes; files sized by B; colour-coded borders show added (green), removed (red), and changed (blue) files. Git/hg repos scan only tracked files; change detection uses blob hashes (LFS-aware).
- Scan **SSH hosts**, **AWS S3**, **GitHub repos** (public and private), **Docker containers**, **Kubernetes pods**, and **Google Drive** — no extra deps beyond the respective CLI.
- Read **archives** directly (zip, tar, 7z, rar, jar, whl, …) without unpacking.
- Works on macOS, Linux, and Windows (WSL2 fully supported).

## Installation

```bash
# Try without installing (always fetches the latest release)
uvx dirplot@latest --version

# Recommended: isolated tool install via uv (fastest)
uv tool install dirplot

# Alternative: pipx (install pipx first if needed: brew install pipx on macOS)
pipx install dirplot

# Into the current environment
pip install dirplot
```

**Optional extras** — install only what you need:

| Extra | Enables | Install |
|---|---|---|
| `ssh` | Scan remote servers via SSH (adds [paramiko](https://www.paramiko.org/)) | `pip install "dirplot[ssh]"` |
| `s3` | Scan AWS S3 buckets (adds [boto3](https://boto3.amazonaws.com/)) | `pip install "dirplot[s3]"` |
| `libarchive` | Additional archive formats: `.tar.zst`, `.iso`, `.dmg`, `.rpm`, `.cab`, … (requires system [libarchive](https://libarchive.org/)) | `pip install "dirplot[libarchive]"` |

**Other runtime requirements:**

- `dirplot watch` — [watchdog](https://github.com/gorakhargosh/watchdog) is installed automatically.
- `dirplot git` — requires `git` on `PATH`.
- `dirplot hg` — requires `hg` (Mercurial) on `PATH`.
- MP4 output (`dirplot git`, `dirplot hg`, `dirplot replay`) — requires [ffmpeg](https://ffmpeg.org/) on `PATH`.
- `dirplot meta` on `.mp4` files — requires `ffprobe` (bundled with ffmpeg).

## Quick start

```bash
dirplot map .                                # current directory, opens in viewer
dirplot map . --inline                       # display in terminal (iTerm2/Kitty/Ghostty)
dirplot map . --output treemap.png --no-show # save to file
dirplot map . --log-scale 4                  # log scale when one file dominates
dirplot map github://pallets/flask           # GitHub repo
dirplot map project.zip                      # archive — no unpacking needed

dirplot diff .                               # uncommitted changes
dirplot diff .@HEAD~5 .@HEAD                 # last 5 commits

dirplot metrics .                            # file counts, sizes, top extensions
dirplot git . --range main --output h.mp4    # full git history as MP4
```

See the [full documentation](https://deeplook.github.io/dirplot) for the complete command reference.

## Documentation

Full documentation is available at **[deeplook.github.io/dirplot](https://deeplook.github.io/dirplot)**.

## Development

```bash
git clone https://github.com/deeplook/dirplot
cd dirplot
make test
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

A significant portion of this codebase was developed with AI assistance (primarily Claude by Anthropic). All generated code was reviewed and curated by the author.

## License

MIT — see [LICENSE](LICENSE).
