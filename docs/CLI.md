# CLI Reference

## `dirplot map` — treemap for any directory tree

```bash
# Use without installing
uvx dirplot --help

# Current directory in system viewer
dirplot map .

# Display inline in terminal (iTerm2 / Kitty / WezTerm, auto-detected)
dirplot map . --inline

# Save to file without displaying
dirplot map . --output treemap.png --no-show

# Exclude paths — plain names, globs, or relative paths
dirplot map . --exclude .venv --exclude .git
dirplot map . --exclude "*.egg-info" --exclude "**/__pycache__"
dirplot map . --exclude src/vendor

# Focus on named subtrees (allowlist complement to --exclude)
dirplot map . --include src --include tests
dirplot map . --include src/dirplot/fonts

# Multiple roots shown under their common parent
dirplot map src tests
dirplot map src/main.py src/util.py

# Pipe tree or find output (format auto-detected)
tree src/           | dirplot map
tree -s src/        | dirplot map
find . -name "*.py" | dirplot map
find . -type d      | dirplot map

# Read a saved path list from a file
tree src/ > paths.txt && dirplot map --paths-from paths.txt

# Custom size, colormap, font
dirplot map . --size 1920x1080 --output treemap.png --no-show
dirplot map . --colormap Set2 --font-size 18

# Log scale — use when one large file dominates and squashes everything else
dirplot map . --log-scale 2

# Disable cushion shading
dirplot map . --no-cushion

# Show a file-count legend
dirplot map . --legend           # up to 20 entries
dirplot map . --legend 10        # cap at 10

# Disable breadcrumb collapsing
dirplot map . --no-breadcrumbs

# Interactive SVG output (hover highlight + floating tooltip)
dirplot map . --output treemap.svg --no-show
dirplot map . --format svg --output treemap.svg --no-show

# Pipe PNG bytes to stdout
dirplot map . --output - --no-show | convert - -resize 50% small.png
dirplot map . --output - --format svg --no-show > treemap.svg

# Archive files — no unpacking needed
dirplot map project.zip
dirplot map release.tar.gz --depth 2
dirplot map app.jar

# Remote sources
dirplot map ssh://alice@prod.example.com/var/www
dirplot map s3://noaa-ghcn-pds --no-sign
dirplot map github://pallets/flask
dirplot map github://torvalds/linux@v6.12/Documentation
dirplot map docker://my-container:/app
dirplot map pod://my-pod:/app
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--paths-from` | | — | File with path list (`tree`/`find` output); `-` for stdin |
| `--output` | `-o` | — | Save to this path (PNG or SVG); `-` for stdout |
| `--format` | `-f` | auto | Output format: `png` or `svg` |
| `--show/--no-show` | | `--show` | Display the image after rendering |
| `--inline` | | off | Display in terminal (auto-detected protocol; PNG only) |
| `--legend [N]` | | off | File-count legend; `N` = max entries (default: 20) |
| `--font-size` | | `12` | Directory label font size in pixels |
| `--colormap` | | `tab20` | Matplotlib colormap for unknown extensions |
| `--exclude` | `-e` | — | Pattern to exclude (repeatable): plain name, glob (``*.egg-info``), ``**`` glob, or relative path |
| `--include` | | — | Show only this subtree (repeatable); supports nested paths; allowlist complement to `--exclude` |
| `--depth` | | unlimited | Maximum recursion depth |
| `--size` | | terminal size | Output dimensions as `WIDTHxHEIGHT` (e.g. `1920x1080`) |
| `--header/--no-header` | | `--header` | Print info lines before rendering |
| `--cushion/--no-cushion` | | `--cushion` | Van Wijk cushion shading for a raised 3-D look |
| `--log-scale` | | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--breadcrumbs/--no-breadcrumbs` | | `--breadcrumbs` | Collapse single-child chains into `foo / bar / baz` labels |
| `--metrics/--no-metrics` | | off | Print detailed metrics after scanning (same output as `dirplot metrics`) |
| `--password-file` | | — | File containing archive password; prompted interactively if not supplied |
| `--github-token-file` | | `$GITHUB_TOKEN` | File containing GitHub personal access token |
| `--ssh-key` | | `~/.ssh/id_rsa` | SSH private key path |
| `--ssh-password-file` | | — | File containing SSH password |
| `--aws-profile` | | `$AWS_PROFILE` | Named AWS profile |
| `--no-sign` | | off | Anonymous access for public S3 buckets |

---

## `dirplot metrics` — directory metrics

Scans a directory tree and prints a structured text summary: file/directory counts, total size, tree depth, scan time, top file extensions (by count or size), and the largest files and directories with their share of total size. All remote sources supported by `dirplot map` are accepted.

```bash
# Basic metrics for the current directory
dirplot metrics .

