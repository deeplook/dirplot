"""Tests for git_scanner: log parsing, diff application, node tree building, rendering."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dirplot.git_scanner import (
    _blob_sizes,
    _render_frame_worker,
    build_node_tree,
    build_tree_from_git,
    git_apply_diff,
    git_initial_files,
    git_log,
)

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git CLI not found")


# ---------------------------------------------------------------------------
# Fixture: minimal git repo
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    env = {
        **__import__("os").environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(r), *args], check=True, capture_output=True, env=env)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")

    (r / "hello.py").write_text("print('hello')\n")
    git("add", "hello.py")
    git("commit", "-m", "first commit")

    (r / "world.py").write_text("print('world')\n")
    git("add", "world.py")
    git("commit", "-m", "second commit")

    return r


# ---------------------------------------------------------------------------
# git_log — edge cases via mock
# ---------------------------------------------------------------------------


def test_git_log_blank_lines_skipped() -> None:
    """Blank lines in git log output do not produce entries."""
    mock_result = MagicMock()
    mock_result.stdout = "\n1234abc 1700000000 first\n\n5678def 1700000001 second\n"
    with patch("subprocess.run", return_value=mock_result):
        commits = git_log(Path("/fake/repo"))
    assert len(commits) == 2
    assert commits[0][0] == "1234abc"
    assert commits[1][0] == "5678def"


def test_git_log_invalid_timestamp_falls_back_to_zero() -> None:
    """Non-numeric timestamp in git log output → ts=0 (no crash)."""
    mock_result = MagicMock()
    mock_result.stdout = "abc123 NOT_A_NUMBER the subject\n"
    with patch("subprocess.run", return_value=mock_result):
        commits = git_log(Path("/fake/repo"))
    assert commits[0][1] == 0


# ---------------------------------------------------------------------------
# git_initial_files — edge cases via mock
# ---------------------------------------------------------------------------


def _ls_tree_result(stdout: str) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    return m


def test_git_initial_files_blank_lines_skipped() -> None:
    out = "\n100644 blob abc123  42\thello.py\n\n"
    with patch("subprocess.run", return_value=_ls_tree_result(out)):
        files = git_initial_files(Path("/repo"), "HEAD")
    assert "hello.py" in files


def test_git_initial_files_non_blob_skipped() -> None:
    out = "040000 tree abc123  -\tsome_dir\n100644 blob def456  10\tfile.py\n"
    with patch("subprocess.run", return_value=_ls_tree_result(out)):
        files = git_initial_files(Path("/repo"), "HEAD")
    assert "file.py" in files
    assert "some_dir" not in files


def test_git_initial_files_excluded_skipped() -> None:
    out = "100644 blob abc  10\texcluded_dir/file.py\n100644 blob def  20\tkeep.py\n"
    with patch("subprocess.run", return_value=_ls_tree_result(out)):
        files = git_initial_files(Path("/repo"), "HEAD", exclude=frozenset(["excluded_dir"]))
    assert "keep.py" in files
    assert "excluded_dir/file.py" not in files


def test_git_initial_files_invalid_size_fallback() -> None:
    out = "100644 blob abc NOTANINT\tfile.py\n"
    with patch("subprocess.run", return_value=_ls_tree_result(out)):
        files = git_initial_files(Path("/repo"), "HEAD")
    assert files.get("file.py") == 1


def test_git_initial_files_missing_tab_skipped() -> None:
    out = "100644 blob abc 10 no_tab_here\n"
    with patch("subprocess.run", return_value=_ls_tree_result(out)):
        files = git_initial_files(Path("/repo"), "HEAD")
    assert not files


# ---------------------------------------------------------------------------
# _blob_sizes
# ---------------------------------------------------------------------------


def test_blob_sizes_empty() -> None:
    assert _blob_sizes(Path("/repo"), []) == {}


def test_blob_sizes_with_repo(repo: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    sha = result.stdout.strip()
    # Get a real blob hash
    ls = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--long", sha],
        capture_output=True,
        text=True,
        check=True,
    )
    line = ls.stdout.splitlines()[0]
    blob_hash = line.split()[2]
    sizes = _blob_sizes(repo, [blob_hash])
    assert blob_hash in sizes
    assert sizes[blob_hash] >= 1


# ---------------------------------------------------------------------------
# git_apply_diff — status types via mock
# ---------------------------------------------------------------------------


def _diff_result(stdout: str) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    return m


def _cat_file_result(blob_hash: str, size: int) -> MagicMock:
    m = MagicMock()
    m.stdout = f"{blob_hash} blob {size}\n"
    return m


def test_git_apply_diff_added() -> None:
    diff_out = ":000000 100644 0000000 abc1234 A\tnew_file.py\n"
    files: dict[str, int] = {}
    with patch(
        "subprocess.run", side_effect=[_diff_result(diff_out), _cat_file_result("abc1234", 42)]
    ):
        highlights = git_apply_diff(Path("/repo"), files, "prev", "curr")
    assert files.get("new_file.py") == 42
    assert "/repo/new_file.py" in highlights


def test_git_apply_diff_modified() -> None:
    diff_out = ":100644 100644 old1234 new1234 M\texisting.py\n"
    files = {"existing.py": 10}
    with patch(
        "subprocess.run", side_effect=[_diff_result(diff_out), _cat_file_result("new1234", 99)]
    ):
        highlights = git_apply_diff(Path("/repo"), files, "prev", "curr")
    assert files.get("existing.py") == 99
    assert highlights.get("/repo/existing.py") == "modified"


def test_git_apply_diff_deleted() -> None:
    diff_out = ":100644 000000 abc1234 0000000 D\tgone.py\n"
    files = {"gone.py": 50}
    with patch("subprocess.run", return_value=_diff_result(diff_out)):
        highlights = git_apply_diff(Path("/repo"), files, "prev", "curr")
    assert "gone.py" not in files
    assert highlights.get("/repo/gone.py") == "deleted"


def test_git_apply_diff_renamed() -> None:
    diff_out = ":100644 100644 old1234 new1234 R090\told.py\tnew.py\n"
    files = {"old.py": 30}
    with patch(
        "subprocess.run", side_effect=[_diff_result(diff_out), _cat_file_result("new1234", 30)]
    ):
        highlights = git_apply_diff(Path("/repo"), files, "prev", "curr")
    assert "old.py" not in files
    assert files.get("new.py") == 30
    assert highlights.get("/repo/old.py") == "deleted"
    assert highlights.get("/repo/new.py") == "created"


def test_git_apply_diff_copied() -> None:
    diff_out = ":100644 100644 src1234 dst1234 C100\tsrc.py\tcopy.py\n"
    files = {"src.py": 20}
    with patch(
        "subprocess.run", side_effect=[_diff_result(diff_out), _cat_file_result("dst1234", 20)]
    ):
        highlights = git_apply_diff(Path("/repo"), files, "prev", "curr")
    assert files.get("copy.py") == 20
    assert highlights.get("/repo/copy.py") == "created"


def test_git_apply_diff_excluded() -> None:
    diff_out = ":000000 100644 0000000 abc1234 A\texcl/secret.py\n"
    files: dict[str, int] = {}
    with patch("subprocess.run", return_value=_diff_result(diff_out)):
        highlights = git_apply_diff(
            Path("/repo"), files, "prev", "curr", exclude=frozenset(["excl"])
        )
    assert not files
    assert not highlights


def test_git_apply_diff_blank_line_skipped() -> None:
    diff_out = "\n:000000 100644 0000000 abc1234 A\tvalid.py\n"
    files: dict[str, int] = {}
    with patch(
        "subprocess.run", side_effect=[_diff_result(diff_out), _cat_file_result("abc1234", 5)]
    ):
        git_apply_diff(Path("/repo"), files, "prev", "curr")
    assert "valid.py" in files


# ---------------------------------------------------------------------------
# build_node_tree
# ---------------------------------------------------------------------------


def test_build_node_tree_depth_limit(tmp_path: Path) -> None:
    files = {"a/b/c/deep.py": 100, "top.py": 50}
    node = build_node_tree(tmp_path, files, depth=2)
    assert node.is_dir
    # With depth=2, "a/b/c/deep.py" is truncated to "a/b"
    names = {c.name for c in node.children}
    assert "a" in names
    assert "top.py" in names


def test_build_node_tree_duplicate_leaf_accumulates(tmp_path: Path) -> None:
    """Two entries mapping to the same truncated leaf accumulate sizes."""
    files = {"a/b/x.py": 100, "a/b/y.py": 200}
    node = build_node_tree(tmp_path, files, depth=2)
    # Both truncate to "a/b" — sizes are accumulated on the directory
    assert node.size >= 300


def test_build_node_tree_empty(tmp_path: Path) -> None:
    node = build_node_tree(tmp_path, {})
    assert node.is_dir
    assert node.size >= 1


# ---------------------------------------------------------------------------
# _render_frame_worker
# ---------------------------------------------------------------------------


def test_render_frame_worker(tmp_path: Path) -> None:
    files = {"hello.py": 100, "world.py": 50}
    import time

    args = (
        str(tmp_path),
        files,
        {},  # highlights
        "abc1234",  # sha
        int(time.time()),  # ts
        0,  # orig_i
        0.5,  # progress
        None,  # depth
        0.0,  # logscale (disabled)
        200,  # width_px
        150,  # height_px
        12,  # font_size
        "tab20",  # colormap
        False,  # cushion
        True,  # dark
    )
    orig_i, png_bytes, rect_map = _render_frame_worker(args)
    assert orig_i == 0
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_frame_worker_log_scale(tmp_path: Path) -> None:
    files = {"big.py": 10_000, "small.py": 1}
    import time

    args = (
        str(tmp_path),
        files,
        None,
        "def5678",
        int(time.time()),
        2,
        1.0,
        None,
        4.0,  # logscale
        200,
        150,
        12,
        "tab20",
        True,  # cushion
        True,  # dark
    )
    orig_i, png_bytes, _ = _render_frame_worker(args)
    assert orig_i == 2
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# build_tree_from_git
# ---------------------------------------------------------------------------


def test_build_tree_from_git(repo: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    sha = result.stdout.strip()
    node = build_tree_from_git(repo, sha)
    assert node.is_dir
    assert node.size >= 1
    names = {c.name for c in node.children}
    assert "hello.py" in names or "world.py" in names
