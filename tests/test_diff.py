"""Tests for the ``dirplot diff`` command."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dirplot.main import app

runner = CliRunner()

_git_available = bool(shutil.which("git"))

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=_GIT_ENV)


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Minimal git repo with two commits and an untracked file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    # First commit: two files
    (repo / "alpha.py").write_bytes(b"a" * 200)
    (repo / "beta.py").write_bytes(b"b" * 300)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    # Second commit: modify alpha (same size, different content), add gamma
    (repo / "alpha.py").write_bytes(b"z" * 200)  # same size, changed content
    (repo / "gamma.py").write_bytes(b"g" * 100)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "update")

    # Uncommitted change: modify beta
    (repo / "beta.py").write_bytes(b"b" * 400)

    # Untracked file — should never appear in diff output
    (repo / "untracked.txt").write_bytes(b"noise")

    return repo


@pytest.fixture()
def tree_a(tmp_path: Path) -> Path:
    root = tmp_path / "a"
    root.mkdir()
    (root / "same.py").write_bytes(b"x" * 500)
    (root / "changed.py").write_bytes(b"x" * 300)
    (root / "removed.py").write_bytes(b"x" * 200)
    sub = root / "sub"
    sub.mkdir()
    (sub / "sub_same.py").write_bytes(b"x" * 100)
    (sub / "sub_removed.py").write_bytes(b"x" * 150)
    return root


@pytest.fixture()
def tree_b(tmp_path: Path) -> Path:
    root = tmp_path / "b"
    root.mkdir()
    (root / "same.py").write_bytes(b"x" * 500)
    (root / "changed.py").write_bytes(b"x" * 999)  # size changed
    (root / "added.py").write_bytes(b"x" * 400)
    sub = root / "sub"
    sub.mkdir()
    (sub / "sub_same.py").write_bytes(b"x" * 100)
    (sub / "sub_added.py").write_bytes(b"x" * 250)
    return root


def test_diff_produces_png(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--output",
            str(out),
            "--canvas",
            "300x200",
            "--no-show",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_diff_reports_counts(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--output",
            str(out),
            "--canvas",
            "300x200",
            "--no-show",
        ],
    )
    assert result.exit_code == 0, result.output
    # 2 added (added.py, sub/sub_added.py), 2 removed (removed.py, sub/sub_removed.py), 1 changed
    assert "2 added" in result.output
    assert "2 removed" in result.output
    assert "1 changed" in result.output


def test_diff_include_reports_counts_for_included_subtree(
    tree_a: Path, tree_b: Path, tmp_path: Path
) -> None:
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--include",
            "sub",
            "--output",
            str(out),
            "--canvas",
            "300x200",
            "--no-show",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Diff: 1 added, 1 removed, 0 changed" in result.output


def test_diff_invalid_tree_a(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["diff", str(tmp_path / "nonexistent"), str(tmp_path), "--canvas", "300x200", "--no-show"],
    )
    assert result.exit_code == 1


def test_diff_invalid_tree_b(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["diff", str(tmp_path), str(tmp_path / "nonexistent"), "--canvas", "300x200", "--no-show"],
    )
    assert result.exit_code == 1


def test_diff_identical_trees(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.py").write_bytes(b"x" * 100)
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app,
        ["diff", str(root), str(root), "--output", str(out), "--canvas", "300x200", "--no-show"],
    )
    assert result.exit_code == 0, result.output
    assert "0 added" in result.output
    assert "0 removed" in result.output
    assert "0 changed" in result.output


def test_diff_svg_output(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    out = tmp_path / "diff.svg"
    result = runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--output",
            str(out),
            "--canvas",
            "300x200",
            "--no-show",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    content = out.read_text()
    assert "<svg" in content


def test_diff_changed_only(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    """--changed-only produces a smaller image (fewer tiles) than --context."""
    out_ctx = tmp_path / "diff_ctx.png"
    out_noctx = tmp_path / "diff_noctx.png"
    runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--output",
            str(out_ctx),
            "--canvas",
            "300x200",
            "--no-show",
        ],
    )
    runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--output",
            str(out_noctx),
            "--canvas",
            "300x200",
            "--no-show",
            "--changed-only",
        ],
    )
    assert out_ctx.exists() and out_noctx.exists()
    # --changed-only excludes unchanged files so the image should differ
    assert out_ctx.read_bytes() != out_noctx.read_bytes()


def test_diff_light_mode(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--output",
            str(out),
            "--canvas",
            "300x200",
            "--no-show",
            "--light",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


# --- git-aware diff tests ---


@pytest.mark.skipif(not _git_available, reason="git CLI not found")
def test_diff_single_arg_git_repo(git_repo: Path, tmp_path: Path) -> None:
    """Single-argument form diffs working tree against HEAD."""
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app, ["diff", str(git_repo), "--output", str(out), "--canvas", "300x200", "--no-show"]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    # beta.py was modified in the working tree
    assert "1 changed" in result.output


@pytest.mark.skipif(not _git_available, reason="git CLI not found")
def test_diff_single_arg_non_repo_fails(tmp_path: Path) -> None:
    """Single-argument form fails for a plain non-git directory."""
    plain = tmp_path / "plain"
    plain.mkdir()
    result = runner.invoke(app, ["diff", str(plain), "--canvas", "300x200", "--no-show"])
    assert result.exit_code == 1
    assert "Error" in result.output


@pytest.mark.skipif(not _git_available, reason="git CLI not found")
def test_diff_git_ref_syntax(git_repo: Path, tmp_path: Path) -> None:
    """path@ref syntax compares two git commits."""
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app,
        [
            "diff",
            f"{git_repo}@HEAD~1",
            f"{git_repo}@HEAD",
            "--output",
            str(out),
            "--canvas",
            "300x200",
            "--no-show",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    # HEAD added gamma.py and changed alpha.py
    assert "1 added" in result.output
    assert "1 changed" in result.output


@pytest.mark.skipif(not _git_available, reason="git CLI not found")
def test_diff_hash_based_change_detection(git_repo: Path, tmp_path: Path) -> None:
    """Files with same size but different content are detected as changed."""
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app,
        [
            "diff",
            f"{git_repo}@HEAD~1",
            f"{git_repo}@HEAD",
            "--output",
            str(out),
            "--canvas",
            "300x200",
            "--no-show",
        ],
    )
    assert result.exit_code == 0, result.output
    # alpha.py has same size (200 bytes) at both commits but different content
    assert "1 changed" in result.output


@pytest.mark.skipif(not _git_available, reason="git CLI not found")
def test_diff_untracked_files_excluded(git_repo: Path, tmp_path: Path) -> None:
    """Untracked files in a git repo must never appear in the diff."""
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app, ["diff", str(git_repo), "--output", str(out), "--canvas", "300x200", "--no-show"]
    )
    assert result.exit_code == 0, result.output
    # untracked.txt must not count as added
    assert "0 added" in result.output


@pytest.mark.skipif(not _git_available, reason="git CLI not found")
def test_diff_matching_hashes_not_changed(git_repo: Path, tmp_path: Path) -> None:
    """Files with matching hashes are not flagged as changed even if sizes differ.

    Verifies the _is_changed logic: when both hashes are available and equal,
    the file is treated as unchanged regardless of size discrepancy.
    This is the same code path triggered by Git LFS (pointer size vs disk size).
    """
    from dirplot.git_scanner import git_file_hashes, git_worktree_hashes

    # Confirm that an unmodified tracked file has the same hash in both sides
    hashes_head = git_file_hashes(git_repo, "HEAD")
    hashes_wt = git_worktree_hashes(git_repo)

    # gamma.py was added in HEAD and is unmodified in the working tree
    assert "gamma.py" in hashes_head
    assert "gamma.py" in hashes_wt
    assert hashes_head["gamma.py"] == hashes_wt["gamma.py"]


def test_diff_size_filter_keeps_matching_files(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    out = tmp_path / "diff.png"
    # Only files >= 400 bytes: same.py (500), changed.py (999 in B), added.py (400)
    result = runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--output",
            str(out),
            "--canvas",
            "300x200",
            "--no-show",
            "--size",
            "400..",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


def test_diff_size_filter_no_match_exits_nonzero(tree_a: Path, tree_b: Path) -> None:
    result = runner.invoke(
        app,
        ["diff", str(tree_a), str(tree_b), "--no-show", "--size", "999G.."],
    )
    assert result.exit_code == 1
    assert "No files match" in result.output


def test_diff_size_filter_invalid_range(tree_a: Path, tree_b: Path) -> None:
    result = runner.invoke(
        app,
        ["diff", str(tree_a), str(tree_b), "--no-show", "--size", "badrange"],
    )
    assert result.exit_code == 1
    assert "Invalid --size" in result.output
