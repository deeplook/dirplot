"""Path-pattern filtering utilities for --exclude and --size."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_UNIT_MAP: dict[str, int] = {
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "m": 1024**2,
    "mb": 1024**2,
    "g": 1024**3,
    "gb": 1024**3,
    "t": 1024**4,
    "tb": 1024**4,
}

_SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$")


@dataclass(frozen=True)
class SizeRange:
    min_bytes: int | None  # None = no lower bound
    max_bytes: int | None  # None = no upper bound


def parse_size(s: str) -> int:
    """Parse a size string like '10M', '500K', '1G' → bytes (powers of 1024)."""
    s = s.strip()
    m = _SIZE_RE.match(s)
    if not m:
        raise ValueError(f"Invalid size value: {s!r}")
    number, unit = m.group(1), m.group(2).lower()
    if unit == "":
        unit = "b"
    if unit not in _UNIT_MAP:
        valid = ", ".join(sorted(_UNIT_MAP))
        raise ValueError(f"Unknown size unit {m.group(2)!r} in {s!r}. Valid units: {valid}")
    return int(float(number) * _UNIT_MAP[unit])


def parse_size_range(s: str) -> SizeRange:
    """Parse a size range string → SizeRange.

    Forms:
      '10M..500M'  → min=10MiB, max=500MiB
      '100M..'     → min=100MiB, max=None
      '..50K'      → min=None, max=50KiB
      '1G'         → min=1GiB, max=1GiB
    """
    s = s.strip()
    if ".." in s:
        lo, hi = s.split("..", 1)
        lo, hi = lo.strip(), hi.strip()
        min_bytes = parse_size(lo) if lo else None
        max_bytes = parse_size(hi) if hi else None
        if min_bytes is not None and max_bytes is not None and min_bytes > max_bytes:
            raise ValueError(
                f"Invalid size range {s!r}: lower bound ({lo}) exceeds upper bound ({hi})"
            )
        return SizeRange(min_bytes=min_bytes, max_bytes=max_bytes)
    # Single value → exact match
    exact = parse_size(s)
    return SizeRange(min_bytes=exact, max_bytes=exact)


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
