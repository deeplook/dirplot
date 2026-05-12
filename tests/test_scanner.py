"""Tests for directory scanning and tree construction."""

from pathlib import Path

import pytest

from dirplot.scanner import (
    Node,
    _collect_dirs,
    _collect_files,
    _fmt_size,
    apply_breadcrumbs,
    build_tree,
    build_tree_multi,
    collect_extensions,
    prune_to_subtrees,
    tree_metrics,
    tree_metrics_dict,
)


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
    excluded = frozenset({"src"})
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


def test_prune_to_subtrees_basic(tmp_path: Path) -> None:
    (tmp_path / "bar").mkdir()
    (tmp_path / "baz").mkdir()
    (tmp_path / "qux").mkdir()
    (tmp_path / "bar" / "a.py").write_bytes(b"x" * 10)
    (tmp_path / "baz" / "b.py").write_bytes(b"x" * 20)
    (tmp_path / "qux" / "c.py").write_bytes(b"x" * 99)

    root = build_tree(tmp_path)
    pruned = prune_to_subtrees(root, {"bar", "baz"})
    assert {c.name for c in pruned.children} == {"bar", "baz"}
    assert pruned.size == 30


def test_prune_to_subtrees_unknown_name_ignored(tmp_path: Path) -> None:
    (tmp_path / "bar").mkdir()
    (tmp_path / "bar" / "a.py").write_bytes(b"x" * 10)

    root = build_tree(tmp_path)
    pruned = prune_to_subtrees(root, {"bar", "nonexistent"})
    assert {c.name for c in pruned.children} == {"bar"}


def test_prune_to_subtrees_nested_path(tmp_path: Path) -> None:
    (tmp_path / "src" / "dirplot" / "fonts").mkdir(parents=True)
    (tmp_path / "src" / "dirplot" / "fonts" / "f.ttf").write_bytes(b"x" * 10)
    (tmp_path / "src" / "dirplot" / "other.py").write_bytes(b"x" * 5)
    (tmp_path / "src" / "sibling.py").write_bytes(b"x" * 3)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_bytes(b"x" * 7)

    root = build_tree(tmp_path)
    pruned = prune_to_subtrees(root, {"src/dirplot/fonts", "tests"})

    assert {c.name for c in pruned.children} == {"src", "tests"}
    src = next(c for c in pruned.children if c.name == "src")
    assert {c.name for c in src.children} == {"dirplot"}
    dirplot = src.children[0]
    assert {c.name for c in dirplot.children} == {"fonts"}
    assert pruned.size == 17  # 10 (font) + 7 (test)


def test_prune_to_subtrees_empty_result(tmp_path: Path) -> None:
    (tmp_path / "bar").mkdir()

    root = build_tree(tmp_path)
    pruned = prune_to_subtrees(root, {"nonexistent"})
    assert pruned.children == []
    assert pruned.size == 0


def test_build_tree_multi_two_siblings(tmp_path: Path) -> None:
    (tmp_path / "bar").mkdir()
    (tmp_path / "baz").mkdir()
    (tmp_path / "qux").mkdir()
    (tmp_path / "bar" / "a.py").write_bytes(b"x" * 10)
    (tmp_path / "baz" / "b.py").write_bytes(b"x" * 20)
    (tmp_path / "qux" / "c.py").write_bytes(b"x" * 99)  # must be excluded

    root = build_tree_multi([tmp_path / "bar", tmp_path / "baz"])
    assert root.path == tmp_path
    assert {c.name for c in root.children} == {"bar", "baz"}
    assert root.size == 30


def test_build_tree_multi_nested_intermediate(tmp_path: Path) -> None:
    (tmp_path / "a" / "x").mkdir(parents=True)
    (tmp_path / "a" / "y").mkdir()
    (tmp_path / "a" / "z").mkdir()  # sibling, must be excluded
    (tmp_path / "a" / "x" / "f.txt").write_bytes(b"x" * 5)
    (tmp_path / "a" / "y" / "g.txt").write_bytes(b"x" * 7)
    (tmp_path / "a" / "z" / "h.txt").write_bytes(b"x" * 3)

    root = build_tree_multi([tmp_path / "a" / "x", tmp_path / "a" / "y"])
    assert root.path.resolve() == (tmp_path / "a").resolve()
    assert {c.name for c in root.children} == {"x", "y"}


