"""Archive tree source implementation."""

from __future__ import annotations

from pathlib import Path

from dirplot.archives import build_tree_archive, is_archive_path
from dirplot.scanner import Node
from dirplot.sources import register_source


class ArchiveSource:
    """Tree source for archive files (zip, tar, etc.)."""

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
        """Scan an archive file.

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

        # Use the existing build_tree_archive function
        return build_tree_archive(
            archive_path,
            exclude=exclude,
            depth=depth,
        )

    def get_display_name(self, path: str) -> str:
        """Get archive name with contents indicator."""
        archive_path = Path(path)
        return f"{archive_path.name} (archive)"


# Register the source
archive_source = ArchiveSource()
register_source(archive_source)
