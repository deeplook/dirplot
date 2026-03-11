"""Tests for archive scanning (zip, tar.gz, 7z, rar)."""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from dirplot.archives import PasswordRequired, build_tree_archive, is_archive_path
from tests.conftest import ENCRYPTED_PASSWORD

# ---------------------------------------------------------------------------
# is_archive_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "foo.zip",
        "foo.tar",
        "foo.tar.gz",
        "foo.tgz",
        "foo.tar.bz2",
        "foo.tbz2",
        "foo.tar.xz",
        "foo.txz",
        "foo.7z",
        "foo.rar",
        "foo.jar",
        "foo.war",
        "foo.ear",
        "foo.whl",
        "foo.apk",
        "foo.epub",
        "foo.xpi",
        "FOO.ZIP",  # case-insensitive
        # more ZIP aliases
        "foo.nupkg",
        "foo.vsix",
        "foo.ipa",
        "foo.aab",
        # tar.zst
        "foo.tar.zst",
        "foo.tzst",
        # libarchive-handled formats
        "foo.dmg",
        "foo.pkg",
        "foo.img",
        "foo.iso",
        "foo.xar",
        "foo.cpio",
        "foo.rpm",
        "foo.cab",
        "foo.lha",
        "foo.lzh",
        "foo.a",
        "foo.ar",
    ],
)
def test_is_archive_path_true(name: str) -> None:
    assert is_archive_path(name)
    assert is_archive_path(f"/some/dir/{name}")


@pytest.mark.parametrize("name", ["foo.py", "foo.txt", "foo", "foo.tar.bad", ""])
def test_is_archive_path_false(name: str) -> None:
    assert not is_archive_path(name)


# ---------------------------------------------------------------------------
# Helpers to build in-memory archives
# ---------------------------------------------------------------------------