def test_build_tree_multi_single_delegates(tmp_path: Path) -> None:
    (tmp_path / "file.py").write_bytes(b"x" * 10)
    root = build_tree_multi([tmp_path])
    assert root.path == tmp_path
    assert len(root.children) == 1


# ---------------------------------------------------------------------------
# apply_breadcrumbs
# ---------------------------------------------------------------------------


def _make_dir(name: str, children: list[Node] | None = None) -> Node:
    return Node(name=name, path=Path(name), size=1, is_dir=True, children=children or [])


def _make_file(name: str) -> Node:
    return Node(name=name, path=Path(name), size=1, is_dir=False, extension=".txt")


def test_breadcrumbs_collapses_chain() -> None:
    # root → a → b → c → [file.txt]; root is never collapsed, but a/b/c merge
    file_node = _make_file("file.txt")
    c = _make_dir("c", [file_node])
    b = _make_dir("b", [c])
    a = _make_dir("a", [b])
    root = _make_dir("root", [a])

    result = apply_breadcrumbs(root)

    assert result.name == "root"  # root itself is never collapsed
    assert len(result.children) == 1
    merged = result.children[0]
    assert merged.name == "a / b / c"
    assert len(merged.children) == 1
    assert merged.children[0].name == "file.txt"


def test_breadcrumbs_no_collapse_with_files() -> None:
    # root → a → [file.txt, subdir]  — a has file child, must not collapse
    file_node = _make_file("file.txt")
    subdir = _make_dir("subdir", [_make_file("inner.txt")])
    a = _make_dir("a", [file_node, subdir])
    root = _make_dir("root", [a])

    result = apply_breadcrumbs(root)

    assert result.name == "root"
    child = result.children[0]
    assert child.name == "a"
    assert {c.name for c in child.children} == {"file.txt", "subdir"}


def test_breadcrumbs_no_collapse_multi_children() -> None:
    # root → a → [dir1, dir2]  — a has two dir children, must not collapse
    dir1 = _make_dir("dir1", [_make_file("x.txt")])
    dir2 = _make_dir("dir2", [_make_file("y.txt")])
    a = _make_dir("a", [dir1, dir2])
    root = _make_dir("root", [a])

    result = apply_breadcrumbs(root)

    assert result.name == "root"
    child = result.children[0]
    assert child.name == "a"
    assert {c.name for c in child.children} == {"dir1", "dir2"}


# ---------------------------------------------------------------------------
# _fmt_size
# ---------------------------------------------------------------------------


def test_fmt_size_bytes() -> None:
    assert _fmt_size(0) == "0.0 B"
    assert _fmt_size(512) == "512.0 B"


def test_fmt_size_kilobytes() -> None:
    assert _fmt_size(1024) == "1.0 KB"
    assert _fmt_size(2048) == "2.0 KB"


def test_fmt_size_megabytes() -> None:
    assert _fmt_size(1024 * 1024) == "1.0 MB"


def test_fmt_size_gigabytes() -> None:
    assert _fmt_size(1024**3) == "1.0 GB"


def test_fmt_size_terabytes() -> None:
    assert _fmt_size(1024**4) == "1.0 TB"


# ---------------------------------------------------------------------------
# _collect_files / _collect_dirs
# ---------------------------------------------------------------------------


