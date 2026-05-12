"""Path-pattern filtering utilities for --exclude."""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath


def matches_exclude(rel_path: str, patterns: frozenset[str]) -> bool:
    """Return True if *rel_path* matches any pattern in *patterns*.

    Pattern semantics:
    - No ``/``: matched as a glob against every path component.
      ``".git"`` and ``"*.egg-info"`` both skip matching dirs anywhere in the tree.
    - Contains ``/`` but no ``**``: fnmatch against the full relative path.
      ``"src/vendor"`` matches exactly that subtree.
    - Contains ``**``: full glob matching with ``**`` spanning multiple components.
      ``"**/__pycache__"`` skips ``__pycache__`` at any depth.
    """
    if not patterns:
        return False
    parts = tuple(PurePosixPath(rel_path).parts)
    for pattern in patterns:
        if "/" not in pattern:
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
        elif "**" not in pattern:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        else:
            pat_parts = tuple(PurePosixPath(pattern).parts)
            if _glob_match(parts, pat_parts):
                return True
    return False


def _glob_match(path_parts: tuple[str, ...], pat_parts: tuple[str, ...]) -> bool:
    """Recursive glob matcher supporting ``**``."""
    if not pat_parts:
        return not path_parts
    if pat_parts[0] == "**":
        return any(_glob_match(path_parts[i:], pat_parts[1:]) for i in range(len(path_parts) + 1))
    if not path_parts:
        return False
    if fnmatch.fnmatch(path_parts[0], pat_parts[0]):
        return _glob_match(path_parts[1:], pat_parts[1:])
    return False
