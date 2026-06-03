# Web Interface (`dirplot serve`)

← [Home](index.md)

`dirplot serve` launches an interactive treemap in your browser. Unlike the static PNG/SVG output of `dirplot map`, the web interface lets you explore the tree live — zoom into directories, search, preview file contents, and tweak every setting without re-running the command.

```bash
dirplot serve .
dirplot serve /path/to/project
dirplot serve github://owner/repo
dirplot serve s3://my-bucket
```

The server starts on `http://localhost:8000` by default. Press `Ctrl-C` to stop it.

## Options

| Flag | Default | Description |
|---|---|---|
| `--port` | `8000` | TCP port to listen on |
| `--host` | `127.0.0.1` | Bind address (`0.0.0.0` to expose on LAN) |
| `--depth N` | unlimited | Initial recursion depth |
| `--colormap NAME` | `tab20` | Initial colormap |
| `--exclude PATTERN` | — | Glob pattern to skip (repeatable) |
| `--log-scale N` | `1` (off) | Initial log-scale strength (2–10) |
| `--allow-write` | off | Enable file delete/move via the context menu |

---

## Toolbar

The toolbar runs across the top of the page and contains three areas from left to right.

### Source input

The source field (left of the breadcrumbs) shows the current root. Type any supported path or URL and press **Enter** to rescan:

| Input | Example |
|---|---|
| Local directory | `/home/user/project` or `../sibling` |
| Archive (local) | `/tmp/release.tar.gz` |
| Archive (remote URL) | `https://example.com/archive.zip` |
| GitHub repository | `github://owner/repo` or `https://github.com/owner/repo` |
| SSH remote | `ssh://user@host/path` |
| AWS S3 | `s3://bucket/prefix` |
| Docker container | `docker://container/path` |
| Kubernetes pod | `pod://pod-name/path` or `pod://pod-name@namespace/path` |

> **Note:** Remote URL archives are downloaded to a temporary file (max 100 MB), scanned, then deleted immediately.

### Breadcrumbs

Shows your current zoom path inside the tree. Click any crumb to jump back to that level.

### Search

Type to highlight matching files. The `.*` pill to the right of the input toggles **regular expression** mode — the pill turns accent-coloured when active. Invalid regex patterns turn the input border red without crashing.

---

## Treemap

The main canvas renders the directory tree as a nested squarify treemap. Tile area is proportional to file size (or log-scaled size when log-scale > 1).

### Interaction

| Action | Result |
|---|---|
| Click a file tile | Show info panel; load preview if Preview tab is open |
| Double-click a directory tile | Zoom into that directory |
| Click the canvas background | Clear selection |
| Right-click any tile | Open context menu (rename / delete if `--allow-write`) |
| Shift-click tiles | Multi-select |

### Keyboard shortcuts

All shortcuts are suppressed when an input field has focus. Press **Esc** to blur any input and return focus to the canvas.

| Key | Action |
|---|---|
| `j` | Move keyboard focus to next tile |
| `k` | Move keyboard focus to previous tile |
| `Enter` | Zoom into focused directory; preview focused file (if Preview tab open) |
| `Backspace` | Zoom out one level |
| `/` | Jump focus to the search field |
| `Esc` | Clear focus, close info panel, deselect all; blur any input |

The keyboard-focused tile is highlighted with an accent-coloured outline.

---

## Sidebar

The sidebar on the right has three tabs: **Settings**, **Metrics**, and **Preview**. Collapse or expand it with the `‹` / `›` toggle, or drag the resize handle.

### Settings

All settings apply instantly — there is no Apply button.

| Setting | Description |
|---|---|
| Dark mode | Toggle between dark and light theme |
| Depth | Maximum recursion depth (∞ button removes the limit) |
| Log scale | Compress the size range so small files remain visible (1 = off, 2–10) |
| Font size | Label font size inside tiles |
| Colormap | Color palette for file extensions |
| Code theme | Syntax highlighting theme for text file previews (10 paired dark/light options) |
| Canvas size | Fix the treemap to an explicit W × H (blank = auto) |
| Exclude | Glob patterns to hide, one per line |
| Include | Subtree paths to keep, one per line (all others hidden) |
| Highlight | `glob@color` rules, one per line — e.g. `**/*.py@orange` |

**Reset all** restores every setting to its startup default.

### Metrics

Displays aggregate statistics for the current tree: total size, file count, directory count, average file size, largest file, deepest path, and scan duration.

### Preview

Previews the last-clicked file. The panel stays empty until you click a tile — switching to this tab does **not** auto-load a preview; click a tile while the tab is open.

| File type | Preview |
|---|---|
| Images (PNG, JPG, GIF, SVG, WebP, BMP, ICO) | Inline `<img>` |
| Video (MP4, MOV, WebM) | Inline `<video controls>` player |
| PDF | Inline `<iframe>` with the browser's native PDF viewer |
| Text / code | Syntax-highlighted with highlight.js |
| Binary | Hex dump of the first 1 000 bytes |

For PNG, SVG, MP4, and MOV files that were created by dirplot, any embedded metadata (Date, Software, Command, Python, OS, URL) is shown in a table below the preview.

> **Note:** File preview is unavailable for remote sources (GitHub, S3, etc.) since the files are not accessible on the local filesystem.

---

## Live reload

The server watches the scanned directory for changes via a WebSocket connection. When files are added, removed, or modified the treemap refreshes automatically. Live reload is only active for local filesystem sources.
