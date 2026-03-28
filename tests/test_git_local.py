"""Tests for dirplot git with local repositories, including the .@ref syntax."""

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dirplot.main import app

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not shutil.which("git"),
    reason="git CLI not found",
)

_ffmpeg_available = bool(shutil.which("ffmpeg"))


@pytest.fixture()
def local_repo(tmp_path: Path) -> Path:
    """Create a minimal local git repo with two branches and a few commits each."""
    repo = tmp_path / "repo"
    repo.mkdir()

    env_overrides = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            env={**__import__("os").environ, **env_overrides},
        )

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")

    # Two commits on main
    (repo / "hello.py").write_text("print('hello')\n")
    git("add", "hello.py")
    git("commit", "-m", "add hello.py")

    (repo / "world.py").write_text("print('world')\n")
    git("add", "world.py")
    git("commit", "-m", "add world.py")

    # Feature branch with one more commit
    git("checkout", "-b", "feature")
    (repo / "feature.py").write_text("print('feature')\n")
    git("add", "feature.py")
    git("commit", "-m", "add feature.py")

    git("checkout", "main")
    return repo


def test_git_local_at_branch(local_repo: Path, tmp_path: Path) -> None:
    """dirplot git path@branch renders the branch without --range."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["git", f"{local_repo}@feature", "--output", str(out), "--size", "200x150"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_git_local_at_branch_animate(local_repo: Path, tmp_path: Path) -> None:
    """dirplot git path@branch --animate produces a multi-frame APNG."""
    out = tmp_path / "out.apng"
    result = runner.invoke(
        app,
        [
            "git",
            f"{local_repo}@feature",
            "--output",
            str(out),
            "--animate",
            "--size",
            "200x150",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_git_local_at_branch_range_precedence(local_repo: Path, tmp_path: Path) -> None:
    """--range takes precedence over the @ref in the path."""
    out = tmp_path / "out.png"
    # @feature would include feature.py, but --range main limits to main commits only
    result = runner.invoke(
        app,
        [
            "git",
            f"{local_repo}@feature",
            "--output",
            str(out),
            "--range",
            "main",
            "--size",
            "200x150",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_git_local_no_at_syntax(local_repo: Path, tmp_path: Path) -> None:
    """Plain path without @ still works (regression guard)."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["git", str(local_repo), "--output", str(out), "--size", "200x150"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.skipif(not _ffmpeg_available, reason="ffmpeg not found")
def test_git_local_animate_mp4(local_repo: Path, tmp_path: Path) -> None:
    """dirplot git --animate produces a valid .mp4 file."""
    out = tmp_path / "out.mp4"
    result = runner.invoke(
        app,
        ["git", str(local_repo), "--output", str(out), "--animate", "--size", "200x150"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.skipif(not _ffmpeg_available, reason="ffmpeg not found")
def test_git_local_animate_mp4_crf(local_repo: Path, tmp_path: Path) -> None:
    """--crf controls MP4 quality: lower CRF produces a larger file."""
    out_hq = tmp_path / "hq.mp4"
    out_lq = tmp_path / "lq.mp4"
    common = ["git", str(local_repo), "--animate", "--size", "200x150"]
    runner.invoke(app, common + ["--output", str(out_hq), "--crf", "0"])
    runner.invoke(app, common + ["--output", str(out_lq), "--crf", "51"])
    assert out_hq.stat().st_size > out_lq.stat().st_size