# Remote sources work identically to `dirplot map`
dirplot metrics github://pallets/flask
dirplot metrics s3://my-bucket --no-sign
dirplot metrics project.zip

# Sort top extensions by total bytes instead of file count
dirplot metrics . --sort-by size

# Show only top 5 entries in each list
dirplot metrics . --top 5

# JSON output — pipe into jq, scripts, or monitoring tools
dirplot metrics . --json
dirplot metrics . --json | jq '.largest_files[0]'

# Combine with map to get treemap + metrics in one pass
dirplot map . --metrics --no-show
```

### Output fields

```
  Files:      1,011
  Dirs:       70  (0 empty)
  Total size: 4.5 MB
  Depth:      7
  Scan time:  1.28s
  Top extensions (10) [by count]:
    .py                    962    2.3 MB
    .json                   19    48.2 KB
    …
  Largest files:
    671.6 KB     14.9%  uv.lock
    191.8 KB      4.3%  CHANGELOG.md
    …
  Largest dirs:
    2.3 MB       51.1%  src
    …
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--top` | | `10` | Number of entries to show in each list |
| `--sort-by` | | `count` | Sort top extensions by `count` (files) or `size` (bytes) |
| `--json` / `--no-json` | | off | Output all metrics as JSON |
| `--exclude` | `-e` | — | Pattern to exclude (repeatable): plain name, glob (``*.egg-info``), ``**`` glob, or relative path |
| `--include` | | — | Show only this subtree (repeatable); allowlist complement to `--exclude` |
| `--depth` | | unlimited | Maximum recursion depth |
| `--paths-from` | | — | File with path list (`tree`/`find` output); `-` for stdin |
| `--password-file` | | — | File containing archive password; prompted interactively if needed |
| `--github-token-file` | | `$GITHUB_TOKEN` | File containing GitHub personal access token |
| `--ssh-key` | | `~/.ssh/id_rsa` | SSH private key path |
| `--ssh-password-file` | | — | File containing SSH password |
| `--aws-profile` | | `$AWS_PROFILE` | Named AWS profile |
| `--no-sign` | | off | Anonymous access for public S3 buckets |
| `--k8s-namespace` | | — | Kubernetes namespace |
| `--k8s-container` | | — | Container name for multi-container pods |

---

## `dirplot diff` — compare two directory trees

Compares two directory trees A and B as a treemap. Tiles are sized by B (the new tree). Colour-coded borders indicate the diff status of each file: **green** = added (present in B, absent in A), **red** = removed (present in A, absent in B), **blue** = changed (present in both, but content differs). Unchanged files have no border. By default, unchanged files are included as context (`--context`); pass `--no-context` to show only changed, added, and removed files.

A and B can be **any source supported by `dirplot map`** — local directories, GitHub repos, archives, S3 paths, SSH hosts, Docker containers, or Kubernetes pods.

**When a source is a local git or hg repository**, only tracked files are scanned (equivalent to `git diff` / `hg diff` semantics — untracked files are ignored). Change detection uses blob hash comparison, not file size, so edits that don't change file size are caught correctly. Git LFS files are handled transparently.

**Single-argument shorthand** — pass only one argument to diff the working tree against HEAD (git) or tip (hg):

```bash
dirplot diff .                  # uncommitted changes in current repo
dirplot diff /path/to/repo      # uncommitted changes in that repo
```

```bash
# Basic comparison — open in system viewer
dirplot diff old/ new/

