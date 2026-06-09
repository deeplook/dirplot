"""Archive tree source implementation using VirtualPath."""

from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path

from dirplot.archives import is_archive_path
from dirplot.scanner import Node, build_tree_v2
from dirplot.sources import register_source
from dirplot.vpath import ArchiveRoot

_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


def _is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def _download_url(url: str, dest: Path, max_bytes: int = _MAX_DOWNLOAD_BYTES) -> None:
    """Download *url* to *dest*, raising ValueError if Content-Length or actual
    bytes received exceed *max_bytes*."""
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        length = resp.headers.get("Content-Length")
        if length is not None and int(length) > max_bytes:
            raise ValueError(
                f"Remote archive too large: {int(length) // (1024 * 1024)} MB "
                f"(limit {max_bytes // (1024 * 1024)} MB)"
            )
        received = 0
        with dest.open("wb") as f:
            while chunk := resp.read(65536):
                received += len(chunk)
                if received > max_bytes:
                    raise ValueError(
                        f"Remote archive exceeds {max_bytes // (1024 * 1024)} MB limit"
                    )
                f.write(chunk)


class ArchiveSource:
    """Tree source for archive files (zip, tar, etc.) using VirtualPath.

    Accepts local archive paths and HTTP(S) URLs pointing to archives.
    """

    @property
    def name(self) -> str:
        return "archive"

    def can_handle(self, path: str) -> bool:
        """Check if path is an archive file or a URL pointing to one."""
        return is_archive_path(path.split("?")[0])

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        """Scan an archive file using VirtualPath.

        Args:
            path: Local path or HTTP(S) URL of the archive.
            exclude: Glob patterns to skip.
            depth: Maximum recursion depth.

        Returns:
            Root node representing the archive contents.
        """
        if _is_url(path):
            suffix = Path(path.split("?")[0]).suffix or ".tmp"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                _download_url(path, tmp_path)
                with ArchiveRoot(tmp_path) as root:
                    return build_tree_v2(root, exclude=exclude, depth=depth)
            finally:
                tmp_path.unlink(missing_ok=True)

        archive_path = Path(path)
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {path}")

        with ArchiveRoot(archive_path) as root:
            return build_tree_v2(root, exclude=exclude, depth=depth)

    def get_display_name(self, path: str) -> str:
        """Get archive name with contents indicator."""
        name = Path(path.split("?")[0]).name
        return f"{name} (archive)"


# Register the source
archive_source = ArchiveSource()
register_source(archive_source)
