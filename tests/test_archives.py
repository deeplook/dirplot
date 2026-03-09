"""Tests for archive scanning (zip, tar.gz, 7z, rar)."""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from dirplot.archives import build_tree_archive, is_archive_path

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
    """Every archive in sample_archives must produce an identical node tree."""
    reprs = {ext: _tree_repr(build_tree_archive(path)) for ext, path in sample_archives.items()}
    reference_ext, reference = next(iter(reprs.items()))
    for ext, rep in reprs.items():
        assert rep == reference, (
            f"Archive {ext!r} differs from {reference_ext!r}:\n"
            f"  {ext}: size={rep[1]}, top-level={[c[0] for c in rep[2]]}\n"
            f"  {reference_ext}: size={reference[1]}, top-level={[c[0] for c in reference[2]]}"
        )
