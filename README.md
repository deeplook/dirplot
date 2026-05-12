# dirplot

[![CI](https://github.com/deeplook/dirplot/actions/workflows/ci.yml/badge.svg)](https://github.com/deeplook/dirplot/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Python](https://img.shields.io/pypi/pyversions/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Downloads](https://img.shields.io/pypi/dm/dirplot.svg)](https://pepy.tech/project/dirplot)
[![License](https://img.shields.io/pypi/l/dirplot.svg)](https://pypi.org/project/dirplot/)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/deeplook)

**dirplot** creates nested treemap images for directory trees. It can display them in the system image viewer or inline in the terminal (iTerm2 and Kitty protocols, auto-detected). It also animates git history, watches live filesystems, and scans remote sources.

![dirplot output](https://raw.githubusercontent.com/deeplook/dirplot/main/docs/dirplot.png)

## Features

- Squarified treemap layout; file area proportional to size; per-extension colours (GitHub Linguist palette for known types, configurable Matplotlib colormap for the rest).
- PNG, animated PNG (APNG), MP4, and MOV output for single frames and animations; interactive SVG for static maps; renders at terminal pixel size or a custom `WIDTHxHEIGHT`.
- **Animate git history** (`dirplot git`), **Mercurial history** (`dirplot hg`), and **replay filesystem event logs** (`dirplot replay`) — output APNG, MP4, or MOV. **Watch live filesystems** (`dirplot watch`) with optional snapshot and event logging.
- **Scan metrics** (`dirplot metrics`) — file/dir counts, total size, depth, top extensions by count or size, largest files and directories with percentage of total; JSON output supported.
- **Compare two trees** (`dirplot diff`) — treemap diff of any two sources (local dirs, GitHub repos, archives, S3, SSH, Docker, K8s, or two commits/tags); `dirplot diff .` shows uncommitted changes; files sized by B; colour-coded borders show added (green), removed (red), and changed (blue) files. Git/hg repos scan only tracked files; change detection uses blob hashes (LFS-aware).
- Scan **SSH hosts**, **AWS S3**, **GitHub repos** (public and private), **Docker containers**, and **Kubernetes pods** — no extra deps beyond the respective CLI.
- Read **archives** directly (zip, tar, 7z, rar, jar, whl, …) without unpacking.
- Works on macOS, Linux, and Windows (WSL2 fully supported).

## Installation

```bash
# Recommended: isolated tool install via uv (fastest)
uv tool install dirplot

# Alternative: pipx (install pipx first if needed: brew install pipx on macOS)
pipx install dirplot

# Into the current environment
pip install dirplot
```

Optional extras: `pip install "dirplot[ssh]"`, `"dirplot[s3]"`, `"dirplot[libarchive]"`.

`dirplot watch` uses [watchdog](https://github.com/gorakhargosh/watchdog) for filesystem monitoring — installed automatically as a dependency.

`dirplot git` requires `git` on `PATH`; `dirplot hg` requires `hg` (Mercurial) on `PATH`. MP4 output (`dirplot git`, `dirplot hg`, `dirplot replay`) requires [ffmpeg](https://ffmpeg.org/) on `PATH`. `dirplot read-meta` on `.mp4` files also requires `ffprobe` (bundled with ffmpeg).

## Quick start

```bash
dirplot map .                                                    # current directory
dirplot map . --inline                                           # display in terminal
dirplot map . --output treemap.png --no-show                     # save to file
dirplot map . --log-scale 4 --inline                              # log scale (4× ratio), inline
dirplot map github://pallets/flask                               # GitHub repo
dirplot map docker://my-container:/app                           # Docker container
dirplot map project.zip                                          # archive file
tree src/ | dirplot map                                          # pipe tree output

dirplot git . -o history.mp4 --animate                           # full git history
dirplot git . -o history.mp4 --animate --last 30d                # last 30 days
dirplot git github://owner/repo -o h.mp4 --animate --last 7d     # GitHub, last week

dirplot hg /path/to/repo -o history.png --animate                # full hg history
dirplot hg /path/to/repo@tip -o history.png                      # static, tip only

dirplot watch . --snapshot treemap.png                           # live watch, snapshot on each change
dirplot watch . --event-log events.jsonl                         # record events for replay
dirplot replay events.jsonl -o timelapse.mp4 --total-duration 30 # render recording as MP4

dirplot demo                                                     # run examples, save to ./demo/

dirplot metrics .                                                # scan metrics: counts, size, top extensions
dirplot metrics . --sort-by size                                 # sort extensions by total bytes
dirplot metrics . --top 5 --json                                 # top-5 entries as JSON
dirplot map . --metrics --no-show                                # treemap + metrics in one pass

dirplot diff .                                                    # uncommitted changes (git/hg)
dirplot diff . --no-context                                       # only show changed files
dirplot diff .@HEAD~5 .@HEAD                                      # last 5 commits
dirplot diff old/ new/                                            # compare two directories
dirplot diff old/ new/ --output diff.png --no-show                # save to file
dirplot diff github://owner/repo@v1 github://owner/repo@v2        # compare two GitHub tags
dirplot diff archive_v1.tar.gz archive_v2.zip                     # compare two archives
```

## Documentation

- [CLI reference](docs/CLI.md) — all commands, flags, and usage examples
- [Remote access](docs/EXAMPLES.md) — SSH, S3, GitHub, Docker, Kubernetes
- [Archives](docs/ARCHIVES.md) — supported formats and dependencies
- [Python API](docs/API.md) — programmatic usage

## Development

```bash
git clone https://github.com/deeplook/dirplot
cd dirplot
make test
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

## License

MIT — see [LICENSE](LICENSE).
