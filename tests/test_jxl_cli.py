"""CLI coverage for JPEG XL output across supported commands."""

from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from dirplot.main import app
from dirplot.scanner import Node

runner = CliRunner()


@pytest.mark.parametrize(
    ("output_name", "format_args"),
    [("diff.jxl", []), ("diff.data", ["--format", "jxl"])],
)
def test_diff_jxl_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_name: str,
    format_args: list[str],
) -> None:
    import dirplot.image_formats

    monkeypatch.setattr(dirplot.image_formats, "encode_jxl", lambda _buf: BytesIO(b"mock-jxl"))
    tree_a = tmp_path / "a"
    tree_b = tmp_path / "b"
    tree_a.mkdir()
    tree_b.mkdir()
    (tree_a / "file.txt").write_text("before")
    (tree_b / "file.txt").write_text("after")
    output = tmp_path / output_name
    result = runner.invoke(
        app,
        [
            "diff",
            str(tree_a),
            str(tree_b),
            "--no-show",
            "--canvas",
            "100x100",
            "--output",
            str(output),
            *format_args,
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.read_bytes() == b"mock-jxl"


@pytest.mark.parametrize(("command", "repo_marker"), [("git", ".git"), ("hg", ".hg")])
def test_vcs_jxl_snapshot(
    command: str,
    repo_marker: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dirplot.git_scanner as git_scanner
    import dirplot.hg_scanner as hg_scanner
    import dirplot.image_formats
    import dirplot.render_png

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / repo_marker).mkdir()
    output = tmp_path / f"{command}.jxl"
    node = Node(name="repo", path=repo, size=4, is_dir=True)

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/mock-vcs")
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout="1\n"))
    monkeypatch.setattr(git_scanner, "git_log", lambda *_args: [("a" * 40, 1_700_000_000, "first")])
    monkeypatch.setattr(git_scanner, "git_initial_files", lambda *_args: {"file.txt": 4})
    monkeypatch.setattr(hg_scanner, "hg_log", lambda *_args: [("b" * 40, 1_700_000_000, "first")])
    monkeypatch.setattr(hg_scanner, "hg_initial_files", lambda *_args: {"file.txt": 4})
    monkeypatch.setattr(git_scanner, "build_node_tree", lambda *_args: node)
    monkeypatch.setattr(hg_scanner, "build_node_tree", lambda *_args: node)
    monkeypatch.setattr(
        dirplot.render_png, "create_treemap", lambda *_args, **_kwargs: BytesIO(b"mock-png")
    )
    monkeypatch.setattr(dirplot.image_formats, "encode_jxl", lambda _buf: BytesIO(b"mock-jxl"))

    result = runner.invoke(
        app,
        [command, str(repo), "--output", str(output), "--canvas", "100x100", "--quiet"],
    )

    assert result.exit_code == 0, result.output
    assert output.read_bytes() == b"mock-jxl"


@pytest.mark.parametrize(("command", "revision_range"), [("git", "HEAD~1..HEAD"), ("hg", "0:tip")])
def test_vcs_jxl_rejected_for_animations(
    command: str,
    revision_range: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / f"{command}.jxl"
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/mock-vcs")

    result = runner.invoke(
        app,
        [command, ".", "--range", revision_range, "--output", str(output)],
    )

    assert result.exit_code == 1
    assert "animation --output must be a .png (APNG), .mp4, or .mov" in result.output
    assert not output.exists()


def test_watch_jxl_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dirplot.image_formats
    from dirplot.watch import TreemapEventHandler

    (tmp_path / "file.txt").write_text("contents")
    output = tmp_path / "watch.jxl"
    monkeypatch.setattr(dirplot.image_formats, "encode_jxl", lambda _buf: BytesIO(b"mock-jxl"))
    handler = TreemapEventHandler(
        [tmp_path],
        snapshot=output,
        width_px=100,
        height_px=100,
        font_size=12,
        colormap="tab20",
        cushion=False,
    )

    handler._regenerate()

    assert output.read_bytes() == b"mock-jxl"