# Uncommitted changes in current git/hg repo
dirplot diff .

# Uncommitted changes, only show changed files
dirplot diff . --no-context

# Compare two commits in the current repo
dirplot diff .@HEAD~5 .@HEAD

# Compare two git commits by SHA
dirplot diff .@abc1234 .@def5678

# Compare two GitHub tags
dirplot diff github://owner/repo@v1.0 github://owner/repo@v2.0

# Compare two archives
dirplot diff release-1.0.tar.gz release-2.0.tar.gz

# Compare an S3 prefix against a local directory
dirplot diff s3://my-bucket/v1 ./v2

# Save to file
dirplot diff old/ new/ --output diff.png --no-show

# Light mode, SVG output
dirplot diff old/ new/ --light --output diff.svg --no-show
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--output` | `-o` | — | Save to this path (PNG or SVG); `-` for stdout |
| `--format` | `-f` | auto | Output format: `png` or `svg` |
| `--show/--no-show` | | `--show` | Display the image after rendering |
| `--inline` | | off | Display in terminal (auto-detected protocol; PNG only) |
| `--context/--no-context` | | `--context` | Include unchanged files in the treemap |
| `--font-size` | | `12` | Directory label font size in pixels |
| `--colormap` | | `tab20` | Colormap for unknown extensions |
| `--exclude` | `-e` | — | Pattern to exclude (repeatable): plain name, glob (``*.egg-info``), ``**`` glob, or relative path |
| `--include` | | — | Show only this subtree (repeatable); allowlist complement to `--exclude` |
| `--depth` | | unlimited | Maximum recursion depth |
| `--size` | | terminal size | Output dimensions as `WIDTHxHEIGHT` (e.g. `1920x1080`) |
| `--cushion/--no-cushion` | | `--cushion` | Van Wijk cushion shading for a raised 3-D look |
| `--dark/--light` | | `--dark` | Canvas and label colour scheme |
| `--log-scale` | | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--header/--no-header` | | `--header` | Print info lines before rendering |
| `--quiet` | | off | Suppress all status output |
| `--ssh-key` | | `~/.ssh/id_rsa` | SSH private key file |
| `--ssh-password-file` | | — | File containing SSH password |
| `--aws-profile` | | `$AWS_PROFILE` | Named AWS profile for S3 access |
| `--no-sign` | | off | Anonymous access for public S3 buckets |
| `--github-token-file` | | `$GITHUB_TOKEN` | File containing GitHub personal access token |
| `--k8s-namespace` | | — | Kubernetes namespace |
| `--k8s-container` | | — | Container name for multi-container pods |
| `--password-file` | | — | File containing archive password |
| `--no-input` | | off | Fail instead of prompting for passwords |

---

## `dirplot watch` — live watch mode

Monitors directories and regenerates the treemap on every filesystem change. Use `--snapshot` to write the current PNG on each change (useful for external tools or wallpaper updaters). To produce an animated APNG or MP4, record events with `--event-log` and replay with `dirplot replay`.

