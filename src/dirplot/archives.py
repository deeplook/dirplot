"""Archive file scanning (zip, tar, 7z, rar) as virtual directory trees."""

from __future__ import annotations

import tarfile
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath

from dirplot.scanner import Node

ARCHIVE_SUFFIXES = frozenset(
    {
        ".zip",
        ".tar",
        ".tgz",
        ".tbz2",
        ".txz",
        ".7z",
        ".rar",
        # ZIP-based formats
        ".jar",
        ".war",
        ".ear",
        ".whl",
        ".apk",
        ".epub",
        ".xpi",
    }
)
COMPOUND_SUFFIXES = frozenset({".tar.gz", ".tar.bz2", ".tar.xz"})


def is_archive_path(s: str) -> bool:
    """Return True if *s* ends with a known archive extension."""
    name = Path(s).name.lower()
    return any(name.endswith(suf) for suf in COMPOUND_SUFFIXES | ARCHIVE_SUFFIXES)


def _archive_type(path: Path) -> str:
    name = path.name.lower()
    if any(
        name.endswith(s)
        for s in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".tar")
    ):
        return "tar"
    if any(
        name.endswith(s) for s in (".zip", ".jar", ".war", ".ear", ".whl", ".apk", ".epub", ".xpi")
    ):
        return "zip"
    if name.endswith(".7z"):
        return "7z"
    if name.endswith(".rar"):
        return "rar"
    raise ValueError(f"Unsupported archive: {path.name}")


def _root_name(path: Path) -> str:
    """Strip archive suffix(es) to get the display name."""
    name = path.name.lower()
    for suf in COMPOUND_SUFFIXES:
        if name.endswith(suf):
            return Path(path.stem).stem
    return path.stem


def _read_zip(path: Path) -> list[tuple[str, int, bool]]:
    """Return (member_path, size, is_dir) tuples for a zip archive."""
    entries: list[tuple[str, int, bool]] = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            is_dir = info.filename.endswith("/")
            member_path = info.filename.rstrip("/")
            size = info.file_size
            entries.append((member_path, size, is_dir))
    return entries


def _read_tar(path: Path) -> list[tuple[str, int, bool]]:
    """Return (member_path, size, is_dir) tuples for a tar archive, skipping symlinks."""
    entries: list[tuple[str, int, bool]] = []
    with tarfile.open(path) as tf:
        for member in tf.getmembers():
            if member.issym() or member.islnk():
                continue
            member_path = member.name
            while member_path.startswith("./"):
                member_path = member_path[2:]
            member_path = member_path.lstrip("/")
            if not member_path:
                continue
            is_dir = member.isdir()
            size = member.size
            entries.append((member_path, size, is_dir))
    return entries


def _read_rar(path: Path) -> list[tuple[str, int, bool]]:
    """Return (member_path, size, is_dir) tuples for a RAR archive."""
    import rarfile

    entries: list[tuple[str, int, bool]] = []
    with rarfile.RarFile(path) as rf:
        for info in rf.infolist():
            is_dir = info.is_dir()
            member_path = info.filename.rstrip("/")
            size = info.file_size
            entries.append((member_path, size, is_dir))
    return entries


def _read_7z(path: Path) -> list[tuple[str, int, bool]]:
    """Return (member_path, size, is_dir) tuples for a 7z archive."""
    import py7zr

    entries: list[tuple[str, int, bool]] = []
    with py7zr.SevenZipFile(path, mode="r") as sz:
        for info in sz.list():
            member_path = info.filename.rstrip("/")
            is_dir = info.is_directory
            size = info.uncompressed or 0
            entries.append((member_path, size, is_dir))
    return entries


def _entries_to_tree(
    entries: list[tuple[str, int, bool]],
    root_name: str,
    exclude: frozenset[str],
    depth: int | None,
) -> Node:
    """Build a Node tree from a flat list of (path, size, is_dir) tuples."""
    # Collect all entries and synthesize any missing intermediate directories
    all_entries: dict[str, tuple[int, bool]] = {}
    for member_path, size, is_dir in entries:
        if not member_path:
            continue
        all_entries[member_path] = (size, is_dir)
        for ancestor in PurePosixPath(member_path).parents:
            anc_str = str(ancestor)
            if anc_str not in (".", "") and anc_str not in all_entries:
                all_entries[anc_str] = (0, True)

    by_parent: dict[str, list[tuple[str, int, bool, str]]] = defaultdict(list)
    for member_path, (size, is_dir) in all_entries.items():
        p = PurePosixPath(member_path)
        parent = str(p.parent)
        if parent == ".":
            parent = ""
        name = p.name
        by_parent[parent].append((member_path, size, is_dir, name))

    def recurse(prefix: str, name: str, current_depth: int | None) -> Node:
        children: list[Node] = []
        for member_path, size, is_dir, child_name in sorted(
            by_parent.get(prefix, []), key=lambda t: t[3]
        ):
            if child_name.startswith("."):
                continue
            if child_name in exclude or member_path in exclude:
                continue
            if is_dir:
                if current_depth is not None and current_depth <= 1:
                    child: Node = Node(
                        name=child_name,
                        path=Path(member_path),
                        size=1,
                        is_dir=True,
                        extension="",
                    )
                else:
                    child = recurse(
                        member_path,
                        child_name,
                        None if current_depth is None else current_depth - 1,
                    )
            else:
                ext = PurePosixPath(child_name).suffix.lower() or "(no ext)"
                child = Node(
                    name=child_name,
                    path=Path(member_path),
                    size=max(1, size),
                    is_dir=False,
                    extension=ext,
                )
            children.append(child)

        total = sum(c.size for c in children) or 1
        return Node(
            name=name,
            path=Path(prefix) if prefix else Path(root_name),
            size=total,
            is_dir=True,
            extension="",
            children=children,
        )

    return recurse("", root_name, depth)


def build_tree_archive(
    path: Path,
    *,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Read an archive file and return a Node tree of its contents.

    Args:
        path: Path to the archive file.
        exclude: Set of member names or paths to skip.
        depth: Maximum recursion depth. ``None`` means unlimited.
    """
    kind = _archive_type(path)
    if kind == "zip":
        entries = _read_zip(path)
    elif kind == "tar":
        entries = _read_tar(path)
    elif kind == "7z":
        entries = _read_7z(path)
    else:
        entries = _read_rar(path)

    root_name = _root_name(path)
    return _entries_to_tree(entries, root_name, exclude, depth)
