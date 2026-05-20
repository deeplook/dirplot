# Installation

← [Home](index.md)

Install via `uv`, `pipx`, or `pip` — `uv tool install` is the recommended method:

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

## How to run dirplot

| Method / Install | Command | Best for |
|---|---|---|
| `uv tool install dirplot` | `dirplot map .` | Day-to-day use — isolated install, fast startup |
| `uvx dirplot` (no install) | `uvx dirplot map .` | Trying it out or one-off use; always runs the latest release |
| `pip install dirplot` | `from dirplot import build_tree, create_treemap` | Scripting, automation, Jupyter notebooks — see [Python API](api.md) |
| `docker build -t dirplot .` | `docker run --rm dirplot dirplot map … --output -` | CI or containerised environments — see [Docker](guides.md#running-dirplot-via-docker) |

## Optional extras

Install only what you need:

| Extra | Enables | Install |
|---|---|---|
| `ssh` | Scan remote servers via SSH (adds [paramiko](https://www.paramiko.org/)) | `pip install "dirplot[ssh]"` |
| `s3` | Scan AWS S3 buckets (adds [boto3](https://boto3.amazonaws.com/)) | `pip install "dirplot[s3]"` |
| `libarchive` | Additional archive formats: `.tar.zst`, `.iso`, `.dmg`, `.rpm`, `.cab`, … (requires system [libarchive](https://libarchive.org/)) | `pip install "dirplot[libarchive]"` |

**Remote backend CLIs** — no Python package needed; dirplot shells out to these directly:

| CLI | Enables | macOS | Debian/Ubuntu | Check |
|---|---|---|---|---|
| `docker` | Scan Docker containers | [Docker Desktop](https://docs.docker.com/desktop/mac/install/) or `brew install docker` | `sudo apt install docker.io` | `docker info` |
| `kubectl` | Scan Kubernetes pods | `brew install kubectl` | `sudo apt install kubectl` | `kubectl version` |
| `gog` | Scan Google Drive (then run `gog auth`) | `brew install gogcli` | — | `gog --version` |

**Runtime prerequisites** — install these before using the relevant commands:

| Requirement | Used by | macOS | Debian/Ubuntu | Check |
|---|---|---|---|---|
| [ffmpeg](https://ffmpeg.org/) | MP4/MOV output, `dirplot meta` on `.mp4` | `brew install ffmpeg` | `sudo apt install ffmpeg` | `ffmpeg -version` |
| `git` | `dirplot git` | `brew install git` | `sudo apt install git` | `git --version` |
| `hg` (Mercurial) | `dirplot hg` | `brew install mercurial` | `sudo apt install mercurial` | `hg --version` |
| [libarchive](https://libarchive.org/) | `dirplot[libarchive]` extra | `brew install libarchive` | `sudo apt install libarchive-dev` | `bsdtar --version` |
| [watchdog](https://github.com/gorakhargosh/watchdog) | `dirplot watch` | installed automatically | installed automatically | — |
