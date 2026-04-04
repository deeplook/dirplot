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
        ["hg", str(local_hg_repo), "--output", str(out), "--size", "200x150"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_hg_local_animate_apng(local_hg_repo: Path, tmp_path: Path) -> None:
    """dirplot hg --animate produces a multi-frame APNG."""
    out = tmp_path / "out.apng"
    result = runner.invoke(
        app,
        [
            "hg",
            str(local_hg_repo),
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


def test_hg_local_at_rev_syntax(local_hg_repo: Path, tmp_path: Path) -> None:
    """path@rev syntax passes a revision range to hg_log."""
    out = tmp_path / "out.png"
    result = runner.invoke(
        app,
        ["hg", f"{local_hg_repo}@tip", "--output", str(out), "--size", "200x150"],
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
            ["hg", str(local_hg_repo), "--output", str(out), "--size", "200x150"],
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
        ["hg", str(not_a_repo), "--output", str(out), "--size", "200x150"],
    )
    assert result.exit_code == 1
    assert "not a Mercurial repository" in result.output
