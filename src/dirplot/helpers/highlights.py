"""Utilities for resolving --highlight CLI specs to a highlights dict."""

from pathlib import PurePath


def resolve_highlight_specs(specs: list[str], paths: list[str]) -> dict[str, str]:
    """Match *specs* against *paths* and return a highlights dict.

    Each spec is either ``"pattern"`` (defaults to red) or ``"pattern@color"``.
    *paths* are absolute posix path strings (as stored in node/rect maps).

    Directory patterns (e.g. ``"src/dirplot"``) are matched against the path
    itself first, then against each of its ancestor directories — so a folder
    pattern works even when *paths* contains only file paths (as in git/hg
    animation frames where only tracked files are listed).
    """
    result: dict[str, str] = {}
    for spec in specs:
        if "@" in spec:
            pattern, color = spec.rsplit("@", 1)
        else:
            pattern, color = spec, "red"
        for p in paths:
            pure = PurePath(p)
            if pure.match(pattern):
                result[p] = color
                continue
            # Also check ancestor directories so that a folder pattern like
            # "src/dirplot" highlights the directory tile even when *paths*
            # contains only file paths.
            for parent in pure.parents:
                if parent.match(pattern):
                    result[parent.as_posix()] = color
                    break
    return result
