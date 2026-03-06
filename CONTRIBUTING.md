# Contributing

## Development Setup

```bash
git clone https://github.com/deeplook/dirplot
cd dirplot
uv sync --all-extras
uv run pre-commit install
```

## Code Style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [mypy](https://mypy.readthedocs.io/) for type checking.

```bash
make format   # auto-format and fix lint issues
make lint     # check only (no changes)
```

## Testing

```bash
make test       # run the test suite
make coverage   # run with coverage report
```

Target: 90 % line coverage.

## Submitting Changes

1. Fork the repository and create a feature branch (`feature/my-thing`).
2. Make your changes, add tests if needed.
3. Run `make lint` and `make test` — both must pass.
4. Open a pull request against `main`.
