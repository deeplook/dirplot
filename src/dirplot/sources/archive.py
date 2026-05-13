"""Archive tree source implementation using VirtualPath."""

from __future__ import annotations

from pathlib import Path

from dirplot.archives import is_archive_path
from dirplot.scanner import Node, build_tree_v2
from dirplot.sources import register_source
from dirplot.vpath import ArchiveRoot


class ArchiveSource:
    """Tree source for archive files (zip, tar, etc.) using VirtualPath.
    
    This implementation uses the VirtualPath abstraction, making archive
    handling transparent - archives are just another VirtualPath.
    """

    @property
    def name(self) -> str:
        return "archive"

    def can_handle(self, path: str) -> bool:
        """Check if path is an archive file."""
        return is_archive_path(path)

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        """Scan an archive file using VirtualPath.

        Args:
            path: Path to the archive file.
            exclude: Glob patterns to skip.
            depth: Maximum recursion depth.

        Returns:
            Root node representing the archive contents.
        """
        archive_path = Path(path)

        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {path}")

        # Use VirtualPath-based scanner
        with ArchiveRoot(archive_path) as root:
            return build_tree_v2(root, exclude=exclude, depth=depth)

    def get_display_name(self, path: str) -> str:
        """Get archive name with contents indicator."""
        archive_path = Path(path)
        return f"{archive_path.name} (archive)"


# Register the source
archive_source = ArchiveSource()
register_source(archive_source)
