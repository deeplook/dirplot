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

# Exclude paths
dirplot map . --exclude .venv --exclude .git

# Focus on named subtrees
dirplot map . --subtree src --subtree tests
dirplot map . --subtree src/dirplot/fonts

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
dirplot map . --log

# Disable cushion shading
dirplot map . --no-cushion

# Show a file-count legend
dirplot map . --legend           # up to 20 entries
dirplot map . --legend 10        # cap at 10

# Disable breadcrumb collapsing
dirplot map . -B

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
| `--colormap` | `-c` | `tab20` | Matplotlib colormap for unknown extensions |
| `--exclude` | `-e` | — | Path to exclude (repeatable) |
| `--subtree` | `-s` | — | Show only this named subtree (repeatable); supports nested paths |
| `--depth` | | unlimited | Maximum recursion depth |
| `--size` | | terminal size | Output dimensions as `WIDTHxHEIGHT` (e.g. `1920x1080`) |
| `--header/--no-header` | | `--header` | Print info lines before rendering |
| `--cushion/--no-cushion` | | `--cushion` | Van Wijk cushion shading for a raised 3-D look |
| `--log/--no-log` | | `--no-log` | Log scale for file sizes; useful when one large file dominates the layout |
| `--breadcrumbs/--no-breadcrumbs` | `-b`/`-B` | `--breadcrumbs` | Collapse single-child chains into `foo / bar / baz` labels |
| `--password` | | — | Archive password; prompted interactively if not supplied |
| `--github-token` | | `$GITHUB_TOKEN` | GitHub personal access token |
| `--ssh-key` | | `~/.ssh/id_rsa` | SSH private key path |
| `--aws-profile` | | `$AWS_PROFILE` | Named AWS profile |
| `--no-sign` | | off | Anonymous access for public S3 buckets |

---

## `dirplot watch` — live watch mode

Monitors directories and regenerates the treemap on every change. With `--animate`, each debounced render becomes one frame; the complete APNG or MP4 is written on Ctrl-C.

```bash
# Watch and regenerate on every change
dirplot watch . --output treemap.png

# Watch multiple directories
dirplot watch src tests --output treemap.png

# Adjust debounce (default 0.5 s)
dirplot watch . --output treemap.png --debounce 1.0
dirplot watch . --output treemap.png --debounce 0   # immediate

# Log all events to a JSONL file
dirplot watch src --output treemap.png --event-log events.jsonl

# Animated APNG or MP4 — one frame per debounced render, written on Ctrl-C
dirplot watch . --output treemap.png --animate
dirplot watch . --output treemap.mp4 --animate
dirplot watch . --output treemap.mp4 --animate --crf 18         # higher quality
dirplot watch . --output treemap.mp4 --animate --codec libx265  # smaller file
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | required | Output file (`.png`, `.apng`, `.mp4`) |
| `--debounce` | `0.5` | Seconds of quiet before regenerating; `0` disables |
| `--event-log` | — | Write raw events as JSONL on Ctrl-C exit |
| `--animate` / `--no-animate` | off | Capture frames and write APNG or MP4 on Ctrl-C |
| `--crf` | `23` | MP4 quality: 0 = lossless, 51 = worst. Ignored for APNG |
| `--codec` | `libx264` | MP4 codec: `libx264` (H.264) or `libx265` (H.265) |
| `--log` / `--no-log` | off | Log scale for file sizes |
| `--size` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum recursion depth |
| `--exclude` / `-e` | — | Path to exclude (repeatable) |
| `--colormap` / `-c` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion` / `--no-cushion` | on | Van Wijk cushion shading |

---

## `dirplot replay` — event log replay

Replays a JSONL event log produced by `dirplot watch --event-log` as an animated treemap. Events are grouped into time buckets (one frame per bucket).

```bash
# Replay as APNG (60-second buckets, 30-second total)
dirplot replay events.jsonl --output replay.apng --total-duration 30

# Replay as MP4
dirplot replay events.jsonl --output replay.mp4 --total-duration 30
dirplot replay events.jsonl --output replay.mp4 --crf 18         # higher quality
dirplot replay events.jsonl --output replay.mp4 --codec libx265  # smaller file

# Fine-grained buckets with fixed frame duration
dirplot replay events.jsonl --output replay.apng --bucket 10 --frame-duration 200
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | required | Output `.apng` or `.mp4` |
| `--bucket` | `60.0` | Time bucket size in seconds; one frame per bucket |
| `--frame-duration` | `500` | Frame display time in ms (when `--total-duration` is not set) |
| `--total-duration` | — | Target total animation length in seconds; frames scale proportionally to real time gaps |
| `--crf` | `23` | MP4 quality: 0 = lossless, 51 = worst. Ignored for APNG |
| `--codec` | `libx264` | MP4 codec: `libx264` (H.264) or `libx265` (H.265) |
| `--workers` / `-w` | all CPU cores | Parallel render workers |
| `--log` / `--no-log` | off | Log scale for file sizes |
| `--size` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum directory depth |
| `--exclude` / `-e` | — | Path to exclude (repeatable) |
| `--colormap` / `-c` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion` / `--no-cushion` | on | Van Wijk cushion shading |

---

## `dirplot git` — git history animation

Renders a git repository's commit history as an animated treemap. Each commit becomes one frame; changed tiles are highlighted.

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
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | required | Output PNG, APNG, or MP4 |
| `--animate` / `--no-animate` | off | Build APNG or MP4; without this, each commit overwrites the output PNG |
| `--range` / `-r` | all commits | Git revision range (e.g. `main~50..main`, `v1.0..HEAD`) |
| `--max-commits` / `-n` | — | Cap the number of commits processed |
| `--last` | — | Time-period filter: `30d`, `24h`, `2w`, `1mo`, `30m`. Uses `--shallow-since` for GitHub URLs |
| `--frame-duration` | `1000` | Frame display time in ms (when `--total-duration` is not set) |
| `--total-duration` | — | Target total animation length in seconds; frames scale proportionally to real time gaps between commits |
| `--crf` | `23` | MP4 quality: 0 = lossless, 51 = worst. Ignored for APNG |
| `--codec` | `libx264` | MP4 codec: `libx264` (H.264) or `libx265` (~40% smaller at same quality) |
| `--workers` / `-w` | all CPU cores | Parallel render workers; 4–8 is typically optimal |
| `--log` / `--no-log` | off | Log scale for file sizes |
| `--size` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum directory depth |
| `--exclude` / `-e` | — | Path to exclude (repeatable) |
| `--colormap` / `-c` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion` / `--no-cushion` | on | Van Wijk cushion shading |
| `--github-token` | `$GITHUB_TOKEN` | GitHub personal access token |

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
| `git.png` | `dirplot git github://owner/repo --max-commits 5` (static PNG) |
| `git.mp4` | `dirplot git github://owner/repo --max-commits 10 --animate --total-duration 20` |
| *(stdout)* | `dirplot read-meta map-local.png` |

`dirplot watch` and `dirplot replay` are listed but skipped with an explanatory note — both require interactive or pre-recorded input.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--output` | `-o` | `demo` | Folder for generated output files |
| `--github-url` | | `https://github.com/deeplook/dirplot` | GitHub repository URL for remote examples |
| `--interactive` | `-i` | off | Ask for confirmation before each command is run |

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
