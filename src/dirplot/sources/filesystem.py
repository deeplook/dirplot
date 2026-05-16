"""Filesystem tree source implementation using VirtualPath."""

from __future__ import annotations

from pathlib import Path

from dirplot.scanner import Node, build_tree_multi_v2, build_tree_v2
from dirplot.sources import register_source
from dirplot.vpath import FileSystemPath


class FileSystemSource:
    """Tree source for local filesystem directories using VirtualPath.

    This implementation uses the VirtualPath abstraction, unifying
    filesystem handling with other path types.
    """

    @property
    def name(self) -> str:
        return "filesystem"

    def can_handle(self, path: str) -> bool:
        """Check if path is a local filesystem path.

        Returns True for paths that:
        - Don't start with a scheme (e.g., "github://", "s3://")
        - Aren't special URLs
        - Exist as a directory or can be resolved as a path
        """
        # Reject URLs with schemes
        if "://" in path:
            return False

        # Reject special prefixes
        special_prefixes = ("github://", "hg://", "ssh://", "s3://", "docker://", "pod://")
        # Accept any path-like string (we'll validate existence during scan)
        return not any(path.startswith(p) for p in special_prefixes)

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        """Scan a local directory using VirtualPath.

        Args:
            path: Directory path to scan.
            exclude: Glob patterns to skip.
            depth: Maximum recursion depth.

        Returns:
            Root node of the scanned tree.

        Raises:
            FileNotFoundError: If the path doesn't exist.
            NotADirectoryError: If the path isn't a directory.
        """
        root = FileSystemPath(path)

        if not root.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not root.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        return build_tree_v2(root, exclude=exclude, depth=depth)

    def get_display_name(self, path: str) -> str:
        """Get the resolved absolute path as display name."""
        return str(Path(path).resolve())

    def scan_multi(
        self,
        paths: list[str],
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        """Scan multiple directories under a common parent.

        This is a convenience method for scanning multiple roots.
        """
        vpaths = [FileSystemPath(p) for p in paths]
        return build_tree_multi_v2(vpaths, exclude=exclude, depth=depth)


# Register the source
filesystem_source = FileSystemSource()
register_source(filesystem_source)
