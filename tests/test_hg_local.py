"""Integration tests for dirplot hg with a local Mercurial repository."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dirplot.main import app

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not shutil.which("hg"),
    reason="hg CLI not found",
)

_ffmpeg_available = bool(shutil.which("ffmpeg"))


@pytest.fixture()
def local_hg_repo(tmp_path: Path) -> Path:
    """Create a minimal local Mercurial repo with two commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["hg", "init", str(repo)], check=True, capture_output=True)
    (repo / "hello.py").write_text("print('hello')\n")
    subprocess.run(["hg", "add", "hello.py"], check=True, capture_output=True, cwd=str(repo))
    subprocess.run(
        [
            "hg",
            "commit",
            "-m",
            "first",
            "-u",
            "T <t@t.com>",
            "-d",
            "2024-01-01 00:00:00 +0000",
        ],
        check=True,
        capture_output=True,
        cwd=str(repo),
    )
    (repo / "world.py").write_text("print('world')\n")
    subprocess.run(["hg", "add", "world.py"], check=True, capture_output=True, cwd=str(repo))
    subprocess.run(
        [
            "hg",
            "commit",
            "-m",
            "second",
            "-u",
            "T <t@t.com>",
        ],
        check=True,
        capture_output=True,
        cwd=str(repo),
    )
    return repo


def test_hg_local_static_png(local_hg_repo: Path, tmp_path: Path) -> None:
    """dirplot hg renders a static PNG for the final changeset."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["hg", str(local_hg_repo), "--output", str(out), "--canvas", "200x150"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_hg_local_animate_apng(local_hg_repo: Path, tmp_path: Path) -> None:
    """dirplot hg --range produces a multi-frame APNG."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        [
            "hg",
            str(local_hg_repo),
            "--output",
            str(out),
            "--range",
            "0:tip",
            "--canvas",
            "200x150",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_hg_local_at_rev_syntax(local_hg_repo: Path, tmp_path: Path) -> None:
    """path@rev syntax passes a revision range to hg_log."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["hg", f"{local_hg_repo}@tip", "--output", str(out), "--canvas", "200x150"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_hg_not_installed(local_hg_repo: Path, tmp_path: Path) -> None:
    """When hg is not on PATH, exit 1 with a helpful install hint."""
    out = tmp_path / "out.png"
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(shutil, "which", lambda cmd: None if cmd == "hg" else shutil.which(cmd))
        result = runner.invoke(
            app,
            ["hg", str(local_hg_repo), "--output", str(out), "--canvas", "200x150"],
        )
    assert result.exit_code == 1
    assert "hg not found" in result.output or "not found" in result.output


def test_hg_not_a_repo(tmp_path: Path) -> None:
    """Pointing at a non-hg directory exits 1 with a clear error."""
    not_a_repo = tmp_path / "notarepo"
    not_a_repo.mkdir()
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["hg", str(not_a_repo), "--output", str(out), "--canvas", "200x150"],
    )
    assert result.exit_code == 1
    assert "not a Mercurial repository" in result.output


@pytest.fixture()
def local_hg_repo_3(tmp_path: Path) -> Path:
    """Local Mercurial repo with three commits (for --first/--last ordering tests)."""
    repo = tmp_path / "repo3"
    repo.mkdir()
    subprocess.run(["hg", "init", str(repo)], check=True, capture_output=True)

    def commit(filename: str, content: str, message: str, date: str) -> None:
        (repo / filename).write_text(content)
        subprocess.run(["hg", "add", filename], check=True, capture_output=True, cwd=str(repo))
        subprocess.run(
            ["hg", "commit", "-m", message, "-u", "T <t@t.com>", "-d", date],
            check=True,
            capture_output=True,
            cwd=str(repo),
        )

    commit("a.py", "a\n", "first", "2024-01-01 00:00:00 +0000")
    commit("b.py", "b\n", "second", "2024-01-02 00:00:00 +0000")
    commit("c.py", "c\n", "third", "2024-01-03 00:00:00 +0000")
    return repo


# ---------------------------------------------------------------------------
# --period tests
# ---------------------------------------------------------------------------


def test_hg_period_includes_recent_commits(local_hg_repo: Path, tmp_path: Path) -> None:
    """--period 1h animates recently-made commits."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["hg", str(local_hg_repo), "--output", str(out), "--canvas", "200x150", "--period", "1h"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0


def test_hg_period_invalid_value(local_hg_repo: Path, tmp_path: Path) -> None:
    """--period with an unrecognised unit exits 1."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["hg", str(local_hg_repo), "--output", str(out), "--canvas", "200x150", "--period", "3y"],
    )
    assert result.exit_code == 1
    assert "Invalid --period" in result.output


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------


def test_hg_inline_with_range_rejected(local_hg_repo: Path) -> None:
    """--inline is rejected when --range is given (animation mode)."""
    result = runner.invoke(
        app,
        ["hg", str(local_hg_repo), "--inline", "--range", "0:tip", "--canvas", "200x150"],
    )
    assert result.exit_code == 1
    assert "single-frame" in result.output or "--inline" in result.output


def test_hg_first_last_mutually_exclusive(local_hg_repo: Path, tmp_path: Path) -> None:
    """--first and --last together exit 1."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        [
            "hg",
            str(local_hg_repo),
            "--output",
            str(out),
            "--range",
            "0:tip",
            "--first",
            "1",
            "--last",
            "1",
            "--canvas",
            "200x150",
        ],
    )
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_hg_first_without_animation_mode_rejected(local_hg_repo: Path, tmp_path: Path) -> None:
    """--first without --range or --period exits 1."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["hg", str(local_hg_repo), "--output", str(out), "--first", "1", "--canvas", "200x150"],
    )
    assert result.exit_code == 1
    assert "--range" in result.output or "--period" in result.output


# ---------------------------------------------------------------------------
# --first / --last functional tests
# ---------------------------------------------------------------------------


def test_hg_first_n_animate(local_hg_repo_3: Path, tmp_path: Path) -> None:
    """--range 0:tip --first 2 produces a 2-frame animation."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        [
            "hg",
            str(local_hg_repo_3),
            "--output",
            str(out),
            "--range",
            "0:tip",
            "--first",
            "2",
            "--canvas",
            "200x150",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0
    assert "Animating 2" in result.output


def test_hg_last_n_animate(local_hg_repo_3: Path, tmp_path: Path) -> None:
    """--range 0:tip --last 1 produces a 1-frame animation."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        [
            "hg",
            str(local_hg_repo_3),
            "--output",
            str(out),
            "--range",
            "0:tip",
            "--last",
            "1",
            "--canvas",
            "200x150",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0
    assert "Animating 1" in result.output


def test_hg_first_vs_last_select_different_changesets(
    local_hg_repo_3: Path, tmp_path: Path
) -> None:
    """--first 1 picks the oldest changeset; --last 1 picks the newest."""
    out_first = tmp_path / "first.png"
    out_last = tmp_path / "last.png"
    result_first = runner.invoke(
        app,
        [
            "hg",
            str(local_hg_repo_3),
            "--output",
            str(out_first),
            "--range",
            "0:tip",
            "--first",
            "1",
            "--canvas",
            "200x150",
        ],
    )
    result_last = runner.invoke(
        app,
        [
            "hg",
            str(local_hg_repo_3),
            "--output",
            str(out_last),
            "--range",
            "0:tip",
            "--last",
            "1",
            "--canvas",
            "200x150",
        ],
    )
    assert result_first.exit_code == 0, result_first.output
    assert result_last.exit_code == 0, result_last.output
    assert "first" in result_first.output
    assert "third" in result_last.output
