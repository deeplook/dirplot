"""Scanner v2 using VirtualPath abstraction.

This is a drop-in replacement for scanner.py that uses the VirtualPath
protocol, making archives transparent to the scanning logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dirplot.scanner import Node, NO_EXT

if TYPE_CHECKING:
    from dirplot.vpath import VirtualPath, StatResult
else:
    from dirplot.vpath import StatResult


def build_tree_v2(
    root: VirtualPath,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Build a Node tree from a VirtualPath.
    
    This function works identically for filesystem paths and archives,
    because VirtualPath provides a unified interface.
    
    Args:
        root: VirtualPath to scan (FileSystemPath, ArchiveRoot, etc.)
        exclude: Glob patterns to skip
        depth: Maximum recursion depth
    
    Returns:
        Root Node of the tree
    """
    if not root.exists():
        raise FileNotFoundError(f"Path not found: {root.path}")
    
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root.path}")
    
    children: list[Node] = []
    total = 0
    
    try:
        entries = list(root.iterdir())
    except PermissionError:
        return Node(name=root.name, path=Path(root.path), size=0, is_dir=True)
    
    for entry in sorted(entries, key=lambda e: e.name):
        # Apply exclude patterns
        if _matches_exclude(entry.name, exclude):
            continue
        
        if entry.is_dir():
            if depth is not None and depth <= 1:
                # Depth limit reached, create stub node
                child = Node(
                    name=entry.name,
                    path=Path(entry.path),
                    size=1,  # Minimum size for visibility
                    is_dir=True,
                )
            else:
                # Recurse into subdirectory
                child = build_tree_v2(
                    entry,
                    exclude,
                    None if depth is None else depth - 1
                )
        elif entry.is_file():
            stat = entry.stat()
            size = max(1, stat.st_size)
            ext = Path(entry.name).suffix.lower() if "." in entry.name else NO_EXT
            child = Node(
                name=entry.name,
                path=Path(entry.path),
                size=size,
                is_dir=False,
                extension=ext,
            )
        else:
            continue
        
        children.append(child)
        total += child.size
    
    return Node(
        name=root.name,
        path=Path(root.path),
        size=total,
        is_dir=True,
        children=children,
    )


def _matches_exclude(name: str, patterns: frozenset[str]) -> bool:
    """Check if name matches any exclude pattern.
    
    Simple glob matching - can be enhanced to match full paths.
    """
    import fnmatch
    
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        # Also check without leading **/
        if pattern.startswith("**/"):
            if fnmatch.fnmatch(name, pattern[3:]):
                return True
    return False


def build_tree_multi_v2(
    roots: list[VirtualPath],
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Build a Node tree from multiple VirtualPath roots.

    Scans each path independently, then wraps them under their common parent.

    Args:
        roots: List of VirtualPath roots to scan
        exclude: Glob patterns to skip
        depth: Maximum recursion depth

    Returns:
        Root Node containing all scanned paths
    """
    import os

    if not roots:
        raise ValueError("At least one root is required")

    # Find common parent
    resolved = [r.path for r in roots]
    common_str = os.path.commonpath(resolved) if len(resolved) > 1 else str(Path(resolved[0]).parent)
    common = Path(common_str)

    # Build synthetic root
    synthetic_root = type('SyntheticPath', (), {
        'name': common.name or '/',
        'path': str(common),
        'iterdir': lambda: iter(roots),
        'is_dir': lambda: True,
        'is_file': lambda: False,
        'stat': lambda: StatResult(st_size=0),
        'exists': lambda: True,
    })()

    return build_tree_v2(synthetic_root, exclude=exclude, depth=depth + 1 if depth else None)


def scan_any_v2(
    path: str | Path,
    *,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Scan any path (filesystem or archive) using VirtualPath.
    
    This is the main entry point that automatically detects the path type
    and uses the appropriate VirtualPath implementation.
    
    Args:
        path: Path to scan (filesystem directory or archive file)
        exclude: Glob patterns to skip
        depth: Maximum recursion depth
    
    Returns:
        Root Node of the scanned tree
    
    Example:
        # Scan filesystem
        tree = scan_any_v2("/home/user/projects")
        
        # Scan archive
        tree = scan_any_v2("archive.zip")
        
        # With options
        tree = scan_any_v2("src", exclude=frozenset({"*.pyc", ".git"}), depth=3)
    """
    from dirplot.vpath import open_path
    
    vpath = open_path(path)
    
    # If it's an archive, use context manager
    if hasattr(vpath, '__enter__'):
        with vpath:
            return build_tree_v2(vpath, exclude=exclude, depth=depth)
    
    # Filesystem path
    return build_tree_v2(vpath, exclude=exclude, depth=depth)
