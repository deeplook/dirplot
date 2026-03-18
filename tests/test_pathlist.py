"""Tests for the pathlist parser (tree/find format detection and parsing)."""

from __future__ import annotations

from pathlib import Path

from dirplot.pathlist import detect_format, parse_find, parse_pathlist, parse_tree

# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------


def test_detect_format_find():
    lines = ["/home/user/foo.py", "/home/user/bar.txt", "./relative/path"]
    assert detect_format(lines) == "find"


def test_detect_format_tree():
    lines = [
        "/home/user",
        "├── src",
        "│   └── main.py",
        "└── README.md",
    ]
    assert detect_format(lines) == "tree"


def test_detect_format_tree_full_paths():
    lines = [
        "/home/user",
        "├── /home/user/src",
        "│   └── /home/user/src/main.py",
        "└── /home/user/README.md",
    ]
    assert detect_format(lines) == "tree_f"


# ---------------------------------------------------------------------------
# parse_find
# ---------------------------------------------------------------------------


def test_parse_find_basic(tmp_path: Path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.py"
    f1.write_text("x")
    f2.write_text("y")
    lines = [str(f1), str(f2), ""]
    result = parse_find(lines)
    assert result == [f1, f2]


def test_parse_find_skips_blank_lines():
    result = parse_find(["", "  ", "/tmp/foo"])
    assert result == [Path("/tmp/foo")]


# ---------------------------------------------------------------------------
# parse_tree (default indentation format)
# ---------------------------------------------------------------------------

_TREE_DEFAULT = """\
/tmp/myroot
├── dir1
│   ├── file1.txt
│   └── file2.py
├── dir2
│   └── sub
│       └── deep.js
└── README.md
"""


def test_parse_tree_default():
    lines = _TREE_DEFAULT.splitlines()
    paths = parse_tree(lines)
    assert Path("/tmp/myroot/dir1") in paths
    assert Path("/tmp/myroot/dir1/file1.txt") in paths
    assert Path("/tmp/myroot/dir1/file2.py") in paths
    assert Path("/tmp/myroot/dir2") in paths
    assert Path("/tmp/myroot/dir2/sub") in paths
    assert Path("/tmp/myroot/dir2/sub/deep.js") in paths
    assert Path("/tmp/myroot/README.md") in paths


_TREE_SIZES = """\
/tmp/myroot
├── [       4096]  dir1
│   ├── [       1234]  file1.txt
│   └── [       5678]  file2.py
└── [        512]  README.md
"""


def test_parse_tree_with_sizes():
    lines = _TREE_SIZES.splitlines()
    paths = parse_tree(lines)
    assert Path("/tmp/myroot/dir1") in paths
    assert Path("/tmp/myroot/dir1/file1.txt") in paths
    assert Path("/tmp/myroot/dir1/file2.py") in paths
    assert Path("/tmp/myroot/README.md") in paths


_TREE_FULL_PATHS = """\
/tmp/myroot
├── /tmp/myroot/dir1
│   ├── /tmp/myroot/dir1/file1.txt
│   └── /tmp/myroot/dir1/file2.py
└── /tmp/myroot/README.md
"""


def test_parse_tree_full_paths():
    lines = _TREE_FULL_PATHS.splitlines()
    paths = parse_tree(lines)
    assert Path("/tmp/myroot/dir1") in paths
    assert Path("/tmp/myroot/dir1/file1.txt") in paths
    assert Path("/tmp/myroot/dir1/file2.py") in paths
    assert Path("/tmp/myroot/README.md") in paths


_TREE_COMMENTS = """\
.crosspoint/
├── epub_12471232/       # Each EPUB is cached to a subdirectory named epub_<hash>
│   ├── progress.bin     # Stores reading progress (chapter, page, etc.)
│   ├── cover.bmp        # Book cover image (once generated)
│   ├── book.bin         # Book metadata (title, author, spine, etc.)
│   └── sections/        # All chapter data is stored here
│       ├── 0.bin        # Chapter data
│       └── 1.bin        #     named by spine index
│
└── epub_189013891/
"""


def test_parse_tree_strips_comments():
    lines = _TREE_COMMENTS.splitlines()
    paths = parse_tree(lines)
    names = [p.name for p in paths]
    assert "epub_12471232" in names
    assert "progress.bin" in names
    assert "sections" in names
    assert "0.bin" in names
    assert "1.bin" in names
    assert "epub_189013891" in names
    # Comments must not leak into path names
    assert not any("#" in str(p) for p in paths)


def test_parse_tree_preserves_hash_in_filename():
    lines = [
        "/tmp/root",
        "├── file#2.txt",
        "└── notes.md",
    ]
    paths = parse_tree(lines)
    assert Path("/tmp/root/file#2.txt") in paths


def test_parse_tree_skips_summary_lines():
    lines = [
        "/tmp/myroot",
        "└── file.txt",
        "",
        "1 directory, 1 file",
    ]
    paths = parse_tree(lines)
    assert Path("/tmp/myroot/file.txt") in paths
    # Summary line must not appear as a path
    assert not any("directory" in str(p) for p in paths)


# ---------------------------------------------------------------------------
# parse_pathlist (auto-dispatch)
# ---------------------------------------------------------------------------


def test_parse_pathlist_dispatches_find():
    result = parse_pathlist(["/tmp/a", "/tmp/b"])
    # minimal_roots resolves paths; use resolved comparisons
    assert Path("/tmp/a").resolve() in result
    assert Path("/tmp/b").resolve() in result


def test_parse_pathlist_dispatches_tree():
    lines = _TREE_DEFAULT.splitlines()
    paths = parse_pathlist(lines)
    # minimal_roots collapses to the root since all entries are descendants
    assert len(paths) == 1
    assert paths[0] == Path("/tmp/myroot").resolve()


def test_parse_pathlist_empty():
    assert parse_pathlist([]) == []
    assert parse_pathlist(["", "   "]) == []
