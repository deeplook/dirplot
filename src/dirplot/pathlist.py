"""Parse path lists produced by ``tree`` and ``find`` into Path objects."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

# Tree box-drawing characters used to detect tree format
_TREE_CHARS = re.compile(r"[├└│]")
# Strip leading tree decorations (box-drawing + spaces + dashes)
_TREE_PREFIX = re.compile(r"^[│ ]*[├└]──\s*")
# Strip optional [size] column emitted by tree -s / tree -h
_TREE_SIZE = re.compile(r"^\[\s*[\d.,]+[KMGTPkBb]*\s*\]\s*")
# Trailing comment: ` # ...` (space-hash-space) at the end of a name.
# Filenames containing '#' without a leading space are left intact.
_TRAILING_COMMENT = re.compile(r"\s+#\s.*$")


def _strip_comment(name: str) -> str:
    """Remove a trailing ``# comment`` from a tree line name."""
    return _TRAILING_COMMENT.sub("", name).rstrip()


def detect_format(lines: list[str]) -> Literal["find", "tree", "tree_f"]:
    """Return the format of a path list.

    * ``"tree"``   – ``tree`` default output (indented names, first line is root)
    * ``"tree_f"`` – ``tree -f`` output (tree decorations + full paths)
    * ``"find"``   – ``find`` output (one path per line, no decorations)
    """
    for line in lines:
        if _TREE_CHARS.search(line):
            # Strip tree decoration and optional size bracket to get the name/path
            name = _TREE_PREFIX.sub("", line).strip()
            name = _TREE_SIZE.sub("", name).strip()
            name = _strip_comment(name)
            if name.startswith("/"):
                return "tree_f"
            return "tree"
    return "find"


def parse_find(lines: list[str]) -> list[Path]:
    """Parse ``find`` output: one path per line."""
    paths: list[Path] = []
    for line in lines:
        line = line.rstrip("\n")
        if not line or line.isspace():
            continue
        paths.append(Path(line))
    return paths


def parse_tree(lines: list[str]) -> list[Path]:
    """Parse ``tree`` or ``tree -f`` or ``tree -s/-h`` output into paths.

    Handles:
    * ``tree``       – first line is root path, rest are indented names
    * ``tree -f``    – box-drawing decorations followed by full absolute paths
    * ``tree -s/-h`` – optional ``[size]`` column before the name
    * ``tree --noreport`` compatible (summary lines like "N directories, M files" are skipped)
    """
    non_empty = [line.rstrip("\n") for line in lines if line.strip()]
    if not non_empty:
        return []

    fmt = detect_format(non_empty)

    if fmt == "tree_f":
        return _parse_tree_full_paths(non_empty)

    # Default tree format: first line is root (may have [size] prefix with tree -s)
    root_line = _TREE_SIZE.sub("", non_empty[0].strip()).strip()
    root_line = _strip_comment(root_line)
    root = Path(root_line)

    paths: list[Path] = [root]
    # Stack maps depth → current Path at that depth
    stack: dict[int, Path] = {0: root}

    for line in non_empty[1:]:
        if not _TREE_CHARS.search(line):
            # Could be a summary line ("3 directories, 5 files") – skip
            continue

        # Determine depth by counting leading │/space groups (each unit = 4 chars)
        prefix_match = re.match(r"^([│ ]*)[├└]", line)
        if not prefix_match:
            continue
        indent = prefix_match.group(1)
        depth = len(indent) // 4 + 1  # depth 1 = direct child of root

        # Strip tree decoration
        name = _TREE_PREFIX.sub("", line).strip()
        # Strip optional [size] column
        name = _TREE_SIZE.sub("", name).strip()
        # Strip trailing comment
        name = _strip_comment(name)
        if not name:
            continue

        parent = stack.get(depth - 1, root)
        full_path = parent / name
        stack[depth] = full_path
        paths.append(full_path)

    return paths


def _parse_tree_full_paths(lines: list[str]) -> list[Path]:
    """Parse ``tree -f`` output where each decorated line contains a full path."""
    paths: list[Path] = []
    for line in lines:
        if _TREE_CHARS.search(line):
            name = _TREE_PREFIX.sub("", line).strip()
            name = _TREE_SIZE.sub("", name).strip()
            name = _strip_comment(name)
            if name:
                paths.append(Path(name))
        else:
            # First line (root) or summary line
            stripped = line.strip()
            if stripped.startswith("/"):
                paths.append(Path(stripped))
    return paths


def minimal_roots(paths: list[Path]) -> list[Path]:
    """Return the minimal set of paths: drop any path whose ancestor is already present.

    This prevents passing both ``/dir`` and ``/dir/file`` to ``build_tree_multi``,
    which would cause an ``IndexError`` in the combine step.
    """
    resolved = sorted({p.resolve() for p in paths}, key=lambda p: len(p.parts))
    result: list[Path] = []
    for p in resolved:
        if not any(p != r and p.is_relative_to(r) for r in result):
            result.append(p)
    return result


def parse_pathlist(lines: list[str]) -> list[Path]:
    """Auto-detect format and return the minimal set of root paths.

    Dispatches to :func:`parse_find` or :func:`parse_tree` based on content.
    Applies :func:`minimal_roots` to deduplicate ancestor/descendant pairs.
    """
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return []
    fmt = detect_format(non_empty)
    raw = parse_find(lines) if fmt == "find" else parse_tree(lines)
    return minimal_roots(raw)
