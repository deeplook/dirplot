# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Manual reload and auto-reload controls in `serve`** — the web UI gained a toolbar **Reload**
  button that rescans the source and updates the treemap in place (preserving the current zoom and
  without touching the sidebar). A new **Auto-reload** toggle in the Settings tab connects or
  disconnects the live-update WebSocket at runtime, and a `--watch/--no-watch` flag sets its initial
  state (default: on). Auto-reload works for local sources; remote/read-only sources fall back to
  the manual Reload button.

- **Multiple archive roots for `map`, `diff`, and other commands** — passing two or more archive
  files (zip, tar, 7z, etc.) as positional arguments now works, e.g.
  `dirplot map foo.zip bar.zip`. Each archive is scanned independently and the results are combined
  under a synthetic common-parent node, matching the behaviour already supported for multiple local
  directory/file arguments.

## [0.6.0] - 2026-06-09

### Added

- **`dirplot serve` — interactive web treemap (experimental, undocumented)** — new command that
  starts a local FastAPI server and opens a D3.js treemap in the browser. This feature is still
  under active development; the interface and API are subject to change in future releases, and
  full documentation is forthcoming. Features include: zoomable tiles, breadcrumb navigation,
  keyword and regex search, keyboard navigation (j/k, Enter, /, Esc), a sidebar with Settings,
  Metrics, and Preview tabs, and instant (no Apply button) settings changes.

- **File preview in `serve`** — the Preview tab renders syntax-highlighted source files (10 paired
  dark/light code themes), PDF documents via iframe, a hex dump for binary files, and image/video
  previews with embedded dirplot metadata. HEIC images are supported via `pillow-heif` or the
  macOS `sips` fallback.

- **Source input and history in `serve`** — a toolbar text field accepts any source supported by
  `dirplot` (local path, archive, GitHub URL, Docker, K8s, S3). Previous sources are tracked in a
  history dropdown.

- **HTTP(S) URL archive sources** — `dirplot` now accepts `https://` and `http://` URLs pointing
  to archive files (zip, tar, etc.) as a source in any command. Downloads are capped at 100 MB.

- **Docker, Kubernetes, and S3 as first-class sources** — `docker://`, `k8s://`, and `s3://`
  schemes are now registered in the global source registry, making them available wherever a
  source path is accepted.

## [0.5.1] - 2026-05-28

### Fixed

- **`click` declared as an explicit dependency** — `dirplot` imports `click` directly in
  `_overview.py`, but relied on it being pulled in transitively by `typer`. Starting around
  typer 0.12, click became optional in some typer builds, causing `ModuleNotFoundError: No module
  named 'click'` when running the installed tool under Python 3.14. `click>=8.0` is now a direct
  dependency.

### Added

- **SVG snapshot output for `git` and `hg`** — both commands now accept `--output file.svg` for
  single-frame snapshots, producing an interactive SVG (hover tooltips, CSS highlight) identical to
  `map`'s SVG output. Animation output (APNG/MP4) is unchanged and still requires `.png`/`.mp4`/`.mov`.

- **Remote URL support for `hg`** — `dirplot hg` now accepts `https://`, `http://`, and `ssh://`
  URLs directly (e.g. `dirplot hg https://hg.reportlab.com/hg-public/reportlab --inline`). The
  repository is cloned into a temporary directory automatically, mirroring the GitHub URL support
  already available in `dirplot git`.

## [0.5.0] - 2026-05-20

### Documentation

- Documentation greatly expanded: new dedicated pages for Installation, Examples, Remote Sources, Guides, and Troubleshooting; richer use-case descriptions; API page updated with tested code snippets; CLI reference reordered to match `dirplot -h`.

### Changed

- **`read-meta` renamed to `meta`** — `dirplot read-meta` is now `dirplot meta`. The new command
  also gains a `--json` flag that outputs structured JSON with fields `file`, `has_metadata`,
  `created`, `version`, `command`, `os`, and `python`. Multiple files return a JSON array.
  Human-readable output now uses friendlier labels (`Created:`, `Version:` instead of `Date:`,
  `Software:`). **Breaking change.**

- **`--size` renamed to `--canvas`** in `map`, `diff`, `watch`, `git`, `hg`, and `replay` — the
  old flag controlled output pixel dimensions (e.g. `--canvas 1920x1080`). The name was freed up
  so that `--size` can be used for file-size filtering (see below). **Breaking change.**

### Added

- **`--size`/`-S` file-size filter** — available on `map`, `diff`, `watch`, and `replay`. Filters the
  scanned tree to files whose byte size matches a range. Syntax: `10M..500M` (between 10 MiB and
  500 MiB), `100M..` (≥ 100 MiB), `..50K` (≤ 50 KiB), `1G` (exactly 1 GiB). Units: `B K KB M
  MB G GB T TB` (powers of 1024, case-insensitive). Repeatable — multiple `--size` flags combine
  with OR logic. Pass `--keep-empty-dirs` to retain directories that become empty after filtering.
  Filtering is post-scan; parent directory sizes are recalculated after pruning.

