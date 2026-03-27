"""Integration test: dirplot git with a real GitHub URL (requires network + git CLI)."""

import shutil
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dirplot.main import app

runner = CliRunner()


def _github_reachable() -> bool:
    try:
        with socket.create_connection(("github.com", 443), timeout=5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not shutil.which("git") or not _github_reachable(),
    reason="git CLI not found or GitHub not reachable",
)


def test_git_github_animate(tmp_path: Path) -> None:
    """Blobless-clone dirplot/dirplot and render the last 10 commits as an APNG."""
    out = tmp_path / "history.png"
    result = runner.invoke(
        app,
        [
            "git",
            "github://deeplook/dirplot",
            "--output",
            str(out),
            "--animate",
            "--max-commits",
            "10",
            "--size",
            "400x300",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0
