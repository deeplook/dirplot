# CLI Reference

← [Home](index.md)

- [dirplot map](#dirplot-map-treemap-for-any-directory-tree)
- [dirplot diff](#dirplot-diff-compare-two-directory-trees)
- [dirplot git](#dirplot-git-git-history-treemap)
- [dirplot hg](#dirplot-hg-mercurial-history-treemap)
- [dirplot watch](#dirplot-watch-live-watch-mode)
- [dirplot replay](#dirplot-replay-event-log-replay)
- [dirplot metrics](#dirplot-metrics-directory-metrics)
- [dirplot meta](#dirplot-meta-read-embedded-metadata)
- [dirplot demo](#dirplot-demo-run-example-commands)
- [dirplot overview](#dirplot-overview-command-overview)
- [dirplot termsize](#dirplot-termsize-terminal-size)

---

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

# Focus on named subtrees (keeps only these paths; repeatable)
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

# Custom canvas size, colormap, font
dirplot map . --canvas 1920x1080 --output treemap.png --no-show
dirplot map . --colormap Set2 --font-size 18

# Filter by file size — only show files in a given size range
dirplot map . --size 10K..1M           # between 10 KiB and 1 MiB
dirplot map . --size 500K..            # 500 KiB or larger
dirplot map . --size ..100K            # 100 KiB or smaller
dirplot map . --size 1M --size ..1K    # exactly 1 MiB or under 1 KiB (OR logic)

# Log scale — use when one large file dominates and squashes everything else
dirplot map . --log-scale 4

# Highlight specific files or folders with coloured borders
dirplot map . --highlight "src/main.py"                   # single file, red (default)
dirplot map . --highlight "**/*.py@orange"                # all Python files in orange
dirplot map . --highlight "src@orange" --highlight "**/*.md@cyan"  # folder + glob

# Interactive SVG output (hover highlight + floating tooltip)
dirplot map . --output treemap.svg

# Pipe PNG bytes to stdout
dirplot map . --output - | convert - -resize 50% small.png
dirplot map . --output - --format svg > treemap.svg

# Archive files — no unpacking needed
dirplot map project.zip
dirplot map release.tar.gz --depth 2

# Remote sources
dirplot map ssh://alice@prod.example.com/var/www
dirplot map s3://noaa-ghcn-pds --no-sign
dirplot map github://pallets/flask
dirplot map github://torvalds/linux@v6.12/Documentation
dirplot map gdrive://                           # Google Drive root (requires gog)
dirplot map gdrive://FOLDER_ID                  # specific Drive folder
dirplot map docker://my-container:/app
dirplot map pod://my-pod:/app
```

See [EXAMPLES.md](examples.md) for detailed examples of each remote backend and git history animation.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--paths-from` | | — | File with path list (`tree`/`find` output); `-` for stdin |
| `--output` | `-o` | — | Save to this path (PNG or SVG); `-` for stdout |
| `--format` | `-f` | auto | Output format: `png` or `svg` |
| `--show/--no-show` | | `--show` | Display the image after rendering; SVG saved with `-o` defaults to `--no-show` (`--output -` also implies `--no-show`) |
| `--inline` | | off | Display in terminal (auto-detected protocol; PNG only) — see [Inline terminal display](guides.md#inline-terminal-display) |
| `--legend [N]` | | off | File-count legend; `N` = max entries (default: 20) |
| `--font-size` | | `12` | Directory label font size in pixels |
| `--colormap` | | `tab20` | Matplotlib colormap for unknown extensions |
| `--exclude` | `-e` | — | Pattern to exclude (repeatable): plain name, glob (`*.egg-info`), `**` glob, or relative path |
| `--include` | | — | Keep only these subtrees (repeatable, supports nested paths); the inverse of `--exclude` |
| `--highlight` | `-H` | — | Draw a coloured border around matching paths (repeatable). Accepts exact paths or globs including `**`. Append `@color` to set the colour (e.g. `**/*.py@orange`); defaults to red. Works for files and directories |
| `--depth` | | unlimited | Maximum recursion depth |
| `--size` | `-S` | — | Filter files by size range (e.g. `10M..500M`, `100M..`, `..50K`, `1G`). Repeatable — multiple values combine with OR logic. Units: `B K KB M MB G GB T TB` (powers of 1024, case-insensitive) |
| `--keep-empty-dirs` | | off | Retain directories that become empty after `--size` filtering |
| `--canvas` | | terminal size | Output dimensions as `WIDTHxHEIGHT` (e.g. `1920x1080`) |
| `--header/--no-header` | | `--header` | Print info lines before rendering |
| `--cushion/--no-cushion` | | `--cushion` | Van Wijk cushion shading for a raised 3-D look |
| `--log-scale` | | `0` (off) | Log-scale compression ratio; any value > 1 enables it (e.g. `4` = largest tile is at most 4× the smallest) |
| `--breadcrumbs/--no-breadcrumbs` | | `--breadcrumbs` | Collapse single-child chains into `foo / bar / baz` labels |
| `--metrics/--no-metrics` | | off | Print detailed metrics after scanning (same output as `dirplot metrics`) |
| `--password-file` | | — | File containing archive password; prompted interactively if not supplied |
| `--github-token-file` | | `$GITHUB_TOKEN` | File containing GitHub personal access token |
| `--ssh-key` | | — | SSH private key path |
| `--ssh-password-file` | | — | File containing SSH password |
| `--aws-profile` | | `$AWS_PROFILE` | Named AWS profile |
| `--no-sign` | | off | Anonymous access for public S3 buckets |

---

## `dirplot diff` — compare two directory trees

Compares two directory trees A and B as a treemap. Tiles are sized by B (the new tree). Colour-coded borders indicate the diff status of each file: **green** = added (present in B, absent in A), **red** = removed (present in A, absent in B), **blue** = changed (present in both, but content differs). Unchanged files have no border. By default, unchanged files are included as context (`--context`); pass `--changed-only` to show only changed, added, and removed files.

A and B can be **any source supported by `dirplot map`** — local directories, GitHub repos, archives, S3 paths, SSH hosts, Docker containers, or Kubernetes pods.

**When a source is a local git or hg repository**, only tracked files are scanned (equivalent to `git diff` / `hg diff` semantics — untracked files are ignored). Change detection uses blob hash comparison, not file size, so edits that don't change file size are caught correctly. Git LFS files are handled transparently.

**Single-argument shorthand** — pass only one argument to diff the working tree against HEAD (git) or tip (hg):

```bash
dirplot diff .                  # uncommitted changes in current repo
dirplot diff /path/to/repo      # uncommitted changes in that repo
```

**`@ref` syntax** — append `@<ref>` to any local path or GitHub URL to pin it to a specific commit, tag, or branch:

```bash
dirplot diff .@HEAD~5 .@HEAD           # last 5 commits
dirplot diff .@abc1234 .@def5678       # two specific SHAs
dirplot diff .@v1.0 .@v2.0             # two tags
dirplot diff github://owner/repo@v1.0 github://owner/repo@v2.0   # GitHub tags
```

```bash
# Basic comparison — open in system viewer
dirplot diff old/ new/

# Uncommitted changes, only show changed files
dirplot diff . --changed-only

# Compare an S3 prefix against a local directory
dirplot diff s3://my-bucket/v1 ./v2

# Save to file
dirplot diff old/ new/ --output diff.png --no-show

# Light mode, SVG output
dirplot diff old/ new/ --light --output diff.svg
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--output` | `-o` | — | Save to this path (PNG or SVG); `-` for stdout |
| `--format` | `-f` | auto | Output format: `png` or `svg` |
| `--show/--no-show` | | `--show` | Display the image after rendering; SVG saved with `-o` defaults to `--no-show` (`--output -` also implies `--no-show`) |
| `--inline` | | off | Display in terminal (auto-detected protocol; PNG only) |
| `--context/--changed-only` | | `--context` | Include unchanged files in the treemap |
| `--font-size` | | `12` | Directory label font size in pixels |
| `--colormap` | | `tab20` | Colormap for unknown extensions |
| `--exclude` | `-e` | — | Pattern to exclude (repeatable): plain name, glob (`*.egg-info`), `**` glob, or relative path |
| `--include` | | — | Keep only these subtrees (repeatable); the inverse of `--exclude`. The added/removed/changed summary counts in the header are scoped to the included paths |
| `--highlight` | `-H` | — | Draw a coloured border on top of diff borders (repeatable). Same `pattern[@color]` syntax as `dirplot map --highlight` |
| `--depth` | | unlimited | Maximum recursion depth |
| `--size` | `-S` | — | Filter files by size range (e.g. `10M..500M`, `100M..`, `..50K`, `1G`). Repeatable — multiple values combine with OR logic |
| `--keep-empty-dirs` | | off | Retain directories that become empty after `--size` filtering |
| `--canvas` | | terminal size | Output dimensions as `WIDTHxHEIGHT` (e.g. `1920x1080`) |
| `--cushion/--no-cushion` | | `--cushion` | Van Wijk cushion shading for a raised 3-D look |
| `--dark/--light` | | `--dark` | Canvas and label colour scheme |
| `--log-scale` | | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--header/--no-header` | | `--header` | Print info lines before rendering |
| `--quiet` | | off | Suppress all status output |
| `--ssh-key` | | — | SSH private key file |
| `--ssh-password-file` | | — | File containing SSH password |
| `--aws-profile` | | `$AWS_PROFILE` | Named AWS profile for S3 access |
| `--no-sign` | | off | Anonymous access for public S3 buckets |
| `--github-token-file` | | `$GITHUB_TOKEN` | File containing GitHub personal access token |
| `--k8s-namespace` | | — | Kubernetes namespace |
| `--k8s-container` | | — | Container name for multi-container pods |
| `--password-file` | | — | File containing archive password |
| `--no-input` | | off | Fail instead of prompting for passwords |

---

## `dirplot git` — git history treemap

Renders a single commit or an animated history of a git repository as a treemap. Without `--range` or `--period`, a single PNG of the last commit (HEAD or the given ref) is produced. With `--range` or `--period`, an animated APNG or MP4 is produced — one frame per commit.

> **Requires** `git` on `PATH`. `ffmpeg` is also required for MP4 output.

The `repo` argument accepts:

| Form | Example |
|---|---|
| Local path | `.`, `/path/to/repo` |
| Local path with ref | `.@my-branch`, `.@v1.0`, `.@abc1234` |
| `github://` URL | `github://owner/repo`, `github://owner/repo@branch` |
| HTTPS GitHub URL | `https://github.com/owner/repo`, `https://github.com/owner/repo@v1.0` |
| HTTPS GitHub tree URL | `https://github.com/owner/repo/tree/branch` |

For GitHub URLs, dirplot clones into a temporary directory (shallow when possible) and removes it on exit.

**Single frame** (no `--range` or `--period`):

```bash
# Snapshot of HEAD
dirplot git . --output snapshot.png

# Specific local branch or tag
dirplot git .@my-branch --output branch.png
dirplot git .@v1.0 --output v1.png --inline

# GitHub repo at a specific tag — display inline
dirplot git https://github.com/owner/repo@v1.0 --inline
dirplot git github://owner/repo@v1.0 --inline
```

**Animation** (`--range` or `--period` triggers multi-frame output):

A bare branch or tag name (`--range main`) animates **all** commits on that branch.
The `A..B` syntax animates only commits reachable from B but not from A (standard git range).

```bash
# All commits on main → animated PNG
dirplot git . --range main --output history.png

# All commits on main, time-proportional frame durations
dirplot git . --range main --total-duration 30 --output history.png

# Only the last 50 commits on main
dirplot git . --range main --last 50 --output history.png

# Specific revision range → animated PNG
dirplot git . --range main~50..main --output history.png

# Tagged release range
dirplot git . --range v1.0..v2.0 --output release.mp4

# First 10 commits of a range
dirplot git github://owner/repo --range v1.0..v2.0 --first 10 --output history.png

# Last 10 commits of a range
dirplot git github://owner/repo --range v1.0..v2.0 --last 10 --output history.png

# All commits in the last 30 days
dirplot git . --period 30d --output history.mp4

# Commits in a branch that fall within the last 3 days of that branch's history
dirplot git github://owner/repo --range main --period 3d --output history.png

# Fade out to black at the end
dirplot git . --period 7d --total-duration 20 \
  --fade-out --fade-out-duration 2.0 --output history.mp4
```

See [EXAMPLES.md — Git History Animation](examples.md#git-history-animation) for more examples including video output.

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | — | Output file: `.png` (static or animated APNG) or `.mp4` / `.mov`. Required unless `--inline` is given |
| `--inline` | off | Render and display the image directly in the terminal (single-frame mode only; not compatible with `--range` or `--period`) |
| `--range` | — | Git revision range. A bare branch/tag name (e.g. `main`) animates all commits on it; `A..B` animates commits in B but not A. Triggers animation mode |
| `--period` | — | Relative time filter: `30d`, `24h`, `2w`, `1mo`, `30m`. Triggers animation mode. Without `--range`, filters from now; with `--range`, filters relative to the range end |
| `--first` / `--last` | — | After applying `--range` / `--period`, keep only the first or last N commits |
| `--frame-duration` | `1000` | Frame display time in ms (when `--total-duration` is not set) |
| `--total-duration` | — | Target total animation length in seconds; frames scale proportionally to real time gaps between commits |
| `--fade-out` / `--no-fade-out` | off | Append a fade-out sequence at the end (animation mode only) |
| `--fade-out-duration` | `1.0` | Duration of the fade-out in seconds |
| `--fade-out-frames` | 4 × duration | Number of fade frames; defaults to 4 per second |
| `--fade-out-color` | `auto` | Fade target: `auto` (black/white per mode), `transparent` (PNG/APNG only), CSS name, or hex |
| `--crf` | `23` | MP4 quality: 0 = lossless, 51 = worst. Ignored for APNG |
| `--codec` | `libx264` | MP4 codec: `libx264` (H.264) or `libx265` (~40% smaller at same quality) |
| `--workers` | all CPU cores | Parallel render workers; must be a positive integer. 4–8 is typically optimal |
| `--log-scale` | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--canvas` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum directory depth |
| `--exclude` / `-e` | — | Pattern to exclude (repeatable): plain name, glob (`*.egg-info`), `**` glob, or relative path |
| `--highlight` / `-H` | — | Draw a coloured border on matching paths in every frame (repeatable). Same `pattern[@color]` syntax as `dirplot map --highlight` |
| `--colormap` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion/--no-cushion` | `--cushion` | Van Wijk cushion shading |
| `--github-token-file` | `$GITHUB_TOKEN` | File containing GitHub personal access token |

---

## `dirplot hg` — Mercurial history treemap

Renders a single changeset or an animated history of a Mercurial repository as a treemap. Without `--range` or `--period`, a single PNG of the tip (or the given rev) is produced. With `--range` or `--period`, an animated APNG or MP4 is produced — one frame per changeset.

> **Requires** `hg` on `PATH`. `ffmpeg` is also required for MP4 output.

The `repo` argument accepts a local path (`.`, `/path/to/repo`) optionally followed by `@rev` to pin to a specific revision or tag (e.g. `.@tip`, `.@1.0`, `.@abc1234`).

**Single frame** (no `--range` or `--period`):

```bash
# Snapshot of tip
dirplot hg . --output snapshot.png

# Specific revision or tag
dirplot hg .@tip --output tip.png
dirplot hg .@1.0 --inline
```

**Animation** (`--range` triggers multi-frame output):

```bash
# Full history as animated PNG
dirplot hg . --range 0:tip --output history.png

# Revision range
dirplot hg . --range 10:tip --output history.mp4

# First 20 changesets of a range
dirplot hg . --range 0:tip --first 20 --output history.png
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | — | Output file: `.png` (static or animated APNG) or `.mp4` / `.mov`. Required unless `--inline` is given |
| `--inline` | off | Render and display the image directly in the terminal (single-frame mode only; not compatible with `--range`) |
| `--range` | — | Mercurial revision range (e.g. `0:tip`, `10:tip`). Triggers animation mode |
| `--period` | — | Relative time filter: `30d`, `24h`, `2w`, `1mo`, `30m`. Triggers animation mode |
| `--first` / `--last` | — | After applying `--range` / `--period`, keep only the first or last N changesets |
| `--frame-duration` | `1000` | Frame display time in ms (when `--total-duration` is not set) |
| `--total-duration` | — | Target total animation length in seconds |
| `--fade-out` / `--no-fade-out` | off | Append a fade-out sequence at the end (animation mode only) |
| `--fade-out-duration` | `1.0` | Duration of the fade-out in seconds |
| `--fade-out-frames` | 4 × duration | Number of fade frames; defaults to 4 per second |
| `--fade-out-color` | `auto` | Fade target: `auto` (black/white per mode), `transparent` (PNG/APNG only), CSS name, or hex |
| `--crf` | `23` | MP4 quality: 0 = lossless, 51 = worst. Ignored for APNG |
| `--codec` | `libx264` | MP4 codec: `libx264` (H.264) or `libx265` (~40% smaller at same quality) |
| `--workers` | all CPU cores | Parallel render workers; must be a positive integer |
| `--log-scale` | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--canvas` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum directory depth |
| `--exclude` / `-e` | — | Pattern to exclude (repeatable) |
| `--highlight` / `-H` | — | Draw a coloured border on matching paths in every frame (repeatable). Same `pattern[@color]` syntax as `dirplot map --highlight` |
| `--colormap` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion/--no-cushion` | `--cushion` | Van Wijk cushion shading |

---

## `dirplot watch` — live watch mode

Records filesystem events as JSONL for later replay as an animated treemap. Use `dirplot replay` to turn the recording into an APNG or MP4. Pass `--snapshot` to also write a live PNG/SVG on each change — best for small trees only, as rendering adds latency.

```bash
# Record events to a JSONL file (primary use case)
dirplot watch src --output events.jsonl

# Watch multiple directories
dirplot watch src tests --output events.jsonl

# Append to an existing log instead of truncating
dirplot watch src --output events.jsonl --append

# Also write a live snapshot PNG on each change (small trees only)
dirplot watch . --output events.jsonl --snapshot treemap.png

# Snapshot only, no event log
dirplot watch . --snapshot treemap.png --debounce 1.0
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` / `-o` | — | Write filesystem events as JSONL to this file, flushed after each regeneration. Use with `dirplot replay` to produce an animation |
| `--append/--no-append` | off | Append to an existing `--output` file instead of truncating on startup |
| `--snapshot` | — | Also write the current treemap as a PNG or SVG on each change (best for small trees) |
| `--debounce` | `0.5` | Seconds of quiet before regenerating; `0` disables |
| `--log-scale` | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--size` / `-S` | — | Filter files by size range (e.g. `10M..500M`, `100M..`, `..50K`). Repeatable (OR logic) |
| `--keep-empty-dirs` | off | Retain directories emptied by `--size` filtering |
| `--canvas` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum recursion depth |
| `--include` | — | Show only this subtree (repeatable). Allowlist complement to `--exclude` |
| `--exclude` / `-e` | — | Pattern to exclude (repeatable): plain name, glob (`*.egg-info`), `**` glob, or relative path |
| `--highlight` / `-H` | — | Highlight matching paths with a coloured border (repeatable); append `@color` to set colour |
| `--colormap` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion/--no-cushion` | `--cushion` | Van Wijk cushion shading |

---

## `dirplot replay` — event log replay

Replays a JSONL event log produced by `dirplot watch --output` as an animated treemap. Events are grouped into time buckets (one frame per bucket). By default the full directory tree is scanned at replay time so unchanged files appear as context; pass `--changed-only` to show only files that appear in the event log.

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
| `--workers` | all CPU cores | Parallel render workers; must be a positive integer |
| `--log-scale` | `0` (off) | Log-scale compression ratio; any value > 1 enables it |
| `--size` / `-S` | — | Filter files by size range (e.g. `10M..500M`, `100M..`, `..50K`). Repeatable (OR logic). Frames with no matching files are skipped |
| `--canvas` | terminal size | Output dimensions as `WIDTHxHEIGHT` |
| `--depth` | — | Maximum directory depth |
| `--exclude` / `-e` | — | Pattern to exclude (repeatable): plain name, glob (`*.egg-info`), `**` glob, or relative path |
| `--highlight` / `-H` | — | Draw a coloured border on matching paths in every frame (repeatable). Same `pattern[@color]` syntax as `dirplot map --highlight` |
| `--colormap` | `tab20` | Matplotlib colormap |
| `--font-size` | `12` | Directory label font size in pixels |
| `--cushion/--no-cushion` | `--cushion` | Van Wijk cushion shading |
| `--changed-only` | off | Show only files from the event log; skip the initial directory scan |

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
  Depth:      7          ← maximum nesting level in the tree
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
| `--exclude` | `-e` | — | Pattern to exclude (repeatable): plain name, glob (`*.egg-info`), `**` glob, or relative path |
| `--include` | | — | Keep only these subtrees (repeatable); the inverse of `--exclude` |
| `--depth` | | unlimited | Maximum recursion depth |
| `--paths-from` | | — | File with path list (`tree`/`find` output); `-` for stdin |
| `--password-file` | | — | File containing archive password; prompted interactively if needed |
| `--github-token-file` | | `$GITHUB_TOKEN` | File containing GitHub personal access token |
| `--ssh-key` | | — | SSH private key path |
| `--ssh-password-file` | | — | File containing SSH password |
| `--aws-profile` | | `$AWS_PROFILE` | Named AWS profile |
| `--no-sign` | | off | Anonymous access for public S3 buckets |
| `--k8s-namespace` | | — | Kubernetes namespace |
| `--k8s-container` | | — | Container name for multi-container pods |

---

## `dirplot meta` — read embedded metadata

Reads dirplot metadata (date, software version, OS, Python version, executed command) embedded in a PNG, SVG, or MP4/MOV output file.

> **Requires** `ffprobe` on `PATH` (bundled with [ffmpeg](https://ffmpeg.org/)) to read metadata from `.mp4` / `.mov` files.

```bash
dirplot meta treemap.png
dirplot meta treemap.svg
dirplot meta history.mp4
dirplot meta a.png b.png c.svg   # multiple files
dirplot meta --json treemap.png  # structured JSON output
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--json` | off | Output metadata as structured JSON |

When `--json` is used, each file produces an object with: `file`, `has_metadata`, `created`, `version`, `command`, `os`, `python`. Multiple files return a JSON array.

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
| `map-highlight.png` | `dirplot map tests --highlight "tests/conftest.py@red" --highlight "**/test_git*.py@cyan" --highlight "tests/fixtures@lime"` |
| `map-github.png` | `dirplot map github://owner/repo` (dark mode, PNG) |
| `map-local.svg` | `dirplot map .` (light mode, SVG) |
| `git-static.png` | `dirplot git github://owner/repo --first 1` (static PNG of latest commit) |
| `git.mp4` | `dirplot git github://owner/repo --range main --first 10 --total-duration 20` |
| `git-animated.png` | `dirplot git github://owner/repo --range main --first 10 --total-duration 20 --fade-out` |
| *(stdout)* | `dirplot meta map-local.png` |

`dirplot watch` and `dirplot replay` are listed but skipped with an explanatory note — both require interactive or pre-recorded input.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--output` | `-o` | `demo` | Folder for generated output files |
| `--github-url` | | `https://github.com/deeplook/dirplot` | GitHub repository URL for remote examples |
| `--interactive` | `-i` | off | Ask for confirmation before each command is run |

---

## `dirplot overview` — command overview

Prints a structured overview of all commands, their arguments, options, and default values. Useful as a quick reference without leaving the terminal.

```bash
dirplot overview
```

There are no options beyond `--help`.

---

## `dirplot termsize` — terminal size

Shows the current terminal size in characters and pixels. Run this before `dirplot map` to check what canvas size dirplot will use by default.

```bash
dirplot termsize
```

Example output:

```
Characters : 160 cols × 45 rows
Pixels     : 1280 × 720
```

There are no options beyond `--help`.

---