### Fixed

- Several correctness and robustness fixes: archive stat modes now include file type bits; watch mode SVG snapshots now render change highlights; `diff` summary counts respect `--include`; `--workers` rejects non-positive values; the `watch_events.py` script ignores its own output file when placed inside a watched directory; GitHub tokens are no longer embedded in clone URLs; and various edge-case fixes across the k8s, S3, and animation subsystems.

### Added

- **`watch` improvements**:
  - **`--event-log` renamed to `--output`/`-o`** — the JSONL event log is now the primary named
    output of `watch`, consistent with all other commands. **Breaking change.**
  - **`--append-event-log` renamed to `--append`** — shorter flag to append to an existing log
    instead of truncating on startup.
  - **Continuous event-log flushing** — events are flushed to `--output` after each regeneration
    (debounce window) rather than only at exit, so the log is safe against crashes or SIGKILL.
  - **`--highlight`/`-H`** — highlight matching paths with a coloured border, same syntax as
    `map` and `diff`. Patterns are re-evaluated on every regeneration.
  - **`--include`** — show only a named subtree, same as the `map` command.
  - **`--debounce` validation** — negative values are now rejected with an error.
  - **`--snapshot` help text** clarified: PNG or SVG; best for small trees as rendering adds
    latency on large directories.
  - **Signal handling fixed** — removed a stray `signal.signal(SIGINT, SIG_IGN)` call in the
    cleanup path that was unnecessarily suppressing Ctrl-C globally during shutdown.

- **`--log-scale` validation** — values ≤ 1 (including negative values) are now rejected with an
  error in all commands (`map`, `diff`, `watch`, `git`, `hg`, `replay`). Previously, invalid
  values were silently ignored. The programmatic API (`apply_log_sizes`) raises `ValueError`.

- **`--highlight`/`-H` flag** — available on `map`, `diff`, `git`, `hg`, and `replay`. Draws a
  coloured border around tiles whose paths match a pattern. Accepts exact paths or glob patterns
  including `**` (e.g. `src/**/*.py`). Append `@color` to set the border colour
  (e.g. `--highlight "**/*.py@orange"`); defaults to red. Repeatable — each `--highlight`
  can target a different set of paths with its own colour. Works for both files and directories.
  Renders in both PNG and SVG output. In `diff`, user highlights are layered on top of the
  diff colour-coding. In `git` and `hg`, highlights appear in every animation frame.
  Colour names and hex codes accepted (any value supported by Pillow / CSS).

- **Highlight step in `dirplot demo`** — the demo now includes a `map tests/` example that
  highlights a single file (`conftest.py@red`), a glob (`**/test_git*.py@cyan`), and a folder
  (`tests/fixtures@lime`) to demonstrate the feature.

- **`replay` shows full directory context by default** — the initial frame now includes all files
  in the watched directory tree, not just those that appear in the event log. Files touched during
  recording use the first logged size as their baseline; untouched files use a live stat. Pass
  `--changed-only` to revert to the old behaviour (event-log files only), which is faster for large
  trees where the surrounding context is not needed.

## [0.4.5] - 2026-05-15

### Changed

- **`-o name.svg` no longer auto-opens a browser** — defaults to `--no-show`; pass `--show` to override. PNG unchanged.

### Internal

- **New architecture** — `VirtualPath` protocol unifies filesystem/archive path handling;
  `TreeSource` registry replaces per-backend dispatch; `RenderingPipeline` centralises
  scan → render → display orchestration; `ConsoleSession` replaces scattered terminal globals.

## [0.4.4] - 2026-05-15

### Fixed

- **`--inline` fills terminal width in iTerm2** — the iTerm2 inline image protocol now
  receives an explicit `width=<cols>` parameter so the image always fills the full column
  count, regardless of pixel-to-cell rounding differences (scrollbar width, DPI). Ghostty
  and Kitty are unaffected.

### Added

- **`dirplot diff` command** — compares two directory trees A and B as a treemap. Files are
  sized by B. Borders show diff status: green = added, red = removed, blue = changed (content
  differs). Unchanged files show no border. Supports `--context/--changed-only` (default: on,
  i.e. unchanged files are shown). A and B accept any source supported by `dirplot map`:
  local directories, `github://owner/repo[@ref]`, archives (`.zip`, `.tar.gz`, …), `s3://`,
  `ssh://`, `docker://`, and `pod://`. All visual and remote-access options are available:
  `--output`, `--format`, `--show/--no-show`, `--inline`, `--font-size`, `--colormap`,
  `--exclude`, `--depth`, `--canvas`, `--cushion/--no-cushion`, `--dark/--light`,
  `--log-scale`, `--header/--no-header`, `--quiet`, `--ssh-key`, `--ssh-password-file`,
  `--aws-profile`, `--no-sign`, `--github-token-file`, `--k8s-namespace`,
  `--k8s-container`, `--password-file`, and `--no-input`.

