"""Directory scanning and tree construction."""

import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Node:
    """A node in the directory tree."""

    name: str
    path: Path
    size: int  # bytes; sum of all descendants for directories
    is_dir: bool
    extension: str = ""
    children: list["Node"] = field(default_factory=list)
    original_size: int = 0  # set by apply_log_sizes; 0 means size was never transformed


def build_tree(
    root: Path,
    exclude: frozenset[Path] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Recursively build a Node tree from *root*.

    Args:
        root: Directory to scan.
        exclude: Resolved absolute paths to skip entirely.
        depth: Maximum recursion depth. ``None`` means unlimited.
            ``depth=1`` lists direct children without recursing into subdirs.

    Returns:
        Root node whose ``size`` is the total size of all descendants.
    """
    children: list[Node] = []
    total = 0
    try:
        entries = list(root.iterdir())
    except PermissionError:
        return Node(name=root.name, path=root, size=0, is_dir=True)

    for entry in sorted(entries, key=lambda e: e.name):
        if entry.resolve() in exclude:
            continue
        if entry.is_symlink():
            continue
        if entry.is_dir():
            if depth is not None and depth <= 1:
                child = Node(name=entry.name, path=entry, size=1, is_dir=True)
            else:
                child = build_tree(entry, exclude, None if depth is None else depth - 1)
        elif entry.is_file():
            try:
                size = max(1, entry.stat().st_size)
            except OSError:
                size = 1
            ext = entry.suffix.lower() if entry.suffix else "(no ext)"
            child = Node(name=entry.name, path=entry, size=size, is_dir=False, extension=ext)
        else:
            continue
        children.append(child)
        total += child.size

    return Node(name=root.name, path=root, size=total, is_dir=True, children=children)


def apply_log_sizes(node: Node) -> None:
    """Replace file sizes with their natural log in-place, then recompute directory totals.

    The original byte count is preserved in ``node.original_size`` so that renderers
    can display the real size rather than the log-transformed layout value.
    """
    if not node.is_dir:
        node.original_size = node.size
        node.size = max(1, round(math.log(max(1, node.size))))
        return
    node.original_size = node.size  # save real total before recomputing
    for child in node.children:
        apply_log_sizes(child)
    node.size = sum(c.size for c in node.children)


def count_nodes(node: Node) -> tuple[int, int]:
    """Return *(n_files, n_dirs)* for the subtree rooted at *node*.

    *node* itself is not counted — only its descendants.
    """
    files = 0
    dirs = 0
    for child in node.children:
        if child.is_dir:
            dirs += 1
            cf, cd = count_nodes(child)
            files += cf
            dirs += cd
        else:
            files += 1
    return files, dirs


def collect_extensions(node: Node) -> list[str]:
    """Return a flat list of file extensions under *node*."""
    if not node.is_dir:
        return [node.extension]
    exts: list[str] = []
    for child in node.children:
        exts.extend(collect_extensions(child))
    return exts
