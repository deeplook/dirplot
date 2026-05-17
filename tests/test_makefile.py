"""Tests for Makefile defaults."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_make_defaults_to_help() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["make", "-n"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "grep -E '^[a-zA-Z_-]+:.*##'  Makefile" in result.stdout
    assert "publish --token" not in result.stdout