- **`dirplot diff` enhancements** — single-argument shorthand: `dirplot diff .` diffs the
  working tree against HEAD (git) or tip (hg). Supports `<path>@<ref>` syntax for local git
  repos (e.g. `dirplot diff .@HEAD~5 .@HEAD`). When a source is a local git or hg repo,
  only tracked files are scanned (untracked files ignored). Change detection uses blob hash
  comparison — edits that don't change file size are caught, and Git LFS files are handled
  transparently (pointer size vs disk size no longer causes false positives).

- **`--include` flag** (replaces `--subtree`, which remains as a hidden alias) — available on
  `map`, `diff`, and `metrics`. Keeps only the named subtrees after scanning; supports nested
  paths (`--include src/dirplot/fonts`). Allowlist complement to `--exclude`.

- **Glob patterns in `--exclude`** — the `--exclude` flag now accepts glob patterns on all
  commands and all backends (local, git, hg, SSH, S3, GitHub, Docker, Kubernetes, archives).
  Plain names (`.git`, `node_modules`) still work as before and match any path component.
  New: single-component globs (`*.egg-info`), relative paths (`src/vendor`), and `**` globs
  (`**/__pycache__`). Matching is consistent across all backends — previously each backend
  used a different comparison strategy (absolute paths, basenames, full URIs).

- **ISO 8601 timestamps in event log** — `dirplot watch --event-log` now writes timestamps
  as timezone-aware ISO 8601 strings (e.g. `2026-05-12T14:21:52.341+00:00`) instead of raw
  Unix epoch floats. `dirplot replay` still accepts both formats for backwards compatibility.

- **`--inline` on `dirplot git` and `dirplot hg`** — displays the single-frame output
  directly in the terminal (iTerm2, Kitty, Ghostty protocols). Only available in
  single-frame mode (no `--range` or `--period`).

- **`@ref` on HTTPS GitHub URLs** — `https://github.com/owner/repo@v1.0` is now a valid
  `repo` argument for `dirplot git`, equivalent to `github://owner/repo@v1.0`.

### Changed

- **`dirplot git` and `dirplot hg` interface redesigned** — the animation model is now
  explicit: `--range` or `--period` triggers animation mode (APNG / MP4, one frame per
  commit); neither flag produces a single static PNG of the last commit (HEAD / tip).

- **`--animate` removed** (`git`, `hg`) — use `--range` or `--period` to produce an
  animation. Without either, a single static frame is rendered.

- **`--max-commits` renamed to `--first`** (`git`, `hg`) — keeps the first N commits
  after the range/period filter is applied. The old name is no longer accepted.

- **`--last N` added** (`git`, `hg`) — keeps the *last* N commits after the range/period
  filter is applied. Counterpart to `--first`.

- **`--last PERIOD` renamed to `--period`** (`git`, `hg`) — the time-period filter is now
  `--period 30d`, `--period 24h`, etc. The old `--last` name for this flag is removed.

- **`--period` without `--range` triggers animation** — commits within the period relative
  to now are fetched and animated. GitHub URLs use `--shallow-since` for an efficient
  date-bounded shallow clone.

- **`--period` with `--range` filters relative to range end** — when both are given, the
  period cutoff is anchored to the timestamp of the last commit in the range rather than
  to now (e.g. "last 3 days of activity on this branch").

- **`--first` / `--last` slice post-fetch** — the count cap is applied in Python after all
  commits are fetched, not via `git log -n`. This ensures `--first` always gives the oldest
  N commits and `--last` always gives the newest N commits.

- **`--first` no longer controls clone depth when `--range` is given** — previously
  `--first N` would pass `--depth N` to `git clone`, making tags outside the shallow history
  unreachable. `--depth` is now only used when `--range` is absent.

- **Output extension `.png` for animations** — APNG output uses `.png` (not `.apng`).

- **`--output -` implies `--no-show`** — piping to stdout no longer opens a viewer window;
  pass `--show` explicitly to override.

- **`dirplot watch` simplified** — animation output removed from `watch`; use `dirplot replay`
  on a `--event-log` file to produce APNG/MP4. New `--snapshot FILE` option writes the current
  treemap PNG on each filesystem change (for external tools or wallpaper updaters).

- **matplotlib replaced by cmap** — matplotlib is no longer a dependency. Colormap lookups
  now use the `cmap` package instead, which is significantly smaller. All colormap names
  previously accepted by matplotlib continue to work.

## [0.4.3] - 2026-05-08

### Changed

- **Secret flags removed** — `--github-token`, `--ssh-password`, and `--password`
  flags have been removed from all commands. Use the `$GITHUB_TOKEN` / `$SSH_PASSWORD`
  environment variables or the `--github-token-file`, `--ssh-password-file`, and
  `--password-file` options instead. This prevents secrets from appearing in shell
  history and process listings.