```bash
# Watch a directory (display only, no file output)
dirplot watch .

# Watch multiple directories
dirplot watch src tests

# Write a snapshot PNG on each change
dirplot watch . --snapshot treemap.png

# Adjust debounce (default 0.5 s)
dirplot watch . --snapshot treemap.png --debounce 1.0
dirplot watch . --snapshot treemap.png --debounce 0   # immediate

# Log all events to a JSONL file (replay later with dirplot replay)
dirplot watch src --event-log events.jsonl
dirplot watch src --snapshot treemap.png --event-log events.jsonl
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--snapshot` | — | Write the current treemap as a PNG to this file on each change |
| `--debounce` | `0.5` | Seconds of quiet before regenerating; `0` disables |
| `--event-log` | — | Write raw events as JSONL on Ctrl-C exit |
| `--log-scale` | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--size` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum recursion depth |
| `--exclude` / `-e` | — | Pattern to exclude (repeatable): plain name, glob (``*.egg-info``), ``**`` glob, or relative path |
| `--colormap` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion` / `--no-cushion` | on | Van Wijk cushion shading |

---

## `dirplot replay` — event log replay

Replays a JSONL event log produced by `dirplot watch --event-log` as an animated treemap. Events are grouped into time buckets (one frame per bucket).

> **Requires** `ffmpeg` on `PATH` for MP4 output.

```bash
# Replay as APNG (60-second buckets, 30-second total)
dirplot replay events.jsonl --output replay.apng --total-duration 30

# Replay as MP4
dirplot replay events.jsonl --output replay.mp4 --total-duration 30
dirplot replay events.jsonl --output replay.mp4 --crf 18         # higher quality
dirplot replay events.jsonl --output replay.mp4 --codec libx265  # smaller file

# Fine-grained buckets with fixed frame duration
dirplot replay events.jsonl --output replay.apng --bucket 10 --frame-duration 200

# Fade out at the end
dirplot replay events.jsonl --output replay.mp4 --total-duration 30 --fade-out
dirplot replay events.jsonl --output replay.png --total-duration 30 --fade-out --fade-out-color white
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | required | Output `.png`, `.apng`, or `.mp4` |
| `--bucket` | `60.0` | Time bucket size in seconds; one frame per bucket |
| `--frame-duration` | `500` | Frame display time in ms (when `--total-duration` is not set) |
| `--total-duration` | — | Target total animation length in seconds; frames scale proportionally to real time gaps |
| `--fade-out` / `--no-fade-out` | off | Append a fade-out sequence at the end |
| `--fade-out-duration` | `1.0` | Duration of the fade-out in seconds |
| `--fade-out-frames` | 4 × duration | Number of fade frames; defaults to 4 per second |
| `--fade-out-color` | `auto` | Fade target: `auto` (black/white per mode), `transparent` (PNG/APNG only), CSS name, or hex |
| `--crf` | `23` | MP4 quality: 0 = lossless, 51 = worst. Ignored for APNG |
| `--codec` | `libx264` | MP4 codec: `libx264` (H.264) or `libx265` (H.265) |
| `--workers` | all CPU cores | Parallel render workers |
| `--log-scale` | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--size` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum directory depth |
| `--exclude` / `-e` | — | Pattern to exclude (repeatable): plain name, glob (``*.egg-info``), ``**`` glob, or relative path |
| `--colormap` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion` / `--no-cushion` | on | Van Wijk cushion shading |

---

## `dirplot git` — git history animation

Renders a git repository's commit history as an animated treemap. Each commit becomes one frame; changed tiles are highlighted.

> **Requires** `git` on `PATH`. `ffmpeg` is also required for MP4 output.

The `repo` argument accepts:
- Local path: `.`, `/path/to/repo`
- Local path with ref: `.@my-branch`, `.@v1.0`, `.@abc1234`
- GitHub URL: `github://owner/repo[@branch]` or `https://github.com/owner/repo[/tree/branch]`

For GitHub URLs, dirplot clones into a temporary directory (shallow when `--max-commits` or `--last` is set) and removes it on exit.