def _make_zip(tmp_path: Path, members: list[tuple[str, bytes]]) -> Path:
    """Write a zip to tmp_path/test.zip and return the path."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        for name, data in members:
            zf.writestr(name, data)
    dest = tmp_path / "test.zip"
    dest.write_bytes(buf.getvalue())
    return dest


def _make_tar_gz(tmp_path: Path, members: list[tuple[str, bytes]]) -> Path:
    """Write a tar.gz to tmp_path/test.tar.gz and return the path."""
    buf = io.BytesIO()
    with tarfile.open(mode="w:gz", fileobj=buf) as tf:
        for name, data in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    dest = tmp_path / "test.tar.gz"
    dest.write_bytes(buf.getvalue())
    return dest


# ---------------------------------------------------------------------------
# zip tests
# ---------------------------------------------------------------------------


def test_zip_flat(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path, [("a.txt", b"hello"), ("b.py", b"world!")])
    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert names == {"a.txt", "b.py"}
    assert node.size > 0


def test_zip_nested(tmp_path: Path) -> None:
    archive = _make_zip(
        tmp_path,
        [
            ("src/foo.py", b"x" * 100),
            ("src/bar.py", b"y" * 200),
            ("README.md", b"z" * 50),
        ],
    )
    node = build_tree_archive(archive)
    child_names = {c.name for c in node.children}
    assert "src" in child_names
    assert "README.md" in child_names
    src_node = next(c for c in node.children if c.name == "src")
    assert {c.name for c in src_node.children} == {"foo.py", "bar.py"}


def test_zip_depth_limit(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path, [("a/b/c.txt", b"deep")])
    node = build_tree_archive(archive, depth=1)
    assert len(node.children) == 1
    assert node.children[0].is_dir
    # depth=1 means children of root dir are present but not recursed into
    assert node.children[0].children == []


def test_zip_excludes(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path, [("keep.txt", b"a"), ("skip.txt", b"b")])
    node = build_tree_archive(archive, exclude=frozenset({"skip.txt"}))
    names = {c.name for c in node.children}
    assert "keep.txt" in names
    assert "skip.txt" not in names


def test_zip_dotfile_skipped(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path, [(".hidden", b"secret"), ("visible.txt", b"ok")])
    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert ".hidden" not in names
    assert "visible.txt" in names


def test_zip_zero_size_becomes_one(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path, [("empty.txt", b"")])
    node = build_tree_archive(archive)
    assert node.children[0].size == 1


def test_zip_root_name(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path, [("a.txt", b"hi")])
    node = build_tree_archive(archive)
    assert node.name == "test"  # stem of test.zip


# ---------------------------------------------------------------------------
# tar.gz tests
# ---------------------------------------------------------------------------


def test_tar_gz_flat(tmp_path: Path) -> None:
    archive = _make_tar_gz(tmp_path, [("a.txt", b"hello"), ("b.py", b"world!")])
    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert names == {"a.txt", "b.py"}


def test_tar_gz_nested(tmp_path: Path) -> None:
    archive = _make_tar_gz(
        tmp_path,
        [("src/foo.py", b"x" * 100), ("README.md", b"z" * 50)],
    )
    node = build_tree_archive(archive)
    child_names = {c.name for c in node.children}
    assert "src" in child_names
    assert "README.md" in child_names


def test_tar_gz_depth_limit(tmp_path: Path) -> None:
    archive = _make_tar_gz(tmp_path, [("a/b/c.txt", b"deep")])
    node = build_tree_archive(archive, depth=1)
    assert len(node.children) == 1
    assert node.children[0].is_dir
    assert node.children[0].children == []


def test_tar_gz_excludes(tmp_path: Path) -> None:
    archive = _make_tar_gz(tmp_path, [("keep.txt", b"a"), ("skip.txt", b"b")])
    node = build_tree_archive(archive, exclude=frozenset({"skip.txt"}))
    names = {c.name for c in node.children}
    assert "keep.txt" in names
    assert "skip.txt" not in names


def test_tar_gz_dotfile_skipped(tmp_path: Path) -> None:
    archive = _make_tar_gz(tmp_path, [(".hidden", b"secret"), ("visible.txt", b"ok")])
    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert ".hidden" not in names
    assert "visible.txt" in names


def test_tar_gz_root_name(tmp_path: Path) -> None:
    archive = _make_tar_gz(tmp_path, [("a.txt", b"hi")])
    node = build_tree_archive(archive)
    assert node.name == "test"  # double-stem of test.tar.gz


# ---------------------------------------------------------------------------
# 7z tests (skipped if py7zr not installed)
# ---------------------------------------------------------------------------


def test_7z_basic(tmp_path: Path) -> None:
    import py7zr

    archive = tmp_path / "test.7z"
    content = tmp_path / "sample.txt"
    content.write_bytes(b"hello 7z")
    with py7zr.SevenZipFile(archive, mode="w") as sz:
        sz.write(content, "sample.txt")

    node = build_tree_archive(archive)
    assert node.name == "test"
    names = {c.name for c in node.children}
    assert "sample.txt" in names


def test_7z_dotfile_skipped(tmp_path: Path) -> None:
    import py7zr

    archive = tmp_path / "test.7z"
    hidden = tmp_path / ".hidden"
    visible = tmp_path / "visible.txt"
    hidden.write_bytes(b"secret")
    visible.write_bytes(b"ok")
    with py7zr.SevenZipFile(archive, mode="w") as sz:
        sz.write(hidden, ".hidden")
        sz.write(visible, "visible.txt")

    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert ".hidden" not in names
    assert "visible.txt" in names


# ---------------------------------------------------------------------------
# RAR tests (skipped if the `rar` CLI is not installed)
# ---------------------------------------------------------------------------

rar_cli = shutil.which("rar")
skip_no_rar = pytest.mark.skipif(rar_cli is None, reason="rar CLI not installed")


def _make_rar(tmp_path: Path, members: list[tuple[str, bytes]]) -> Path:
    """Write a rar to tmp_path/test.rar using the rar CLI and return the path."""
    assert rar_cli is not None
    src = tmp_path / "_src"
    src.mkdir()
    for name, data in members:
        dest = src / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    archive = tmp_path / "test.rar"
    subprocess.run(
        [rar_cli, "a", "-r", str(archive), "."], cwd=src, check=True, capture_output=True
    )
    return archive


@skip_no_rar
def test_rar_flat(tmp_path: Path) -> None:
    archive = _make_rar(tmp_path, [("a.txt", b"hello"), ("b.py", b"world")])
    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert "a.txt" in names
    assert "b.py" in names


@skip_no_rar
def test_rar_nested(tmp_path: Path) -> None:
    archive = _make_rar(tmp_path, [("src/foo.py", b"x" * 100), ("README.md", b"z" * 50)])
    node = build_tree_archive(archive)
    child_names = {c.name for c in node.children}
    assert "src" in child_names
    assert "README.md" in child_names


@skip_no_rar
def test_rar_dotfile_skipped(tmp_path: Path) -> None:
    archive = _make_rar(tmp_path, [(".hidden", b"secret"), ("visible.txt", b"ok")])
    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert ".hidden" not in names
    assert "visible.txt" in names


@skip_no_rar
def test_rar_root_name(tmp_path: Path) -> None:
    archive = _make_rar(tmp_path, [("a.txt", b"hi")])
    node = build_tree_archive(archive)
    assert node.name == "test"


# ---------------------------------------------------------------------------
# Fixture-based smoke tests: every supported format via sample_archives
# ---------------------------------------------------------------------------

# All extensions produced by make_fixtures.py / the sample_archives fixture.
# RAR is excluded here because it requires the rar CLI; tested separately below.
_ALL_EXTENSIONS = [
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
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
    ".7z",
]


@pytest.mark.parametrize("ext", _ALL_EXTENSIONS)
def test_fixture_tree_structure(ext: str, sample_archives: dict[str, Path]) -> None:
    """Every supported format yields the expected top-level names and sizes."""
    node = build_tree_archive(sample_archives[ext])
    top = {c.name for c in node.children}
    # .hidden must be absent; README.md, docs/, src/ must be present
    assert ".hidden" not in top
    assert {"README.md", "docs", "src"} <= top
    # src/ should contain app.py and util.py
    src = next(c for c in node.children if c.name == "src")
    assert {c.name for c in src.children} == {"app.py", "util.py"}
    # root size = 50+80+100+200 = 430 bytes
    assert node.size == 430


def test_fixture_rar_tree_structure(sample_archives: dict[str, Path]) -> None:
    """RAR fixture yields the same structure (skipped if rar CLI absent)."""
    if ".rar" not in sample_archives:
        pytest.skip("rar CLI not installed")
    node = build_tree_archive(sample_archives[".rar"])
    top = {c.name for c in node.children}
    assert ".hidden" not in top
    assert {"README.md", "docs", "src"} <= top


# ---------------------------------------------------------------------------
# Cross-format consistency: all archives must produce identical trees
# ---------------------------------------------------------------------------

from dirplot.scanner import Node as _Node  # noqa: E402


def _tree_repr(node: _Node) -> tuple[str, int, tuple[object, ...]]:
    """Recursively convert a Node into a comparable (name, size, children) tuple."""
    return (node.name, node.size, tuple(sorted(_tree_repr(c) for c in node.children)))


def test_all_formats_same_content(sample_archives: dict[str, Path]) -> None:
    """Every archive in sample_archives must produce an identical node tree.

    `.a` / `.ar` archives are intentionally excluded: the `ar` format is flat
    (no directory hierarchy), so the tree structure necessarily differs.
    """
    reprs = {
        ext: _tree_repr(build_tree_archive(path))
        for ext, path in sample_archives.items()
        if ext not in (".a", ".ar")
    }
    reference_ext, reference = next(iter(reprs.items()))
    for ext, rep in reprs.items():
        assert rep == reference, (
            f"Archive {ext!r} differs from {reference_ext!r}:\n"
            f"  {ext}: size={rep[1]}, top-level={[c[0] for c in rep[2]]}\n"
            f"  {reference_ext}: size={reference[1]}, top-level={[c[0] for c in reference[2]]}"
        )


# ---------------------------------------------------------------------------
# libarchive tests (.cpio, .iso) – skipped if bsdtar CLI is not available
# ---------------------------------------------------------------------------

bsdtar_cli = shutil.which("bsdtar")
skip_no_bsdtar = pytest.mark.skipif(bsdtar_cli is None, reason="bsdtar CLI not installed")


def _make_cpio(tmp_path: Path, members: list[tuple[str, bytes]]) -> Path:
    """Create a cpio archive at tmp_path/test.cpio using bsdtar and return the path."""
    assert bsdtar_cli is not None
    src = tmp_path / "_src_cpio"
    src.mkdir()
    for name, data in members:
        dest = src / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    archive = tmp_path / "test.cpio"
    subprocess.run(
        [bsdtar_cli, "-cf", str(archive), "--format", "cpio"] + [name for name, _ in members],
        cwd=str(src),
        check=True,
        capture_output=True,
    )
    return archive


def _make_iso(tmp_path: Path, members: list[tuple[str, bytes]]) -> Path:
    """Create an ISO 9660 archive at tmp_path/test.iso using bsdtar and return the path."""
    assert bsdtar_cli is not None
    src = tmp_path / "_src_iso"
    src.mkdir()
    for name, data in members:
        dest = src / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    archive = tmp_path / "test.iso"
    subprocess.run(
        [bsdtar_cli, "-cf", str(archive), "--format", "iso9660", "-C", str(src), "."],
        check=True,
        capture_output=True,
    )
    return archive


@skip_no_bsdtar
def test_cpio_flat(tmp_path: Path) -> None:
    archive = _make_cpio(tmp_path, [("a.txt", b"hello"), ("b.py", b"world!")])
    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert "a.txt" in names
    assert "b.py" in names


@skip_no_bsdtar
def test_cpio_nested(tmp_path: Path) -> None:
    archive = _make_cpio(tmp_path, [("src/foo.py", b"x" * 100), ("README.md", b"z" * 50)])
    node = build_tree_archive(archive)
    child_names = {c.name for c in node.children}
    assert "src" in child_names
    assert "README.md" in child_names


@skip_no_bsdtar
def test_cpio_root_name(tmp_path: Path) -> None:
    archive = _make_cpio(tmp_path, [("a.txt", b"hi")])
    node = build_tree_archive(archive)
    assert node.name == "test"


@skip_no_bsdtar
def test_iso_flat(tmp_path: Path) -> None:
    archive = _make_iso(tmp_path, [("a.txt", b"hello"), ("b.py", b"world!")])
    node = build_tree_archive(archive)
    names = {c.name for c in node.children}
    assert "a.txt" in names
    assert "b.py" in names


@skip_no_bsdtar
def test_iso_nested(tmp_path: Path) -> None:
    archive = _make_iso(tmp_path, [("src/foo.py", b"x" * 100), ("README.md", b"z" * 50)])
    node = build_tree_archive(archive)
    child_names = {c.name for c in node.children}
    assert "src" in child_names
    assert "README.md" in child_names


@skip_no_bsdtar
def test_iso_root_name(tmp_path: Path) -> None:
    archive = _make_iso(tmp_path, [("a.txt", b"hi")])
    node = build_tree_archive(archive)
    assert node.name == "test"


def test_libarchive_missing_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure a clear ImportError is raised when libarchive-c is not installed."""
    import builtins

    real_import = builtins.__import__

    def mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "libarchive":
            raise ImportError("No module named 'libarchive'")
        return real_import(name, *args, **kwargs)

    # Create a dummy .cpio so _archive_type returns "libarchive"
    dummy = tmp_path / "dummy.cpio"
    dummy.write_bytes(b"")

    monkeypatch.setattr(builtins, "__import__", mock_import)
    with pytest.raises(ImportError, match="libarchive-c is required"):
        build_tree_archive(dummy)