def test_collect_files_flat(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    files = _collect_files(root)
    assert all(not f.is_dir for f in files)
    names = {f.name for f in files}
    assert "app.py" in names
    assert "README.md" in names


def test_collect_files_single_file_node() -> None:
    node = Node(name="f.py", path=Path("f.py"), size=10, is_dir=False, extension=".py")
    assert _collect_files(node) == [node]


def test_collect_dirs_excludes_root(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    dirs = _collect_dirs(root)
    assert all(d.is_dir for d in dirs)
    assert root not in dirs
    names = {d.name for d in dirs}
    assert "src" in names
    assert "docs" in names


def test_collect_dirs_empty_tree(tmp_path: Path) -> None:
    root = build_tree(tmp_path)
    assert _collect_dirs(root) == []


# ---------------------------------------------------------------------------
# tree_metrics
# ---------------------------------------------------------------------------


def test_tree_metrics_contains_key_fields(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    out = tree_metrics(root, t_scan=0.5)
    assert "Files:" in out
    assert "Dirs:" in out
    assert "Total size:" in out
    assert "Depth:" in out
    assert "Scan time:" in out
    assert "Top extensions" in out
    assert "Largest files:" in out
    assert "Largest dirs:" in out


def test_tree_metrics_file_count(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    out = tree_metrics(root, t_scan=0.0)
    # sample_tree has 4 files
    assert "4" in out


def test_tree_metrics_empty_dir_count(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    (tmp_path / "nonempty").mkdir()
    (tmp_path / "nonempty" / "f.txt").write_bytes(b"x")
    root = build_tree(tmp_path)
    out = tree_metrics(root, t_scan=0.0)
    assert "1 empty" in out


def test_tree_metrics_top_n(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    out = tree_metrics(root, t_scan=0.0, top_n=1)
    assert "Top extensions (1)" in out


def test_tree_metrics_scan_time(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    out = tree_metrics(root, t_scan=1.23)
    assert "1.23s" in out


def test_tree_metrics_shows_ext_size(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    out = tree_metrics(root, t_scan=0.0)
    # Each extension line should include a human-readable size
    assert "KB" in out or "MB" in out or "B" in out


def test_tree_metrics_shows_percentages(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    out = tree_metrics(root, t_scan=0.0)
    assert "%" in out


def test_tree_metrics_sort_by_size(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    out = tree_metrics(root, t_scan=0.0, sort_by="size")
    assert "by size" in out


def test_tree_metrics_sort_by_count(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    out = tree_metrics(root, t_scan=0.0, sort_by="count")
    assert "by count" in out


def test_tree_metrics_dict_keys(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    d = tree_metrics_dict(root, t_scan=0.5)
    assert d["files"] == 4
    assert d["dirs"] == 2
    assert d["total_size_bytes"] == 430
    assert d["depth"] >= 1
    assert isinstance(d["top_extensions"], list)
    assert isinstance(d["largest_files"], list)
    assert isinstance(d["largest_dirs"], list)


def test_tree_metrics_dict_ext_fields(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    d = tree_metrics_dict(root, t_scan=0.0)
    for e in d["top_extensions"]:
        assert "ext" in e
        assert "count" in e
        assert "size_bytes" in e


def test_tree_metrics_dict_pct(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    d = tree_metrics_dict(root, t_scan=0.0)
    for f in d["largest_files"]:
        assert 0.0 <= f["pct"] <= 100.0
    for dr in d["largest_dirs"]:
        assert 0.0 <= dr["pct"] <= 100.0


def test_tree_metrics_dict_sort_by_size(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    d = tree_metrics_dict(root, t_scan=0.0, sort_by="size")
    sizes = [e["size_bytes"] for e in d["top_extensions"]]
    assert sizes == sorted(sizes, reverse=True)


def test_breadcrumbs_partial_chain() -> None:
    # root → a → b → [dir1, dir2]  — b has two children, so a/b merges but stops there
    dir1 = _make_dir("dir1", [_make_file("x.txt")])
    dir2 = _make_dir("dir2", [_make_file("y.txt")])
    b = _make_dir("b", [dir1, dir2])
    a = _make_dir("a", [b])
    root = _make_dir("root", [a])

    result = apply_breadcrumbs(root)

    assert result.name == "root"
    child = result.children[0]
    assert child.name == "a / b"
    assert {c.name for c in child.children} == {"dir1", "dir2"}
