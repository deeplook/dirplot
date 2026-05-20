# Guides

← [Home](index.md)

- [Inline terminal display](#inline-terminal-display)
- [Running via Docker](#running-dirplot-via-docker)
- [Performance and scaling](#performance-and-scaling)

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
  --output - | imgcat
```

**Display inline (any iTerm2-compatible terminal, no extra tools):**

```bash
docker run --rm dirplot dirplot map github://steipete/birdclaw \
  --output - | python3 -c "
import sys, base64
data = sys.stdin.buffer.read()
sys.stdout.buffer.write(
    b'\033]1337;File=inline=1;size=' + str(len(data)).encode()
    + b':' + base64.b64encode(data) + b'\a\n'
)
"
```

> **Note:** `--inline` does not work when running inside a container — dirplot cannot probe your host terminal from within Docker. Use `--output -` and display the bytes on the host side instead, as shown above.
>
> **Terminal size:** the container has no tty, so dirplot cannot detect your terminal dimensions. The default 1280×720 fallback is used unless you pass `--canvas WIDTHxHEIGHT` explicitly or set `-e COLUMNS=$(tput cols) -e LINES=$(tput lines)`.

---

## Performance and scaling

### Limiting recursion depth with `--depth`

For large remote sources (GitHub repos, S3 buckets, SSH hosts, Docker containers) or deeply nested local trees, use `--depth N` to cap recursion:

```bash
dirplot map github://torvalds/linux --depth 3   # top 3 levels only
dirplot map s3://my-bucket --depth 2             # bucket root + one prefix level
dirplot map ssh://user@host:/data --depth 4
```

Start with `--depth 3` as a baseline — it covers most meaningful structure without enumerating every leaf file. Increase only if you need finer detail. For local directories, `--depth` is rarely needed unless the tree exceeds a few hundred thousand files.

### When to use `--log-scale`

By default, tile area is proportional to file size. If one file or directory dominates (e.g. a large binary, a `node_modules` folder, a media asset), everything else shrinks to invisible tiles. Use `--log-scale` to compress the size range:

```bash
dirplot map . --log-scale 4       # moderate compression (recommended starting point)
dirplot map . --log-scale 8       # strong compression — extreme size ratios
dirplot map . --log-scale 2       # mild compression
```

The argument is the log base: `--log-scale 4` means a 4× size ratio maps to a 1-stop visual difference. Higher values flatten the map more. Omit `--log-scale` entirely when file sizes are in a similar range — the default linear scale gives the most accurate area encoding.

### Very large trees

For trees with hundreds of thousands of files (e.g. the Linux kernel, a full S3 bucket):

- **Use `--depth`** — the single biggest speedup for remote sources.
- **Avoid `--output` formats that embed all metadata** — SVG grows linearly with node count; prefer PNG for very large trees.
- **GitHub API truncation**: the Git Trees API caps responses at ~100k entries. dirplot warns when this happens and renders what it received. Use `--depth` to stay under the limit.
- **Memory**: each node uses a small fixed amount of memory; 500k files typically uses ~500 MB. If memory is a concern, combine `--depth` with `--exclude` to prune large subtrees.

### WSL2 performance tips

- File I/O across the WSL2 boundary (accessing Windows paths like `/mnt/c/…` from Linux) is significantly slower than native Linux paths. Where possible, work with files in the Linux filesystem (`~/` or `/tmp/`).
- For `--inline`, keep the canvas small (`--canvas 800x600`) to reduce the data transferred over the WSL2 bridge to the terminal.
