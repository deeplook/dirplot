"""Unified tree source interface for dirplot.

This module provides a common protocol for all directory tree sources,
including filesystem, git, mercurial, archives, SSH, S3, and more.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from dirplot.scanner import Node


@runtime_checkable
class TreeSource(Protocol):
    """Protocol for directory tree sources.

    Implementations provide a unified interface for scanning trees from
    various sources: filesystem, git, mercurial, archives, remote storage, etc.
    """

    @property
    def name(self) -> str:
        """Human-readable name of this source type."""
        ...

    def can_handle(self, path: str) -> bool:
        """Check if this source can handle the given path.

        Args:
            path: The path/URL to check (e.g., ".", "github://owner/repo",
                  "s3://bucket/path", "archive.zip")

        Returns:
            True if this source can scan the path, False otherwise.
        """
        ...

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        """Scan the given path and return a Node tree.

        Args:
            path: The path/URL to scan.
            exclude: Glob patterns to skip (names, relative paths, or ``**`` globs).
            depth: Maximum recursion depth. None means unlimited.

        Returns:
            Root node whose ``size`` is the total size of all descendants.

        Raises:
            ValueError: If the path cannot be handled by this source.
            RuntimeError: If scanning fails (network error, permission denied, etc.)
        """
        ...

    def get_display_name(self, path: str) -> str:
        """Get a human-readable display name for this path.

        Args:
            path: The path/URL.

        Returns:
            A display name suitable for UI (e.g., window title, metadata).
        """
        ...


class SourceRegistry:
    """Registry for tree sources with auto-discovery.

    Sources are tried in registration order. Register more specific sources
    (github://, s3://) before generic ones (filesystem).
    """

    def __init__(self):
        self._sources: list[TreeSource] = []

    def register(self, source: TreeSource) -> None:
        """Register a tree source."""
        self._sources.append(source)

    def find_source(self, path: str) -> TreeSource:
        """Find the first source that can handle the given path.

        Args:
            path: The path/URL to scan.

        Returns:
            The first compatible TreeSource.

        Raises:
            ValueError: If no source can handle the path.
        """
        for source in self._sources:
            if source.can_handle(path):
                return source
        raise ValueError(f"No source can handle path: {path}")

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        """Scan using the first compatible source.

        This is a convenience method that finds a source and scans.
        """
        source = self.find_source(path)
        return source.scan(path, exclude=exclude, depth=depth)

    def get_display_name(self, path: str) -> str:
        """Get display name using the first compatible source."""
        source = self.find_source(path)
        return source.get_display_name(path)

    @property
    def sources(self) -> list[TreeSource]:
        """List all registered sources."""
        return self._sources.copy()


# Global registry instance
registry = SourceRegistry()


def register_source(source: TreeSource) -> TreeSource:
    """Decorator to register a tree source.

    Example:
        @register_source
        class MySource:
            ...
    """
    registry.register(source)
    return source


def scan_any(
    path: str,
    *,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Scan any supported path type.

    This is the main entry point for scanning. It automatically
    detects the source type and uses the appropriate scanner.

    Args:
        path: Path, URL, or identifier to scan.
        exclude: Glob patterns to skip.
        depth: Maximum recursion depth.

    Returns:
        Root node of the scanned tree.

    Raises:
        ValueError: If no source can handle the path.
    """
    return registry.scan(path, exclude=exclude, depth=depth)


# Import and register built-in sources
# These imports register the sources automatically
from dirplot.sources import filesystem

# Import optional sources (these may fail if dependencies are missing)
try:
    from dirplot.sources import archive
except ImportError:
    pass

try:
    from dirplot.sources import github
except ImportError:
    pass

try:
    from dirplot.sources import ssh
except ImportError:
    pass

__all__ = [
    "TreeSource",
    "SourceRegistry",
    "registry",
    "register_source",
    "scan_any",
]
