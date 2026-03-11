"""Entry point for ``python -m dirplot``."""

import sys

from dirplot.main import app


def _inject_legend_default(argv: list[str]) -> list[str]:
    """If ``--legend`` appears without a following integer, insert ``20``.

    This lets users write ``--legend`` as a bare flag (meaning "use the
    default of 20 entries") while also allowing ``--legend 10`` for a
    custom limit.
    """
    result: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--legend":
            result.append(arg)
            next_arg = argv[i + 1] if i + 1 < len(argv) else ""
            try:
                int(next_arg)
                result.append(next_arg)
                i += 2
            except ValueError:
                result.append("20")
                i += 1
        else:
            result.append(arg)
            i += 1
    return result


def main() -> None:
    sys.argv[1:] = _inject_legend_default(sys.argv[1:])
    app()


if __name__ == "__main__":
    main()
