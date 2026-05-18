"""Tests for Makefile defaults."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="make not available on Windows")
@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_defaults_to_help() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["make", "-n"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    # MAKEFILE_LIST may expand with a leading space, so normalise whitespace.
    normalised = " ".join(result.stdout.split())
    assert "grep -E '^[a-zA-Z_-]+:.*##' Makefile" in normalised
    assert "publish --token" not in result.stdout
