"""Tests for dirplot git with local repositories, including the .@ref syntax."""

import os
import shutil
import subprocess
from datetime import datetime as dt
from datetime import timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dirplot.main import app, parse_last_period

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


# ---------------------------------------------------------------------------
# parse_last_period unit tests
# ---------------------------------------------------------------------------


def test_parse_last_period_hours() -> None:
    before = dt.now(tz=timezone.utc)
    result = parse_last_period("24h")
    expected = before - timedelta(hours=24)
    assert abs((result - expected).total_seconds()) < 5


def test_parse_last_period_days() -> None:
    before = dt.now(tz=timezone.utc)
    result = parse_last_period("10d")
    expected = before - timedelta(days=10)
    assert abs((result - expected).total_seconds()) < 5


def test_parse_last_period_weeks() -> None:
    result = parse_last_period("2w")
    expected = dt.now(tz=timezone.utc) - timedelta(weeks=2)
    assert abs((result - expected).total_seconds()) < 5


def test_parse_last_period_months() -> None:
    """'1mo' parses as 30 days, not mis-read as '1m' (minutes)."""
    result = parse_last_period("1mo")
    expected = dt.now(tz=timezone.utc) - timedelta(days=30)
    assert abs((result - expected).total_seconds()) < 5


def test_parse_last_period_minutes() -> None:
    result = parse_last_period("30m")
    expected = dt.now(tz=timezone.utc) - timedelta(minutes=30)
    assert abs((result - expected).total_seconds()) < 5


def test_parse_last_period_returns_utc() -> None:
    result = parse_last_period("1h")
    assert result.tzinfo == timezone.utc


def test_parse_last_period_invalid_unit() -> None:
    with pytest.raises(ValueError, match="Invalid --last"):
        parse_last_period("3y")


def test_parse_last_period_no_number() -> None:
    with pytest.raises(ValueError, match="Invalid --last"):
        parse_last_period("d")


def test_parse_last_period_empty() -> None:
    with pytest.raises(ValueError, match="Invalid --last"):
        parse_last_period("")


# ---------------------------------------------------------------------------
# --last integration tests
# ---------------------------------------------------------------------------


def test_git_last_includes_recent_commits(local_repo: Path, tmp_path: Path) -> None:
    """--last 1h includes commits made moments ago."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["git", str(local_repo), "--output", str(out), "--size", "200x150", "--last", "1h"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0


def test_git_last_invalid_value(local_repo: Path, tmp_path: Path) -> None:
    """--last with an unrecognised unit exits 1 with a clear error."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["git", str(local_repo), "--output", str(out), "--size", "200x150", "--last", "3y"],
    )
    assert result.exit_code == 1
    assert "Invalid --last" in result.output


def test_git_last_combined_with_max_commits(local_repo: Path, tmp_path: Path) -> None:
    """--last and --max-commits can be combined (date filter + count cap)."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        [
            "git",
            str(local_repo),
            "--output",
            str(out),
            "--size",
            "200x150",
            "--last",
            "1h",
            "--max-commits",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0


@pytest.fixture()
def repo_with_old_base(tmp_path: Path) -> Path:
    """Repo whose initial commit is dated year 2000; two recent commits sit on top."""
    repo = tmp_path / "oldrepo"
    repo.mkdir()
    base_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    def git(*args: str, extra_env: dict | None = None) -> None:
        env = {**base_env, **(extra_env or {})}
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")

    # Initial commit dated far in the past
    (repo / "old.py").write_text("# old\n")
    git("add", "old.py")
    git(
        "commit",
        "-m",
        "old commit",
        extra_env={
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
        },
    )

    # Two recent commits on top (current time)
    (repo / "a.py").write_text("a\n")
    git("add", "a.py")
    git("commit", "-m", "recent a")

    (repo / "b.py").write_text("b\n")
    git("add", "b.py")
    git("commit", "-m", "recent b")

    return repo


def test_git_last_excludes_old_commits(repo_with_old_base: Path, tmp_path: Path) -> None:
    """--last 1h returns only the 2 recent commits, excluding the year-2000 base."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["git", str(repo_with_old_base), "--output", str(out), "--size", "200x150", "--last", "1h"],
    )
    assert result.exit_code == 0, result.output
    # 3 commits total on HEAD, only 2 pass the --last 1h filter
    assert "Replaying 2 of 3" in result.output
    assert "filtered by --last 1h" in result.output