- **`SSH_KEY` and `SSH_PASSWORD` environment variables removed** — SSH credentials
  are now resolved via `--ssh-key` / `--ssh-password-file` flags, `~/.ssh/config`
  `IdentityFile`, the ssh-agent, or an interactive prompt. The non-standard env vars
  are no longer read.
- **`--logscale` renamed to `--log-scale`** — the flag now follows the standard
  CLI convention of hyphen-separated words.
- **`--top -n` short form removed** (`dirplot metrics`) — `-n` is conventionally
  reserved for `--dry-run`; use `--top N` directly.
- **`--range -r`, `--max-commits -n`, `--workers -w` short forms removed** (`git`,
  `hg`) — these single-letter aliases conflicted with conventions or were too obscure
  to warrant a shorthand.
- **`--colormap -c`, `--subtree -s`, `--breadcrumbs -b/-B`, `--k8s-namespace -N`
  short forms removed** — single-letter flags reserved for commonly-used options per
  CLIG guidelines.
- **Status messages now always go to stderr** — info lines from `dirplot map` and
  the "Watching … (Ctrl-C to stop)" line from `dirplot watch` previously went to
  stdout in some cases; they now consistently go to stderr.
- **`$COLUMNS` / `$LINES` honoured for terminal size** — when `ioctl` and
  `os.get_terminal_size()` are both unavailable (CI, SSH sessions, scripts), the
  standard `$COLUMNS` and `$LINES` environment variables are now checked before
  falling back to the hardcoded `160×45` default.
- **`dirplot map` with no arguments shows help** — running `dirplot map` without
  paths or piped input in an interactive terminal now prints the command help instead
  of an error.

### Added

- **`dirplot metrics` command** — scans any source supported by `dirplot map`
  (local, SSH, S3, GitHub, Docker, Kubernetes, archives, stdin) and prints a
  structured text summary:
  - File and directory counts (with empty-directory count)
  - Total size (human-readable)
  - Maximum tree depth and scan time
  - Top N file extensions with file count *and* total bytes
  - Largest N files and directories, each with its percentage share of total size
- **`--sort-by count|size`** on `dirplot metrics` — controls extension ordering;
  `count` (default) sorts by number of files, `size` sorts by total bytes.
- **`--top N`** on `dirplot metrics` — caps the number of entries shown
  in each list (extensions, largest files, largest dirs). Default: 10.
- **`--json` / `--no-json`** on `dirplot metrics` — outputs all metrics as a
  structured JSON object, suitable for piping into `jq` or scripts.
- **`--metrics` / `--no-metrics`** on `dirplot map` — prints the full metrics
  block after scanning, before rendering. Lets you get treemap and metrics in
  a single pass without running two commands.
- **`tree_metrics(root_node, t_scan, top_n, sort_by) → str`** in
  `dirplot.scanner` — public API returning the human-readable metrics string.
- **`tree_metrics_dict(root_node, t_scan, top_n, sort_by) → dict`** in
  `dirplot.scanner` — public API returning a structured dict with all metrics;
  the source of truth for both the text and JSON outputs.

### Changed

- **`--log`/`--logscale` merged into a single `--logscale` parameter** — the
  boolean `--log/--no-log` flag has been removed from all commands (`map`, `watch`,
  `git`, `hg`, `replay`). Pass `--logscale <ratio>` (any value > 1) to enable
  log-scale layout compression; omit it or pass `0` to disable. The default is `0`
  (disabled). The ratio controls the max/min layout-size ratio of leaf files after
  transformation.

### Fixed

- **`dirplot overview` command** — Resolves app name/description/version from
  `importlib.metadata` so the overview output shows richer context without requiring
  manual wiring.

- **macOS Keychain error during git clone** — `git clone` is now invoked with
  `-c credential.helper=` to suppress the system credential helper. This prevents
  the `-25308` Keychain error in non-interactive environments (CI, sandboxed runs).
  Private repos are unaffected because the GitHub token is embedded directly in the
  clone URL, so no credential helper is needed regardless.

## [0.4.2] - 2026-04-15

### Fixed

- **Cushion shading applied to directory tiles** — the batch cushion pass
  incorrectly treated directory rectangles as file tiles, applying full-strength
  shading to the entire area of each directory. Directories are now shaded at half
  strength (scale 0.5) to give broad structural context, while individual file leaf
  tiles continue to receive full-strength shading. The effect is two-level: directory
  gradients provide coarse orientation, per-file gradients add local detail — matching
  the hierarchical intent of van Wijk (1999). Both the PNG and SVG renderers are updated.

### Added

- **`dirplot overview` command** — prints a human-readable summary of all
  commands, their arguments, options, and global options. Appears at position
  #2 in the help listing.

