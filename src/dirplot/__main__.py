"""Entry point for ``python -m dirplot``."""

import os
import sys


# Handle --no-color and TERM=dumb before any Rich/Typer imports so the env var
# takes effect at console creation time (Rich reads NO_COLOR in Console.__init__).
def _rewrite_pre_separator(argv: list[str]) -> list[str]:
    """Rewrite wrapper-only tokens before ``--`` and leave literal args untouched."""
    result: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            result.extend(argv[i:])
            break
        if arg == "--no-color":
            os.environ["NO_COLOR"] = "1"
            i += 1
            continue
        if arg == "--legend":
            result.append(arg)
            next_arg = argv[i + 1] if i + 1 < len(argv) and argv[i + 1] != "--" else ""
            try:
                int(next_arg)
                result.append(next_arg)
                i += 2
            except ValueError:
                result.append("20")
                i += 1
            continue
        result.append(arg)
        i += 1
    return result


sys.argv = [sys.argv[0], *_rewrite_pre_separator(sys.argv[1:])]
if os.environ.get("TERM") == "dumb":
    os.environ["NO_COLOR"] = "1"
if os.environ.get("FORCE_COLOR"):
    os.environ.pop("NO_COLOR", None)

from dirplot.main import app  # noqa: E402


def main() -> None:
    app()


if __name__ == "__main__":
    main()