# ---------------------------------------------------------------------------
# Encrypted archive tests
# ---------------------------------------------------------------------------


def test_7z_encrypted_metadata_readable_without_password(
    encrypted_archives: dict[str, Path],
) -> None:
    """py7zr does not encrypt archive headers by default — only file content is
    encrypted.  Our reader calls ``sz.list()`` only (never extracts), so the
    file listing is accessible without a password.
    """
    node = build_tree_archive(encrypted_archives[".7z"])
    assert {c.name for c in node.children} >= {"README.md", "docs", "src"}


def test_7z_encrypted_with_password(encrypted_archives: dict[str, Path]) -> None:
    node = build_tree_archive(encrypted_archives[".7z"], password=ENCRYPTED_PASSWORD)
    assert {c.name for c in node.children} >= {"README.md", "docs", "src"}


def test_zip_encrypted_metadata_readable_without_password(
    encrypted_archives: dict[str, Path],
) -> None:
    """Standard ZIP encryption covers only file data, not the central directory.

    Our reader only touches metadata (names + uncompressed sizes), so an
    encrypted ZIP is fully usable even without a password.
    """
    if ".zip" not in encrypted_archives:
        pytest.skip("encrypted zip fixture unavailable (zip CLI not found)")
    node = build_tree_archive(encrypted_archives[".zip"])
    assert {c.name for c in node.children} >= {"README.md", "docs", "src"}