```bash
# Full git history as APNG or MP4
dirplot git . --output history.apng --animate --exclude .git
dirplot git . --output history.mp4 --animate
dirplot git . --output history.mp4 --animate --crf 18           # higher quality
dirplot git . --output history.mp4 --animate --codec libx265    # smaller file

# Specific local branch
dirplot git .@my-branch --output history.mp4 --animate

# Revision range with time-proportional frame durations
dirplot git . --output history.apng --animate \
  --range main~50..main --total-duration 30

# Specific revision range at fixed resolution
dirplot git /path/to/repo --output history.apng --animate \
  --range v1.0..HEAD --size 1920x1080 --exclude node_modules

# GitHub repo — no local clone needed
dirplot git github://owner/repo --output history.apng --animate --max-commits 100
dirplot git github://owner/repo@main --output history.apng --animate --max-commits 50

# Filter by time period
dirplot git . --output history.mp4 --animate --last 30d
dirplot git . --output history.mp4 --animate --last 24h
dirplot git github://owner/repo --output history.mp4 --animate --last 2w --max-commits 10

# Fade out to black at the end (animate only)
dirplot git . --output history.png --animate --fade-out
dirplot git . --output history.mp4 --animate --fade-out --fade-out-duration 2.0
dirplot git . --output history.png --animate --fade-out --fade-out-color transparent  # APNG/PNG only
dirplot git . --output history.mp4 --animate --fade-out --fade-out-color "#1a1a2e"
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | required | Output PNG, APNG, or MP4 |
| `--animate` / `--no-animate` | off | Build APNG or MP4; without this, each commit overwrites the output PNG |
| `--range` | all commits | Git revision range (e.g. `main~50..main`, `v1.0..HEAD`) |
| `--max-commits` | — | Cap the number of commits processed |
| `--last` | — | Time-period filter: `30d`, `24h`, `2w`, `1mo`, `30m`. Uses `--shallow-since` for GitHub URLs |
| `--frame-duration` | `1000` | Frame display time in ms (when `--total-duration` is not set) |
| `--total-duration` | — | Target total animation length in seconds; frames scale proportionally to real time gaps between commits |
| `--fade-out` / `--no-fade-out` | off | Append a fade-out sequence at the end (animate only) |
| `--fade-out-duration` | `1.0` | Duration of the fade-out in seconds |
| `--fade-out-frames` | 4 × duration | Number of fade frames; defaults to 4 per second |
| `--fade-out-color` | `auto` | Fade target: `auto` (black/white per mode), `transparent` (PNG/APNG only), CSS name, or hex |
| `--crf` | `23` | MP4 quality: 0 = lossless, 51 = worst. Ignored for APNG |
| `--codec` | `libx264` | MP4 codec: `libx264` (H.264) or `libx265` (~40% smaller at same quality) |
| `--workers` | all CPU cores | Parallel render workers; 4–8 is typically optimal |
| `--log-scale` | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--size` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum directory depth |
| `--exclude` / `-e` | — | Pattern to exclude (repeatable): plain name, glob (``*.egg-info``), ``**`` glob, or relative path |
| `--colormap` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion` / `--no-cushion` | on | Van Wijk cushion shading |
| `--github-token-file` | `$GITHUB_TOKEN` | File containing GitHub personal access token |

---

## `dirplot read-meta` — read embedded metadata

Reads dirplot metadata (date, software version, OS, Python version, executed command) embedded in a PNG, SVG, or MP4/MOV output file.

> **Requires** `ffprobe` on `PATH` (bundled with [ffmpeg](https://ffmpeg.org/)) to read metadata from `.mp4` / `.mov` files.

```bash
dirplot read-meta treemap.png
dirplot read-meta treemap.svg
dirplot read-meta history.mp4
dirplot read-meta a.png b.png c.svg   # multiple files
```

---

## `dirplot demo` — run example commands

Runs a curated set of example commands covering each subcommand and saves outputs to a folder. Useful for a first-time walkthrough or to verify that everything works in your environment.

```bash
# Run all examples with defaults (saves to ./demo/)
dirplot demo

# Custom output folder and repo
dirplot demo --output ~/dirplot-demo --github-url https://github.com/pallets/flask

