"""Archive file scanning (zip, tar, 7z, rar, libarchive) as virtual directory trees."""

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
        ".tzst",
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
        ".nupkg",
        ".vsix",
        ".ipa",
        ".aab",
        # libarchive-handled formats
        ".dmg",
        ".pkg",
        ".img",
        ".iso",
        ".xar",
        ".cpio",
        ".rpm",
        ".cab",
        ".lha",
        ".lzh",
        ".a",
        ".ar",
    }
)
COMPOUND_SUFFIXES = frozenset({".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"})


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
        name.endswith(s)
        for s in (
            ".zip",
            ".jar",
            ".war",
            ".ear",
            ".whl",
            ".apk",
            ".epub",
            ".xpi",
            ".nupkg",
            ".vsix",
            ".ipa",
            ".aab",
        )
    ):
        return "zip"
    if name.endswith(".7z"):
        return "7z"
    if name.endswith(".rar"):
        return "rar"
    if any(
        name.endswith(s)
        for s in (
            ".dmg",
            ".pkg",
            ".img",
            ".iso",
            ".xar",
            ".cpio",
            ".rpm",
            ".cab",
            ".lha",
            ".lzh",
            ".a",
            ".ar",
            ".tar.zst",
            ".tzst",
        )
    ):
        return "libarchive"
    raise ValueError(f"Unsupported archive: {path.name}")


class PasswordRequired(Exception):
    """Raised when an archive is encrypted and no password has been supplied."""


def _root_name(path: Path) -> str:
    """Strip archive suffix(es) to get the display name."""
    name = path.name.lower()
    for suf in COMPOUND_SUFFIXES:
        if name.endswith(suf):
            return Path(path.stem).stem
    return path.stem


def _read_zip(path: Path, password: str | None = None) -> list[tuple[str, int, bool]]:
    """Return (member_path, size, is_dir) tuples for a zip archive.

    ZIP central-directory metadata (names, sizes) is stored unencrypted even in
    password-protected archives, so a password is rarely needed here.  It is
    accepted for completeness and forwarded to ZipFile.setpassword().
    """
    entries: list[tuple[str, int, bool]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            if password is not None:
                zf.setpassword(password.encode())
            for info in zf.infolist():
                is_dir = info.filename.endswith("/")
                member_path = info.filename.rstrip("/")
                size = info.file_size
                entries.append((member_path, size, is_dir))
    except RuntimeError as exc:
        if "encrypted" in str(exc).lower() or "password" in str(exc).lower():
            raise PasswordRequired(path.name) from exc
        raise
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


def _read_rar(path: Path, password: str | None = None) -> list[tuple[str, int, bool]]:
    """Return (member_path, size, is_dir) tuples for a RAR archive."""
    import rarfile

    entries: list[tuple[str, int, bool]] = []
    try:
        with rarfile.RarFile(path) as rf:
            if password is not None:
                rf.setpassword(password)
            for info in rf.infolist():
                is_dir = info.is_dir()
                member_path = info.filename.rstrip("/")
                size = info.file_size
                entries.append((member_path, size, is_dir))
    except (rarfile.PasswordRequired, rarfile.RarWrongPassword) as exc:
        raise PasswordRequired(path.name) from exc
    return entries


def _read_libarchive(path: Path, password: str | None = None) -> list[tuple[str, int, bool]]:
    """Return (member_path, size, is_dir) tuples using the libarchive-c package.

    Handles formats not covered by stdlib or bundled libraries: .iso, .cpio,
    .xar, .pkg, .dmg, .img, .rpm, .cab, .lha/.lzh, .a/.ar, .tar.zst/.tzst,
    and any other format that the installed system libarchive supports.

    Raises:
        ImportError: if ``libarchive-c`` is not installed.
        PasswordRequired: if the archive is encrypted and no password was given.
        OSError: if the archive cannot be opened (unsupported format, corrupted).
    """
    try:
        import libarchive
    except ImportError as exc:
        raise ImportError(
            f"libarchive-c is required to read {path.suffix} archives. "
            "Install it with: pip install libarchive-c\n"
            "(The system libarchive library must also be present: "
            "brew install libarchive  or  apt install libarchive-dev)"
        ) from exc

    entries: list[tuple[str, int, bool]] = []
    try:
        with libarchive.file_reader(str(path), passphrase=password) as archive:
            for entry in archive:
                if entry.issym or entry.islnk:
                    continue
                member_path = entry.pathname.rstrip("/")
                # Skip root-directory placeholders ('.', '', '/')
                if not member_path or member_path == ".":
                    continue
                # Strip leading './'
                while member_path.startswith("./"):
                    member_path = member_path[2:]
                if not member_path:
                    continue
                is_dir = entry.isdir
                size = entry.size or 0
                entries.append((member_path, size, is_dir))
    except Exception as exc:
        msg = str(exc).lower()
        if "passphrase" in msg or "password" in msg or "encrypted" in msg:
            raise PasswordRequired(path.name) from exc
        raise OSError(
            f"Cannot open {path.name}: {exc}\n"
            "The file format may not be supported by the installed libarchive, "
            "or the archive may be encrypted/corrupted."
        ) from exc
    return entries


def _read_7z(path: Path, password: str | None = None) -> list[tuple[str, int, bool]]:
    """Return (member_path, size, is_dir) tuples for a 7z archive."""
    import py7zr

    entries: list[tuple[str, int, bool]] = []
    try:
        with py7zr.SevenZipFile(path, mode="r", password=password) as sz:
            for info in sz.list():
                member_path = info.filename.rstrip("/")
                is_dir = info.is_directory
                size = info.uncompressed or 0
                entries.append((member_path, size, is_dir))
    except py7zr.exceptions.PasswordRequired as exc:
        raise PasswordRequired(path.name) from exc
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
    password: str | None = None,
) -> Node:
    """Read an archive file and return a Node tree of its contents.

    Args:
        path: Path to the archive file.
        exclude: Set of member names or paths to skip.
        depth: Maximum recursion depth. ``None`` means unlimited.
        password: Passphrase for encrypted archives. When ``None`` and the
            archive is encrypted, ``PasswordRequired`` is raised so the caller
            can prompt the user and retry.
    """
    kind = _archive_type(path)
    if kind == "zip":
        entries = _read_zip(path, password)
    elif kind == "tar":
        entries = _read_tar(path)
    elif kind == "7z":
        entries = _read_7z(path, password)
    elif kind == "libarchive":
        entries = _read_libarchive(path, password)
    else:
        entries = _read_rar(path, password)

    root_name = _root_name(path)
    return _entries_to_tree(entries, root_name, exclude, depth)
