# Troubleshooting

← [Home](index.md)

- [Image is the wrong size or too small in `--inline` mode](#image-is-the-wrong-size-or-too-small-in---inline-mode)
- [`--inline` shows nothing or garbled output](#--inline-shows-nothing-or-garbled-output)
- [GitHub rate limit errors](#github-rate-limit-errors)
- [Large remote trees are slow or truncated](#large-remote-trees-are-slow-or-truncated)
- [Archive errors](#archive-errors)
- [MP4 output fails](#mp4-output-fails)
- [SSH authentication failures](#ssh-authentication-failures)
- [S3 access errors](#s3-access-errors)
- [Output image is blank or all one colour](#output-image-is-blank-or-all-one-colour)
- [Labels are too small to read](#labels-are-too-small-to-read)
- [Windows / WSL2 notes](#windows--wsl2-notes)

---

### Image is the wrong size or too small in `--inline` mode

dirplot reads the terminal pixel size via `TIOCGWINSZ`. This can fail or return wrong values when:

- **stdout is a pipe** (e.g. `uv run`, `nohup`, CI): pass `--canvas WIDTHxHEIGHT` explicitly, or set `COLUMNS` and `LINES` env vars.
- **Inside Docker**: same as above — the container has no tty.
- **`--inline` in Docker**: not supported; use `--output - | imgcat` instead (see [Running via Docker](guides.md#running-dirplot-via-docker)).

### `--inline` shows nothing or garbled output

- Confirm your terminal is in the supported list in [Inline terminal display](guides.md#inline-terminal-display).
- In tmux/screen, the inline protocol may be blocked. Try running dirplot in a bare terminal session.
- AI coding tool terminals (Claude Code, Cursor, Copilot Chat) do not support inline images — use `--show` or `--output`.

### GitHub rate limit errors

Without a token, GitHub allows 60 unauthenticated API requests per IP per hour. Authenticate via:

```bash
gh auth login                        # Option 1: gh CLI (picked up automatically)
export GITHUB_TOKEN=ghp_…            # Option 2: env var
dirplot map github://… --github-token-file ~/.github-token   # Option 3: token file
```

See [Examples — GitHub Repositories](remote-sources.md#github-repositories) for full authentication details.

### Large remote trees are slow or truncated

- Use `--depth N` to limit recursion (start with `--depth 3`).
- GitHub's Git Trees API truncates responses above ~100k entries; dirplot warns and renders what it received.
- For SSH scans, slow hosts may time out on very large trees — use `--depth` to reduce the `find` traversal.
- If one large file squashes everything else into tiny tiles, add `--log-scale 4`.

### Archive errors

- **`libarchive-c` import error**: the Python binding is installed but the system C library is missing. Install it:
  ```bash
  brew install libarchive        # macOS
  sudo apt install libarchive-dev  # Debian/Ubuntu
  ```
- **Password-protected archive**: pass `--password-file <file>` or let dirplot prompt interactively. Use `--no-input` to fail instead of prompting.
- **`.deb` / UDIF `.dmg` not supported**: see [Archive Formats — Intentionally unsupported formats](archives.md#intentionally-unsupported-formats).

### MP4 output fails

Ensure `ffmpeg` is installed and on `PATH`:

```bash
ffmpeg -version   # should print version info
brew install ffmpeg   # macOS
sudo apt install ffmpeg   # Debian/Ubuntu
```

### SSH authentication failures

- Ensure your key is loaded: `ssh-add -l` should list it. If not: `ssh-add ~/.ssh/id_ed25519`.
- Confirm the host is reachable: `ssh user@host ls /path/to/dir`.
- dirplot uses `paramiko` (pure-Python SSH); keys stored only in an SSH agent or in non-standard formats may need `--ssh-key /path/to/key`.
- Install the SSH extra if you see an import error: `pip install "dirplot[ssh]"`.

### S3 access errors

- **`NoCredentialsError`**: run `aws configure` or export `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION`.
- **`AccessDenied`**: the IAM principal needs at minimum `s3:ListBucket` and `s3:GetObject` on the target bucket.
- **Slow scans on large buckets**: use `--depth N` to limit prefix recursion (e.g. `--depth 2`).

### Output image is blank or all one colour

- The directory may be empty or contain only zero-byte files. dirplot tiles are sized by file size — nothing to size means nothing to draw.
- With `--log-scale`, a single enormous file can dominate. Try without it first, then add `--log-scale 4` if the range is too wide.
- Check that the path resolves correctly: run `dirplot metrics <path>` first to confirm files are found.

### Labels are too small to read

The default font size is 12 px. If labels appear too small — common on high-resolution displays or when rendering at large canvas sizes — increase it with `--font-size`:

```bash
dirplot map . --font-size 16
dirplot git . --range main --output h.mp4 --font-size 14
```

`--font-size` is available on `map`, `diff`, `git`, `hg`, and `replay`. Automatic font-size scaling based on canvas size is not yet implemented.

### Windows / WSL2 notes

- **Inline display**: WSL2 terminals running inside Windows Terminal do not support iTerm2 or Kitty protocols — use `--output file.png` and open the file, or use a supported terminal (e.g. Ghostty for Windows).
- **`--inline` slow on WSL2**: large images transferred over the WSL2 bridge can be slow; reduce canvas size with `--canvas 800x600`.
- **Path separators**: always use forward slashes or WSL2 Linux paths (`/mnt/c/…`) — Windows-style paths with backslashes are not supported.