# Step through commands one by one
dirplot demo --interactive
```

Examples produced:

| Output file | Command |
|---|---|
| *(stdout)* | `dirplot termsize` |
| `map-local.png` | `dirplot map .` (dark mode, PNG) |
| `map-github.png` | `dirplot map github://owner/repo` (dark mode, PNG) |
| `map-local.svg` | `dirplot map .` (light mode, SVG) |
| `git-static.png` | `dirplot git github://owner/repo --max-commits 5` (static PNG) |
| `git.mp4` | `dirplot git github://owner/repo --max-commits 10 --animate --total-duration 20` |
| `git-animated.png` | `dirplot git github://owner/repo --max-commits 10 --animate --total-duration 20 --fade-out` |
| *(stdout)* | `dirplot read-meta map-local.png` |

`dirplot watch` and `dirplot replay` are listed but skipped with an explanatory note — both require interactive or pre-recorded input.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--output` | `-o` | `demo` | Folder for generated output files |
| `--github-url` | | `https://github.com/deeplook/dirplot` | GitHub repository URL for remote examples |
| `--interactive` | `-i` | off | Ask for confirmation before each command is run |

---

## Running dirplot via Docker

Build the image once from the repo root:

```bash
docker build -t dirplot .
```

Then run any `dirplot` command inside the container. Since the container has no display, use `--output -` to stream the PNG to stdout and display it on the host.

**Save to a local file:**

```bash
docker run --rm -v "$PWD":/out dirplot dirplot map github://steipete/birdclaw \
  --output /out/birdclaw.png --no-show
open birdclaw.png
```

**Display inline (iTerm2 with `imgcat`):**

```bash
docker run --rm dirplot dirplot map github://steipete/birdclaw \
  --output - --no-show | imgcat
```

**Display inline (any iTerm2-compatible terminal, no extra tools):**

```bash
docker run --rm dirplot dirplot map github://steipete/birdclaw \
  --output - --no-show | python3 -c "
import sys, base64
data = sys.stdin.buffer.read()
sys.stdout.buffer.write(
    b'\033]1337;File=inline=1;size=' + str(len(data)).encode()
    + b':' + base64.b64encode(data) + b'\a\n'
)
"
```

> **Note:** `--inline` does not work when running inside a container — dirplot cannot probe your host terminal from within Docker. Use `--output -` and display the bytes on the host side instead, as shown above.

---

## Inline terminal display

The `--inline` flag renders the image directly in the terminal. The protocol is auto-detected at runtime.

| Terminal | Platform | Protocol |
|---|---|---|
| [iTerm2](https://iterm2.com/) | macOS | iTerm2 |
| [WezTerm](https://wezfurlong.org/wezterm/) | macOS, Linux, Windows | Kitty & iTerm2 |
| [Warp](https://www.warp.dev/) | macOS, Linux | iTerm2 |
| [Hyper](https://hyper.is/) | macOS, Linux, Windows | iTerm2 |
| [Kitty](https://sw.kovidgoyal.net/kitty/) | macOS, Linux | Kitty |
| [Ghostty](https://ghostty.org/) | macOS, Linux | Kitty |

The default `--show` mode opens the image in the system viewer (`open` on macOS, `xdg-open` on Linux) and works in any terminal.

> **Windows:** Common shells and terminal emulators (PowerShell, cmd, Windows Terminal) do not support inline image protocols. [WezTerm](https://wezfurlong.org/wezterm/) is currently the only mainstream Windows terminal with support (Kitty protocol). WSL2 is treated as Linux and has full support.

> **AI coding assistants:** `--inline` does not work in Claude Code, Cursor, or GitHub Copilot Chat — these tools intercept terminal output as plain text. Use `--show` or `--output` instead.

> **Tip:** In supported terminals, the rendered image can often be dragged directly out of the terminal window into another application.
