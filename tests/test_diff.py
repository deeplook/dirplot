"""Tests for the ``dirplot diff`` command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dirplot.main import app

runner = CliRunner()


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
        ["diff", str(tree_a), str(tree_b), "--output", str(out), "--size", "300x200", "--no-show"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.stat().st_size > 0


def test_diff_reports_counts(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app,
        ["diff", str(tree_a), str(tree_b), "--output", str(out), "--size", "300x200", "--no-show"],
    )
    assert result.exit_code == 0, result.output
    # 2 added (added.py, sub/sub_added.py), 2 removed (removed.py, sub/sub_removed.py), 1 changed
    assert "2 added" in result.output
    assert "2 removed" in result.output
    assert "1 changed" in result.output


def test_diff_invalid_tree_a(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["diff", str(tmp_path / "nonexistent"), str(tmp_path), "--size", "300x200", "--no-show"],
    )
    assert result.exit_code == 1


def test_diff_invalid_tree_b(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["diff", str(tmp_path), str(tmp_path / "nonexistent"), "--size", "300x200", "--no-show"],
    )
    assert result.exit_code == 1


def test_diff_identical_trees(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.py").write_bytes(b"x" * 100)
    out = tmp_path / "diff.png"
    result = runner.invoke(
        app, ["diff", str(root), str(root), "--output", str(out), "--size", "300x200", "--no-show"]
    )
    assert result.exit_code == 0, result.output
    assert "0 added" in result.output
    assert "0 removed" in result.output
    assert "0 changed" in result.output


def test_diff_svg_output(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    out = tmp_path / "diff.svg"
    result = runner.invoke(
        app,
        ["diff", str(tree_a), str(tree_b), "--output", str(out), "--size", "300x200", "--no-show"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    content = out.read_text()
    assert "<svg" in content


def test_diff_no_context(tree_a: Path, tree_b: Path, tmp_path: Path) -> None:
    """--no-context produces a smaller image (fewer tiles) than --context."""
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
            "--size",
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
            "--size",
            "300x200",
            "--no-show",
            "--no-context",
        ],
    )
    assert out_ctx.exists() and out_noctx.exists()
    # --no-context excludes unchanged files so the image should differ
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
            "--size",
            "300x200",
            "--no-show",
            "--light",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
