"""VirtualPath abstraction for unified path handling.

This module provides a protocol that makes archives, S3, SSH paths, and
other non-filesystem sources transparent to the scanner. Instead of
treating archives as special cases, they become just another VirtualPath
implementation.
"""

from __future__ import annotations

import os
import stat
import tarfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class StatResult:
    """Minimal stat result for VirtualPath.

    Mirrors os.stat_result but only includes fields we need.
    """

    st_size: int
    st_mtime: float = 0.0
    st_mode: int = 0

    @property
    def is_dir(self) -> bool:
        return stat.S_ISDIR(self.st_mode)

    @property
    def is_file(self) -> bool:
        return stat.S_ISREG(self.st_mode)


@runtime_checkable
class VirtualPath(Protocol):
    """Protocol for path-like objects that can be scanned.

    Implementations provide a uniform interface for:
    - Local filesystem paths
    - Archive members
    - S3 objects
    - SSH remote paths
    - Any other hierarchical storage
    """

    @property
    def name(self) -> str:
        """The final component of the path."""
        ...

    @property
    def path(self) -> str:
        """Full path as string."""
        ...

    def iterdir(self) -> Iterator[VirtualPath]:
        """Iterate over entries in this directory."""
        ...

    def is_dir(self) -> bool:
        """Check if this path is a directory."""
        ...

    def is_file(self) -> bool:
        """Check if this path is a regular file."""
        ...

    def stat(self) -> StatResult:
        """Return stat information for this path."""
        ...

    def exists(self) -> bool:
        """Check if this path exists."""
        ...


class FileSystemPath:
    """VirtualPath implementation for local filesystem."""

    def __init__(self, path: Path | str):
        self._path = Path(path)

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def path(self) -> str:
        return str(self._path)

    def iterdir(self) -> Iterator[VirtualPath]:
        """Yield FileSystemPath for each entry."""
        try:
            for entry in os.scandir(self._path):
                # Skip symlinks (matching original scanner behavior)
                if entry.is_symlink():
                    continue
                yield FileSystemPath(entry.path)
        except PermissionError:
            return

    def is_dir(self) -> bool:
        return self._path.is_dir()

    def is_file(self) -> bool:
        return self._path.is_file()

    def is_symlink(self) -> bool:
        return self._path.is_symlink()

    def stat(self) -> StatResult:
        try:
            st = self._path.stat()
            return StatResult(
                st_size=st.st_size,
                st_mtime=st.st_mtime,
                st_mode=st.st_mode,
            )
        except OSError:
            # Return default stat on error (matching original scanner behavior)
            return StatResult(st_size=1, st_mtime=0, st_mode=0o644)

    def exists(self) -> bool:
        return self._path.exists()

    def __repr__(self) -> str:
        return f"FileSystemPath({self._path!r})"


class ZipMember:
    """VirtualPath implementation for ZIP archive members."""

    def __init__(self, archive: zipfile.ZipFile, name: str, parent: str = "", root_name: str = ""):
        self._archive = archive
        self._name = name  # Full path within archive
        self._parent = parent  # Parent directory path
        self._root_name = root_name  # Archive filename

    @property
    def name(self) -> str:
        """Return just the filename part."""
        return Path(self._name).name

    @property
    def path(self) -> str:
        """Return full virtual path including archive name."""
        if self._parent:
            return f"{self._root_name}/{self._parent}/{self.name}"
        return f"{self._root_name}/{self.name}"

    def iterdir(self) -> Iterator[VirtualPath]:
        """Yield ZipMember for each child in this directory."""
        # Find all entries that are direct children of this path
        prefix = self._name
        if not prefix.endswith("/"):
            prefix += "/"

        seen = set()
        for info in self._archive.infolist():
            if info.filename.startswith(prefix):
                # Get the relative part after our prefix
                rest = info.filename[len(prefix) :]
                child_name = rest.split("/", 1)[0] if "/" in rest else rest

                if child_name and child_name not in seen:
                    seen.add(child_name)
                    child_full = prefix + child_name
                    yield ZipMember(
                        self._archive,
                        child_full,
                        parent=prefix.rstrip("/"),
                        root_name=self._root_name,
                    )

    def is_dir(self) -> bool:
        """Check if this member is a directory."""
        # In ZIP, directories end with /
        if self._name.endswith("/"):
            return True
        # Or check if any entry has this as prefix
        return any(name.startswith(self._name + "/") for name in self._archive.namelist())

    def is_file(self) -> bool:
        """Check if this member is a file."""
        return not self.is_dir()

    def stat(self) -> StatResult:
        """Return stat-like info from ZIP metadata."""
        try:
            info = self._archive.getinfo(self._name)
            # Convert zip date_time to timestamp
            import time

            mtime = time.mktime(info.date_time + (0, 0, -1)) if info.date_time else 0
            return StatResult(
                st_size=info.file_size,
                st_mtime=mtime,
                st_mode=(stat.S_IFREG | 0o644) if self.is_file() else (stat.S_IFDIR | 0o755),
            )
        except KeyError:
            # Directory that doesn't have its own entry
            return StatResult(st_size=0, st_mode=stat.S_IFDIR | 0o755)

    def exists(self) -> bool:
        """Check if this member exists in the archive."""
        return self._name in self._archive.namelist() or self.is_dir()

    def __repr__(self) -> str:
        return f"ZipMember({self._name!r})"


