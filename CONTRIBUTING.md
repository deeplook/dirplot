# Contributing

## Development Setup

```bash
git clone -c credential.helper= https://github.com/deeplook/dirplot
cd dirplot
uv sync --all-extras   # install all dependencies including dev tools and extras
uv run pre-commit install  # install git hooks for formatting/linting
```

## Running Tests

```bash
make test       # run the full test suite
make coverage   # run with coverage report (target: 90% line coverage)
```

To run a specific test file or test:

```bash
uv run pytest tests/test_cli.py
uv run pytest tests/test_drawing.py::test_cushion_shading -v
```

## Archive test fixtures

`tests/fixtures/` contains one pre-built archive per supported format. To regenerate them:

```bash
python scripts/make_fixtures.py
```

The script creates a small sample tree and archives it in every supported format. The RAR fixture is skipped automatically if the `rar` CLI is not found.

The pytest `sample_archives` session fixture in `tests/conftest.py` regenerates the same files into a temporary directory at test-session start, so running the script is not required for CI or for running the test suite locally.

## Code Style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [mypy](https://mypy.readthedocs.io/) for type checking. Pre-commit hooks run these automatically on each commit.

```bash
make format   # auto-format and fix lint issues
make lint     # check only (no changes)
```

## Code Organisation

```
src/dirplot/
  app.py            — Typer app entry point; imports all subcommands
  main.py           — CLI entry point called by the `dirplot` script
  commands/
    treemap.py      — `dirplot map` command
    diff.py         — `dirplot diff` command
    vcs.py          — `dirplot git` and `dirplot hg` commands
    watch.py        — `dirplot watch` command
    replay.py       — `dirplot replay` command
    misc.py         — `dirplot demo`, `dirplot termsize`, `dirplot read-meta`
  render_png.py     — PNG treemap renderer (Pillow)
  render_svg.py     — SVG treemap renderer
  layout.py         — squarified treemap layout algorithm
  scanner.py        — local filesystem scanner and metrics
  display.py        — inline terminal display (iTerm2 / Kitty protocols)
  terminal.py       — terminal size detection
  github.py         — GitHub Git Trees API backend
  ssh.py            — SSH backend (paramiko)
  s3.py             — AWS S3 backend (boto3)
  docker.py         — Docker backend (docker exec)
  k8s.py            — Kubernetes backend (kubectl exec)
  archive.py        — archive reading (zip, tar, 7z, rar, libarchive)
  node.py           — Node dataclass (shared tree representation)
```

All remote backends return a `Node` tree using the same dataclass, so `create_treemap` and `create_treemap_svg` work identically regardless of source.

To add a new command: create `src/dirplot/commands/mycommand.py` with a Typer app, then import and add it in `app.py`.

## Submitting Changes

1. Fork the repository and create a feature branch (`feature/my-thing`).
2. Make your changes, add tests if needed.
3. Run `make lint` and `make test` — both must pass.
4. Open a pull request against `main`.
