"""Tests for directory scanning and tree construction."""

from pathlib import Path

import pytest

from dirplot.scanner import Node, build_tree, collect_extensions


def test_build_tree_structure(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    assert root.is_dir
    assert root.size == 430  # 80 + 100 + 200 + 50

    child_names = {c.name for c in root.children}
    assert "docs" in child_names
    assert "src" in child_names
    assert "README.md" in child_names


def test_build_tree_file_node(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    readme = next(c for c in root.children if c.name == "README.md")
    assert not readme.is_dir
    assert readme.size == 50
    assert readme.extension == ".md"


def test_build_tree_exclude(sample_tree: Path) -> None:
    excluded = frozenset({(sample_tree / "src").resolve()})
    root = build_tree(sample_tree, exclude=excluded)
    child_names = {c.name for c in root.children}
    assert "src" not in child_names
    assert root.size == 130  # 80 + 50


def test_build_tree_depth_limit(sample_tree: Path) -> None:
    root = build_tree(sample_tree, depth=1)
    child_names = {c.name for c in root.children}
    assert "src" in child_names
    assert "docs" in child_names
    src = next(c for c in root.children if c.name == "src")
    assert src.is_dir
    assert src.children == []  # not recursed into


def test_build_tree_no_ext(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_bytes(b"x" * 10)
    root = build_tree(tmp_path)
    makefile = next(c for c in root.children if c.name == "Makefile")
    assert makefile.extension == "(no ext)"


def test_build_tree_permission_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(_path: Path) -> list[Path]:
        raise PermissionError

    monkeypatch.setattr(Path, "iterdir", _raise)
    root = build_tree(tmp_path)
    assert root.size == 0
    assert root.children == []


def test_build_tree_skips_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_bytes(b"x" * 20)
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    root = build_tree(tmp_path)
    child_names = {c.name for c in root.children}
    assert "real.txt" in child_names
    assert "link.txt" not in child_names


def test_build_tree_stat_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import stat as stat_module

    (tmp_path / "file.txt").write_bytes(b"x" * 10)

    original_stat = Path.stat

    class _FakeStat:
        """Looks like a regular file for mode checks but raises on st_size."""

        st_mode = stat_module.S_IFREG | 0o644

        @property
        def st_size(self) -> int:
            raise OSError("stat failed")

    def _patched_stat(self: Path, *, follow_symlinks: bool = True) -> object:
        if self.name == "file.txt" and follow_symlinks:
            return _FakeStat()
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", _patched_stat)
    root = build_tree(tmp_path)
    file_node = next(c for c in root.children if c.name == "file.txt")
    assert file_node.size == 1  # OSError falls back to minimum size of 1


def test_build_tree_skips_special_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Entries that are neither files, dirs, nor symlinks are skipped."""
    regular = tmp_path / "normal.txt"
    regular.write_bytes(b"x" * 5)

    special = tmp_path / "special"

    def _fake_iterdir(self: Path) -> list[Path]:  # type: ignore[return]
        return [regular, special]

    monkeypatch.setattr(Path, "iterdir", _fake_iterdir)
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    monkeypatch.setattr(Path, "is_dir", lambda self: False)
    monkeypatch.setattr(Path, "is_file", lambda self: self.name == "normal.txt")

    root = build_tree(tmp_path)
    child_names = {c.name for c in root.children}
    assert "normal.txt" in child_names
    assert "special" not in child_names


def test_collect_extensions(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    exts = collect_extensions(root)
    assert ".py" in exts
    assert ".md" in exts
    assert exts.count(".py") == 2
    assert exts.count(".md") == 2


def test_single_file_node() -> None:
    node = Node(name="foo.py", path=Path("foo.py"), size=42, is_dir=False, extension=".py")
    assert collect_extensions(node) == [".py"]


def test_collect_extensions_empty_dir(tmp_path: Path) -> None:
    root = build_tree(tmp_path)
    assert collect_extensions(root) == []