- **`dirplot hg` command** — replay Mercurial changeset history as an animated
  treemap, identical in interface to `dirplot git`. Supports `--animate`,
  `--max-commits`, `--last`, `--total-duration`, `--frame-duration`, `--fade-out`,
  `--dark`/`--light`, `--workers`, `--crf`, `--codec`, and all other animation flags.
  The `@rev` suffix on the repo path passes a revset directly to `hg log`.
  Requires `hg` on `PATH`. Only local repositories are supported — there is no
  `hg://` URI scheme because there is no Mercurial equivalent of GitHub.
  ```bash
  dirplot hg /path/to/repo --output history.png --animate
  dirplot hg /path/to/repo@tip --output history.png
  dirplot hg /path/to/repo --animate --last 30d --output history.mp4
  ```

## [0.4.1] - 2026-04-03

### Added

- **`--last PERIOD`** for `dirplot git` — filter commits by a relative time period instead
  of (or in addition to) `--max-commits`. Accepts a number followed by a unit:
  `m` (minutes), `h` (hours), `d` (days), `w` (weeks), `mo` (months = 30 days).
  For GitHub URLs, uses `git clone --shallow-since` for an efficient date-bounded shallow
  clone. `--last` and `--max-commits` may be combined (date filter + count cap both apply).
  ```bash
  dirplot git . -o history.mp4 --animate --last 30d
  dirplot git . -o history.mp4 --animate --last 24h
  dirplot git github://owner/repo -o history.mp4 --animate --last 2w --max-commits 10
  ```

- **`dirplot demo` command** — new subcommand that runs a curated set of example commands
  and saves outputs to a folder. Useful for first-time walkthroughs or verifying that
  everything works in a given environment. Accepts `--output` (default: `demo/`),
  `--github-url` (default: `https://github.com/deeplook/dirplot`), and
  `--interactive` / `-i` to step through and confirm each command individually. Output
  uses rich formatting with colour, section rules, and status indicators.
  ```bash
  dirplot demo                             # run all examples, save to ./demo/
  dirplot demo --output ~/dp-demo --interactive
  ```

- **`--fade-out` for animated output** — appends a fade-out sequence at the end of
  animations produced by `dirplot git --animate`, `dirplot watch --animate`, and
  `dirplot replay`. Four flags control the effect:
  - `--fade-out` / `--no-fade-out` — enable/disable (default: off)
  - `--fade-out-duration SECS` — total fade length in seconds (default: 1.0)
  - `--fade-out-frames N` — number of blend steps; defaults to 4 per second of duration
    so longer fades are automatically finer-grained
  - `--fade-out-color COLOR` — target colour: `auto` (black in dark mode, white in light
    mode), `transparent` (PNG/APNG only; fades to fully transparent), any CSS colour
    name, or hex code (e.g. `"#1a1a2e"`)
  ```bash
  dirplot git . -o history.png --animate --fade-out
  dirplot git . -o history.mp4 --animate --fade-out --fade-out-duration 2.0
  dirplot git . -o history.png --animate --fade-out --fade-out-color transparent
  ```

- **`--dark` / `--light` mode** for all treemap commands — controls background and border
  colours. Dark mode (default) uses a near-black canvas with white directory labels; light
  mode uses a white canvas with black labels. Available on `map`, `git`, `watch`, and
  `replay`.
  ```bash
  dirplot map . --light
  dirplot git . -o history.mp4 --animate --light
  ```

- **Metadata in MP4/MOV output** — `dirplot git`, `dirplot watch`, and `dirplot replay`
  now embed the same dirplot metadata (date, software version, OS, Python version,
  executed command) into MP4/MOV files that was previously only written to PNG and SVG.
  `dirplot read-meta` reads it back via `ffprobe`.