def test_zip_encrypted_with_password(encrypted_archives: dict[str, Path]) -> None:
    if ".zip" not in encrypted_archives:
        pytest.skip("encrypted zip fixture unavailable (zip CLI not found)")
    node = build_tree_archive(encrypted_archives[".zip"], password=ENCRYPTED_PASSWORD)
    assert {c.name for c in node.children} >= {"README.md", "docs", "src"}


def test_rar_encrypted_no_password_hides_entries(
    encrypted_archives: dict[str, Path],
) -> None:
    """RAR with header encryption (-hp) and no password: rarfile opens the
    archive but returns an empty listing — the tree root has no children.
    No exception is raised; the archive appears empty.
    """
    if ".rar" not in encrypted_archives:
        pytest.skip("encrypted rar fixture unavailable (rar CLI not found)")
    node = build_tree_archive(encrypted_archives[".rar"])
    assert node.children == []


def test_rar_encrypted_correct_password(encrypted_archives: dict[str, Path]) -> None:
    if ".rar" not in encrypted_archives:
        pytest.skip("encrypted rar fixture unavailable (rar CLI not found)")
    node = build_tree_archive(encrypted_archives[".rar"], password=ENCRYPTED_PASSWORD)
    assert {c.name for c in node.children} >= {"README.md", "docs", "src"}


def test_rar_encrypted_wrong_password_raises(encrypted_archives: dict[str, Path]) -> None:
    """A wrong password on a header-encrypted RAR raises ``PasswordRequired``."""
    if ".rar" not in encrypted_archives:
        pytest.skip("encrypted rar fixture unavailable (rar CLI not found)")
    with pytest.raises(PasswordRequired):
        build_tree_archive(encrypted_archives[".rar"], password="wrong")