class TarMember:
    """VirtualPath implementation for TAR archive members."""

    def __init__(self, archive: tarfile.TarFile, name: str, parent: str = "", root_name: str = ""):
        self._archive = archive
        self._name = name.rstrip("/")
        self._parent = parent
        self._root_name = root_name

    @property
    def name(self) -> str:
        return Path(self._name).name

    @property
    def path(self) -> str:
        if self._parent:
            return f"{self._root_name}/{self._parent}/{self.name}"
        return f"{self._root_name}/{self.name}"

    def iterdir(self) -> Iterator[VirtualPath]:
        """Yield TarMember for each child in this directory."""
        prefix = self._name + "/" if self._name else ""
        seen = set()

        for member in self._archive.getmembers():
            if member.name.startswith(prefix) and member.name != self._name:
                rest = member.name[len(prefix) :]
                child_name = rest.split("/", 1)[0] if "/" in rest else rest

                if child_name and child_name not in seen:
                    seen.add(child_name)
                    child_full = prefix + child_name
                    yield TarMember(
                        self._archive, child_full, parent=self._name, root_name=self._root_name
                    )

    def is_dir(self) -> bool:
        """Check if this member is a directory."""
        member = (
            self._archive.getmember(self._name) if self._name in self._archive.getnames() else None
        )
        if member and member.isdir():
            return True
        # Or check if any entry has this as prefix
        return any(m.name.startswith(self._name + "/") for m in self._archive.getmembers())

    def is_file(self) -> bool:
        """Check if this member is a file."""
        member = (
            self._archive.getmember(self._name) if self._name in self._archive.getnames() else None
        )
        if member:
            return member.isfile()
        return False

    def stat(self) -> StatResult:
        """Return stat-like info from TAR metadata."""
        try:
            member = self._archive.getmember(self._name)
            return StatResult(
                st_size=member.size,
                st_mtime=member.mtime,
                st_mode=(stat.S_IFDIR if member.isdir() else stat.S_IFREG) | member.mode,
            )
        except KeyError:
            return StatResult(st_size=0, st_mode=stat.S_IFDIR | 0o755)

    def exists(self) -> bool:
        """Check if this member exists."""
        return self._name in self._archive.getnames() or self.is_dir()

    def __repr__(self) -> str:
        return f"TarMember({self._name!r})"


class ArchiveRoot:
    """Root VirtualPath for archive files.

    Acts as the entry point for scanning an archive.
    """

    def __init__(self, path: Path | str):
        self._path = Path(path)
        self._archive: zipfile.ZipFile | tarfile.TarFile | None = None

    def __enter__(self) -> ArchiveRoot:
        """Open the archive for scanning."""
        name = self._path.name.lower()
        if name.endswith(".zip") or any(
            name.endswith(ext) for ext in [".jar", ".war", ".ear", ".whl", ".apk", ".epub"]
        ):
            self._archive = zipfile.ZipFile(self._path, "r")
        elif any(name.endswith(ext) for ext in [".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"]):
            self._archive = tarfile.open(self._path, "r:*")
        else:
            raise ValueError(f"Unsupported archive format: {self._path}")
        return self

    def __exit__(self, *args: object) -> None:
        """Close the archive."""
        if self._archive:
            self._archive.close()
            self._archive = None

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def path(self) -> str:
        return str(self._path)

    def iterdir(self) -> Iterator[VirtualPath]:
        """Yield top-level members of the archive."""
        if not self._archive:
            raise RuntimeError("Archive not opened. Use with-statement.")

        if isinstance(self._archive, zipfile.ZipFile):
            seen = set()
            for info in self._archive.infolist():
                # Get top-level name
                parts = info.filename.split("/")
                top = parts[0]
                if top and top not in seen:
                    seen.add(top)
                    yield ZipMember(
                        self._archive,
                        info.filename if len(parts) == 1 else top + "/",
                        root_name=self._path.name,
                    )
        elif isinstance(self._archive, tarfile.TarFile):
            seen = set()
            for member in self._archive.getmembers():
                parts = member.name.split("/")
                top = parts[0]
                if top and top not in seen:
                    seen.add(top)
                    yield TarMember(
                        self._archive,
                        member.name if len(parts) == 1 else top + "/",
                        root_name=self._path.name,
                    )

    def is_dir(self) -> bool:
        return True  # Archive root is always a directory

    def is_file(self) -> bool:
        return False

    def stat(self) -> StatResult:
        st = self._path.stat()
        return StatResult(
            st_size=st.st_size,
            st_mtime=st.st_mtime,
            st_mode=st.st_mode,
        )

    def exists(self) -> bool:
        return self._path.exists()


def open_path(path: str | Path) -> VirtualPath:
    """Open a path and return appropriate VirtualPath implementation.

    This is the factory function that routes to the correct implementation
    based on path type.

    Args:
        path: Path to open (filesystem or archive)

    Returns:
        VirtualPath implementation

    Example:
        # Filesystem
        vpath = open_path("/some/dir")
        for entry in vpath.iterdir():
            print(entry.name)

        # Archive (use as context manager)
        with open_path("archive.zip") as vpath:
            for entry in vpath.iterdir():
                print(entry.name)
    """
    path = Path(path)

    # Check if it's an archive
    from dirplot.archives import is_archive_path

    if is_archive_path(str(path)):
        return ArchiveRoot(path)

    # Default to filesystem
    return FileSystemPath(path)