- **Automatic `gh` CLI credential fallback** — if `--github-token` and `GITHUB_TOKEN`
  are both absent, dirplot silently runs `gh auth token`. Users authenticated with the
  [GitHub CLI](https://cli.github.com/) (`gh auth login`) can access private repositories
  with no extra configuration. Token resolution order: `--github-token` →
  `$GITHUB_TOKEN` → `gh auth token`.

### Changed

- `--fade-out-frames` defaults dynamically to `round(fade_out_duration × 4)` rather than
  a fixed 4, so a 2-second fade automatically uses 8 frames and a 0.5-second fade uses 2.

### Fixed

- **`--total-duration` overshooting the target length** — when many commits fell within
  a burst (closely-spaced timestamps), their proportional frame durations would each be
  raised to the 200 ms floor, inflating the total well beyond the requested duration
  (e.g. 34 s instead of 30 s). The floor is still applied for readability, but the
  non-floored frames are now scaled down to compensate so the sum always matches
  `--total-duration` exactly.

### Docs

- Added `## dirplot read-meta` section to `docs/CLI.md` (previously undocumented).
- Documented external tool requirements: `git` (required by `dirplot git`), `ffmpeg`
  (required for MP4 output), `ffprobe` (required by `read-meta` on MP4 files) — in both
  `README.md` and `docs/CLI.md`.

## [0.4.0] - 2026-03-28

### Added

- **MP4 video output** — all three animation commands (`watch --animate`, `git --animate`,
  `replay`) now write MP4 video when the output path ends in `.mp4` or `.mov`. Quality is
  controlled via `--crf` (Constant Rate Factor: 0 = lossless, 51 = worst, default 23) and
  `--codec` (`libx264` H.264 or `libx265` H.265). MP4 files are typically 10–100× smaller
  than equivalent APNGs. Requires `ffmpeg` on PATH.
  ```bash
  dirplot git . -o history.mp4 --animate
  dirplot git . -o history.mp4 --animate --crf 18 --codec libx265
  dirplot replay events.jsonl -o replay.mp4 --total-duration 30
  dirplot watch . -o treemap.mp4 --animate
  ```
- **`@ref` suffix for `dirplot git`**: local repository paths now accept an optional
  `@ref` suffix to target a specific branch, tag, or commit SHA without needing
  `--range` (e.g. `dirplot git .@my-branch -o out.apng --animate`). `--range` takes
  precedence when both are provided.
- **`dirplot git` subcommand** — replays a git repository's commit history as an
  animated treemap. Each commit becomes one frame; changed tiles receive the same
  colour-coded highlight borders as `watch --animate` (green = created, blue = modified,
  red = deleted). The commit SHA and local timestamp are shown in the root tile header,
  and a progress bar at the top of each frame advances as the animation plays.
  ```bash
  # Animate all commits, write APNG
  dirplot git . --output history.apng --animate --exclude .git

  # Last 50 commits on main, 30-second animation with time-proportional frame durations
  dirplot git . --output history.apng --animate \
    --range main~50..main --total-duration 30

  # Live-updating static PNG (last frame wins; useful with an auto-refreshing viewer)
  dirplot git /path/to/repo --output treemap.png --max-commits 100
  ```
- **`--range`** (`-r`): git revision range passed directly to `git log`
  (e.g. `main~50..main`, `v1.0..HEAD`). Defaults to the full history of the current branch.
- **`--max-commits`** (`-n`): cap the number of commits processed.
- **`--frame-duration`**: fixed frame display time in ms when `--total-duration` is not set
  (default: 1000 ms).
- **`--total-duration`**: target total animation length in seconds. Frame durations are
  scaled proportionally to the real elapsed time between commits, so quiet periods in
  development history map to longer pauses and burst activity to rapid flips. A 200 ms
  floor prevents very fast commits from being invisible; durations are capped at 65 535 ms
  (APNG uint16 limit). A summary line reports the actual range:
  `Proportional timing: 200–7553 ms/frame (total ~30.1s)`.
- **`--workers`** (`-w`): number of parallel render workers in animate mode (default: all
  CPU cores). Rendering is memory-bandwidth bound, so 4–8 workers is typically optimal;
  use this flag to tune for your hardware.
- **Time-proportional progress bar**: a 2 px bar at the top of each frame advances in
  proportion to animation time consumed, not frame count — so a burst of closely-spaced
  commits produces only a small movement while a long quiet period advances it visibly.
  With fixed `--frame-duration` the bar is linear as before.

- **Debounced watch** (`--debounce SECONDS`, default `0.5`): the `watch` subcommand now
  collects rapid file-system event bursts and regenerates the treemap once per quiet
  period instead of on every raw event. A `git checkout` touching 100 files triggers
  exactly one render after the activity settles. Pass `--debounce 0` to restore the
  old immediate-fire behaviour.
  ```bash
  dirplot watch . --output treemap.png                      # 500 ms debounce (default)
  dirplot watch . --output treemap.png --debounce 1.0       # 1 s quiet window
  dirplot watch . --output treemap.png --debounce 0         # immediate, as before
  ```
- **Event log** (`--event-log FILE`): on Ctrl-C exit, all raw file-system events
  recorded during the session are written as newline-delimited JSON (JSONL) to the
  given file. Each line has `timestamp`, `type`, `path`, and `dest_path` fields.
  The log is written only if there are events to record.
  ```bash
  dirplot watch src --output treemap.png --event-log events.jsonl
  # Ctrl-C, then:
  cat events.jsonl | python3 -m json.tool
  ```
- **File-change highlights** (`--animate`): each APNG frame now draws colour-coded
  borders around tiles that changed since the previous frame — green for created,
  blue for modified, red for deleted, orange for moved. Deleted files are highlighted
  retroactively on the *previous* frame (since the tile no longer exists in the current
  one), so the animation clearly shows both the disappearance and the appearance of files.
  Moved files appear as a deletion at the old path and a creation at the new path.
- **Graceful finalization**: Ctrl-C now flushes any pending debounced render before
  stopping the observer, so the output file always reflects the final state of the
  watched tree. A second Ctrl-C during APNG writing is ignored so the file can finish
  being written.
- **Tree comment stripping**: trailing `# comments` in `tree` output are now ignored
  by the path-list parser, so annotated tree listings (e.g. `├── config.json  # app config`)
  are parsed correctly. Filenames containing `#` without a leading space are preserved.
- **`scripts/apng_frames.py`**: utility script to list frame durations, dimensions, and
  offsets in an APNG file.
- **`scripts/watch_events.py`**: utility script to watch directories and log filesystem
  events to a CSV file (or stdout) in real time using watchdog.
- **`--depth` for `watch`**: the `watch` subcommand now accepts `--depth N` to limit
  recursion depth, matching the behaviour of `dirplot map`.
  ```bash
  dirplot watch . --output treemap.png --depth 3
  ```
- **`dirplot replay` subcommand** — replays a JSONL filesystem event log (as produced
  by `dirplot watch --event-log`) as an animated treemap APNG. Events are grouped into
  time buckets (one frame per bucket, default 60 s), with colour-coded highlight borders
  matching `watch --animate`. Only files referenced in the event log appear in the
  treemap; the common ancestor of all paths is used as the tree root. Frame durations
  can be uniform (`--frame-duration`, default 500 ms) or proportional to the real time
  gaps between buckets (`--total-duration`). Frames are rendered in parallel.
  ```bash
  # Replay an event log with 60-second buckets, 30-second total animation
  dirplot replay events.jsonl --output replay.apng --total-duration 30

  # Smaller buckets for fine-grained activity, fixed frame duration
  dirplot replay events.jsonl --output replay.apng --bucket 10 --frame-duration 200
  ```

- **`dirplot git` accepts GitHub URLs** — pass a `github://owner/repo[@branch]` or
  `https://github.com/owner/repo` URL directly to `dirplot git`. dirplot clones the
  repository into a temporary directory (shallow when `--max-commits` is set, full
  otherwise), runs the full history pipeline locally, and removes the clone on exit.
  No permanent local copy is created.
  ```bash
  # Animate the last 50 commits of a GitHub repo — no local clone needed
  dirplot git github://owner/repo --output history.png --animate --max-commits 50

  # Specific branch
  dirplot git github://owner/repo@main --output history.png --animate --max-commits 50
  ```
- **Total commit count shown** — `dirplot git` now reports the total number of commits
  available alongside the number being animated, so you can gauge how much history
  exists before committing to a longer run:
  ```
  Replaying 20 of 147 commit(s) (increase --max-commits to process more) ...
  ```
  For GitHub URLs the count is fetched with a single cheap API request (one commit
  object + `Link` header). For local repos `git rev-list --count HEAD` is used.
- **`--github-token`** (`$GITHUB_TOKEN`): added to `dirplot git` for private GitHub
  repos or to raise the API rate limit when fetching the total commit count.

### Changed

- **`libarchive-c` is now an optional dependency.** Install it with
  `pip install 'dirplot[libarchive]'` (plus the system library:
  `brew install libarchive` / `apt install libarchive-dev`) to enable
  `.iso`, `.cpio`, `.rpm`, `.cab`, `.lha`, `.xar`, `.pkg`, `.dmg`, `.a`, `.ar`,
  and `.tar.zst` / `.tzst` support. The base install works without it; a clear
  error is shown if you try to open one of these formats without the extra.

- **`--animate` writes the APNG once on exit** instead of reading and rewriting the
  entire file on every render. Frames are accumulated as raw PNG bytes in memory and
  flushed as a single multi-frame APNG when the watcher stops (Ctrl-C). This removes
  an O(N²) disk-I/O pattern where frame K required reading a K-frame APNG just to
  append one more frame. Status output during a session now reads `Captured frame N`;
  the final `Wrote N-frame APNG → …` line confirms the file was written on exit.

### Fixed

- **Initial scan progress**: the `watch` subcommand now prints `Scanning <roots> …`
  before the first render and starts the filesystem observer only after the initial
  treemap has been generated, avoiding spurious events during the first scan.
- **`--animate` race condition**: the debounce timer thread was marked as daemon,
  causing an in-progress render to be killed when the main thread exited after
  `observer.join()`. The timer is no longer a daemon thread; `flush()` joins any
  in-flight render before stopping.
- **`--animate` Pillow APNG regression**: passing `pnginfo` alongside `save_all=True`
  caused Pillow to silently write a static PNG instead of an APNG. The `pnginfo`
  argument is now omitted from multi-frame saves (cross-process timing metadata is
  no longer needed since frames are held in memory for the lifetime of the process).
- **APNG frame duration overflow**: restoring the inter-session frame duration from
  stored metadata could produce a value exceeding 65 535 ms — the maximum expressible
  by APNG's uint16 `delay_num` field when `delay_den = 1000` — causing Pillow to raise
  `cannot write duration`. Durations are now capped at 65 535 ms (≈ 65 s).

- **Path-list input from `tree` / `find`** (`--paths-from FILE` or stdin pipe): the `map`
  subcommand now accepts a list of paths produced by `tree` or `find` — either piped via
  stdin or read from a file with `--paths-from`. Format is auto-detected: `tree` output
  (detected by `├──` / `└──` box-drawing characters) or `find` output (one path per line).
  Handles `tree -s` / `tree -h` (size columns), `tree -f` (full embedded paths), and the
  default indented name format. Ancestor/descendant duplicates are collapsed automatically
  so only the minimal set of roots is passed to the scanner.
  ```bash
  # Implicit stdin — no flag needed
  tree src/        | dirplot map
  tree -s src/     | dirplot map        # with file sizes in tree output
  find . -name "*.py" | dirplot map

  # Explicit file
  tree src/ > paths.txt && dirplot map --paths-from paths.txt

  # Explicit stdin
  tree src/ | dirplot map --paths-from -
  ```
  Positional path arguments and path-list input are mutually exclusive — combining them
  exits with a clear error. Only local paths are supported (remote backends such as
  `docker://`, `s3://`, `ssh://` remain positional-arg only).

- **`dirplot watch` accepts multiple directories**: the `watch` subcommand now takes
  one or more positional path arguments and schedules a filesystem observer for each,
  regenerating the treemap from all roots on every change.
  ```bash
  dirplot watch src tests --output treemap.png
  ```
- **`dirplot map` accepts multiple file paths as roots**: previously, multi-root mode
  required every argument to be a directory. Individual files can now be passed as roots;
  each is treated as a leaf node and displayed under the common parent directory.
  ```bash
  dirplot map src/main.py src/util.py --no-show
  ```
- **stdout output** (`--output -`): passing `-` as the output path writes the PNG or SVG
  bytes to stdout, enabling piping to other tools. Header and progress lines are
  automatically redirected to stderr to keep the binary stream clean.
  ```bash
  dirplot map . --output - | convert - -resize 50% small.png
  dirplot map . --output - --format svg > treemap.svg
  ```

## [0.3.3] - 2026-03-14

### Added

- **Breadcrumbs mode** (`--breadcrumbs/--no-breadcrumbs`, `-b/-B`, on by default): directories
  that form a single-child chain (one subdirectory, no files) are collapsed into a single tile
  whose header shows the full path separated by ` / ` (e.g. `src / dirplot / fonts`). When the
  label is too wide, middle segments are replaced with `…` (`src / … / fonts`). The root tile
  is never collapsed. Disable with `-B` or `--no-breadcrumbs`.
- **Tree depth in root label**: the root tile header now includes `depth: N` alongside the
  file, directory, and size summary (e.g. `myproject — 124 files, 18 dirs, 4.0 MB (…), depth: 6`).
  The depth reflects the original tree structure and is invariant to whether breadcrumbs mode
  is active.

## [0.3.2] - 2026-03-13

### Added

- **`dirplot watch`** subcommand — watches a directory and regenerates the treemap
  on every file-system change using watchdog (FSEvents on macOS, inotify on Linux,
  kqueue on BSD). Requires `watchdog`, now a core dependency.
  ```bash
  dirplot watch . --output treemap.png
  dirplot watch . --output treemap.png --animate   # APNG, one frame per change
  ```
- **Vertical file labels**: file tiles that are at least twice as tall as wide now
  display their label rotated 90° CCW, letting the text span the full tile height
  instead of being squeezed into the narrow width.
- **Scan and render timing** shown in header output:
  `Found 1,414 files … [2.3s]` and `Saved dirplot to out.png  [0.4s]`.
- **Multiple local roots**: `dirplot map src tests` accepts two or more local
  directory paths, finds their common parent, and shows only those subtrees.
- **`--subtree` / `-s`** option (repeatable) — allowlist complement to `--exclude`:
  keep only the named direct children of the root after scanning. Supports nested
  paths such as `--subtree src/dirplot/fonts`.

### Fixed

- `--exclude` on pod and Docker backends now prunes entire subtrees — previously only
  the exact path was matched, so all children leaked through.
- Clearer error for distroless pods: exit code 126 from `kubectl exec` now surfaces as
  an actionable message explaining that the container has no shell or `find` utility.
- Adaptive file-label font size is now computed with a single `textbbox` measurement
  (one call per tile) instead of stepping down one pixel at a time — eliminates an
  O(font_size × n_tiles) bottleneck that caused near-blocking on large trees such as
  `.venv` directories.

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
- CLI options: `--output`, `--show/--no-show`, `--inline`, `--legend`, `--font-size`, `--colormap`, `--exclude`, `--canvas`, `--header/--no-header`, `--cushion/--no-cushion`, `--log`.
- Full test suite (65 tests), strict mypy, ruff linting, pre-commit hooks, and CI on Python 3.10–3.13.
