"""Tests for the Typer CLI entry point."""

from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from typer.testing import CliRunner

from dirplot.main import app

runner = CliRunner()


def test_version_flag() -> None:
    from dirplot import __version__

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_invalid_path() -> None:
    result = runner.invoke(app, ["map", "/nonexistent/__dirplot_test__", "--no-show"])
    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_cli_single_file(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("hello")
    result = runner.invoke(app, ["map", str(f), "--no-show"])
    assert result.exit_code == 0


def test_cli_multiple_files(tmp_path: Path) -> None:
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_bytes(b"x" * 100)
    f2.write_bytes(b"x" * 200)
    result = runner.invoke(app, ["map", str(f1), str(f2), "--no-show"])
    assert result.exit_code == 0


def test_cli_bad_colormap(sample_tree: Path) -> None:
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show", "--colormap", "not_a_cmap"])
    assert result.exit_code == 1
    assert "Unknown colormap" in result.output


def test_cli_runs_successfully(sample_tree: Path) -> None:
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show"])
    assert result.exit_code == 0
    assert "Found" in result.output
    assert "files" in result.output


def test_cli_stdout_png(sample_tree: Path, tmp_path: Path) -> None:
    # Binary PNG can't cleanly round-trip through CliRunner's text capture;
    # pipe via --output - to a real file to verify the bytes.
    out = tmp_path / "via_stdout.png"
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dirplot",
            "map",
            str(sample_tree),
            "--no-show",
            "--output",
            "-",
            "--size",
            "100x100",
        ],
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout[:8] == b"\x89PNG\r\n\x1a\n"
    out.write_bytes(result.stdout)
    assert out.stat().st_size > 0


def test_cli_stdout_svg(sample_tree: Path) -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dirplot",
            "map",
            str(sample_tree),
            "--no-show",
            "--output",
            "-",
            "--format",
            "svg",
            "--size",
            "100x100",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("<?xml")
    assert "<?xml" not in result.stderr


def test_cli_saves_output(sample_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.png"
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show", "--output", str(output)])
    assert result.exit_code == 0
    assert output.exists()
    assert output.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_cli_exclude(sample_tree: Path) -> None:
    src = sample_tree / "src"
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show", "--exclude", str(src)])
    assert result.exit_code == 0
    # Only docs/ and README.md remain: 80 + 50 = 130 bytes
    assert "130" in result.output


def test_cli_show_window(sample_tree: Path) -> None:
    mock_img = MagicMock()
    with patch("PIL.Image.open", return_value=mock_img):
        result = runner.invoke(app, ["map", str(sample_tree), "--show"])
    assert result.exit_code == 0
    mock_img.show.assert_called_once()


def test_cli_show_inline(sample_tree: Path) -> None:
    from unittest.mock import mock_open

    m = mock_open()
    with patch("builtins.open", m):
        result = runner.invoke(app, ["map", str(sample_tree), "--show", "--inline"])
    assert result.exit_code == 0


def test_cli_custom_colormap(sample_tree: Path) -> None:
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show", "--colormap", "viridis"])
    assert result.exit_code == 0


def test_cli_custom_scale(sample_tree: Path) -> None:
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show", "--font-size", "14"])
    assert result.exit_code == 0


def test_cli_custom_size(sample_tree: Path) -> None:
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show", "--size", "800x600"])
    assert result.exit_code == 0
    assert "800x600" in result.output


def test_cli_invalid_size(sample_tree: Path) -> None:
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show", "--size", "notasize"])
    assert result.exit_code == 1
    assert "Invalid --size" in result.output


def test_cli_termsize() -> None:
    result = runner.invoke(app, ["termsize"])
    assert result.exit_code == 0
    assert "cols" in result.output
    assert "rows" in result.output
    assert "×" in result.output


def test_read_meta_png(sample_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.png"
    runner.invoke(app, ["map", str(sample_tree), "--no-show", "--output", str(output)])
    result = runner.invoke(app, ["read-meta", str(output)])
    assert result.exit_code == 0
    assert "Date:" in result.output
    assert "Software:" in result.output
    assert "dirplot" in result.output
    assert "Command:" in result.output


def test_read_meta_svg(sample_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.svg"
    runner.invoke(
        app, ["map", str(sample_tree), "--no-show", "--output", str(output), "--format", "svg"]
    )
    result = runner.invoke(app, ["read-meta", str(output)])
    assert result.exit_code == 0
    assert "Date:" in result.output
    assert "Software:" in result.output
    assert "dirplot" in result.output
    assert "Command:" in result.output


def test_read_meta_missing_file() -> None:
    result = runner.invoke(app, ["read-meta", "/nonexistent/file.png"])
    assert result.exit_code == 1


def test_read_meta_unsupported_type(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("hello")
    result = runner.invoke(app, ["read-meta", str(f)])
    assert result.exit_code == 1
    assert "Unsupported" in result.output


def test_read_meta_png_no_metadata(tmp_path: Path) -> None:
    from PIL import Image

    img = Image.new("RGB", (10, 10))
    p = tmp_path / "plain.png"
    img.save(p, format="PNG")
    result = runner.invoke(app, ["read-meta", str(p)])
    assert result.exit_code == 1
    assert "No dirplot metadata" in result.output


def test_read_meta_svg_no_metadata(tmp_path: Path) -> None:
    p = tmp_path / "plain.svg"
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
    result = runner.invoke(app, ["read-meta", str(p)])
    assert result.exit_code == 1
    assert "No dirplot metadata" in result.output


def test_read_meta_multiple_files(sample_tree: Path, tmp_path: Path) -> None:
    out1 = tmp_path / "out1.png"
    out2 = tmp_path / "out2.png"
    runner.invoke(app, ["map", str(sample_tree), "--no-show", "--output", str(out1)])
    runner.invoke(app, ["map", str(sample_tree), "--no-show", "--output", str(out2)])
    result = runner.invoke(app, ["read-meta", str(out1), str(out2)])
    assert result.exit_code == 0
    assert f"==> {out1} <==" in result.output
    assert f"==> {out2} <==" in result.output
    assert result.output.count("Date:") == 2


def test_read_meta_multiple_files_partial_error(sample_tree: Path, tmp_path: Path) -> None:
    out1 = tmp_path / "out1.png"
    runner.invoke(app, ["map", str(sample_tree), "--no-show", "--output", str(out1)])
    result = runner.invoke(app, ["read-meta", str(out1), "/nonexistent/file.png"])
    assert result.exit_code == 1
    assert "Date:" in result.output
    assert "file not found" in result.output


def test_watch_single_path(sample_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.png"
    mock_obs = MagicMock()
    with (
        patch("dirplot.watch.build_tree_multi"),
        patch("dirplot.watch.create_treemap") as mock_render,
        patch("watchdog.observers.Observer", return_value=mock_obs),
        patch("dirplot.main.time.sleep", side_effect=KeyboardInterrupt),
    ):
        mock_render.return_value = MagicMock(read=lambda: b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        result = runner.invoke(
            app, ["watch", str(sample_tree), "--output", str(output), "--size", "100x100"]
        )
    assert result.exit_code == 0
    mock_obs.schedule.assert_called_once_with(ANY, str(sample_tree.resolve()), recursive=True)


def test_watch_multiple_paths(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    output = tmp_path / "out.png"
    mock_obs = MagicMock()
    with (
        patch("dirplot.watch.build_tree_multi"),
        patch("dirplot.watch.create_treemap") as mock_render,
        patch("watchdog.observers.Observer", return_value=mock_obs),
        patch("dirplot.main.time.sleep", side_effect=KeyboardInterrupt),
    ):
        mock_render.return_value = MagicMock(read=lambda: b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        result = runner.invoke(
            app,
            ["watch", str(dir_a), str(dir_b), "--output", str(output), "--size", "100x100"],
        )
    assert result.exit_code == 0
    scheduled_paths = {call.args[1] for call in mock_obs.schedule.call_args_list}
    assert scheduled_paths == {str(dir_a.resolve()), str(dir_b.resolve())}


def test_watch_debounce_coalesces(sample_tree: Path, tmp_path: Path) -> None:
    import time
    from unittest.mock import patch

    from dirplot.watch import TreemapEventHandler

    output = tmp_path / "out.png"
    with (
        patch("dirplot.watch.build_tree_multi"),
        patch("dirplot.watch.create_treemap") as mock_render,
    ):
        mock_render.return_value = MagicMock(read=lambda: b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        handler = TreemapEventHandler(
            [sample_tree.resolve()],
            output,
            width_px=100,
            height_px=100,
            font_size=12,
            colormap="tab20",
            cushion=True,
            debounce=0.1,
        )
        regenerate_calls = []
        original = handler._regenerate
        handler._regenerate = lambda: regenerate_calls.append(1) or original()

        for _ in range(5):
            handler._schedule_regenerate()

        assert len(regenerate_calls) == 0
        time.sleep(0.3)
        assert len(regenerate_calls) == 1


def test_watch_flush_fires_pending(sample_tree: Path, tmp_path: Path) -> None:
    from unittest.mock import patch

    from dirplot.watch import TreemapEventHandler

    output = tmp_path / "out.png"
    with (
        patch("dirplot.watch.build_tree_multi"),
        patch("dirplot.watch.create_treemap") as mock_render,
    ):
        mock_render.return_value = MagicMock(read=lambda: b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        handler = TreemapEventHandler(
            [sample_tree.resolve()],
            output,
            width_px=100,
            height_px=100,
            font_size=12,
            colormap="tab20",
            cushion=True,
            debounce=60.0,
        )
        regenerate_calls = []
        original = handler._regenerate
        handler._regenerate = lambda: regenerate_calls.append(1) or original()

        handler._schedule_regenerate()
        assert len(regenerate_calls) == 0

        handler.flush()
        assert len(regenerate_calls) == 1


def test_watch_event_log_written(tmp_path: Path) -> None:
    from dirplot.watch import TreemapEventHandler

    output = tmp_path / "out.png"
    log_file = tmp_path / "events.jsonl"
    handler = TreemapEventHandler(
        [tmp_path],
        output,
        width_px=100,
        height_px=100,
        font_size=12,
        colormap="tab20",
        cushion=True,
        event_log=log_file,
    )
    handler._events = [
        {"timestamp": 1.0, "type": "created", "path": "/foo/bar.txt", "dest_path": None},
        {"timestamp": 2.0, "type": "modified", "path": "/foo/bar.txt", "dest_path": None},
    ]
    handler.flush()

    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    import json

    first = json.loads(lines[0])
    assert first["type"] == "created"
    assert first["path"] == "/foo/bar.txt"


def test_watch_invalid_path(tmp_path: Path) -> None:
    output = tmp_path / "out.png"
    result = runner.invoke(app, ["watch", "/nonexistent/__dirplot_test__", "--output", str(output)])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_watch_missing_watchdog(sample_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.png"
    with patch.dict("sys.modules", {"watchdog.observers": None}):
        result = runner.invoke(
            app, ["watch", str(sample_tree), "--output", str(output), "--size", "100x100"]
        )
    assert result.exit_code == 1
    assert "watchdog" in result.output


def test_main_module() -> None:
    """__main__.py delegates to app."""
    from dirplot.__main__ import main

    with patch("dirplot.__main__.app") as mock_app:
        main()
        mock_app.assert_called_once()


# ---------------------------------------------------------------------------
# --paths-from and stdin path-list mode
# ---------------------------------------------------------------------------


def test_paths_from_find_format(tmp_path: Path, sample_tree: Path) -> None:
    """--paths-from FILE with find-style output (one path per line)."""
    paths_file = tmp_path / "paths.txt"
    # Write two real sub-paths from sample_tree
    children = sorted(sample_tree.iterdir())[:2]
    paths_file.write_text("\n".join(str(c) for c in children) + "\n")
    result = runner.invoke(
        app, ["map", "--paths-from", str(paths_file), "--no-show", "--size", "100x100"]
    )
    assert result.exit_code == 0, result.output


def test_paths_from_stdin_find_format(tmp_path: Path, sample_tree: Path) -> None:
    """Pipe find-style path list via stdin."""
    import subprocess
    import sys

    children = sorted(sample_tree.iterdir())[:2]
    stdin_data = "\n".join(str(c) for c in children) + "\n"
    result = subprocess.run(
        [sys.executable, "-m", "dirplot", "map", "--no-show", "--size", "100x100"],
        input=stdin_data.encode(),
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_paths_from_tree_format(tmp_path: Path, sample_tree: Path) -> None:
    """--paths-from FILE with tree-style output."""
    import subprocess

    # Generate real tree output from sample_tree
    tree_result = subprocess.run(["tree", str(sample_tree)], capture_output=True, text=True)
    if tree_result.returncode != 0:
        pytest.skip("tree command not available")

    paths_file = tmp_path / "tree.txt"
    paths_file.write_text(tree_result.stdout)
    result = runner.invoke(
        app, ["map", "--paths-from", str(paths_file), "--no-show", "--size", "100x100"]
    )
    assert result.exit_code == 0, result.output


def test_paths_from_conflicts_with_positional(sample_tree: Path, tmp_path: Path) -> None:
    """Combining --paths-from with positional args must error."""
    paths_file = tmp_path / "paths.txt"
    paths_file.write_text(str(sample_tree) + "\n")
    result = runner.invoke(
        app, ["map", str(sample_tree), "--paths-from", str(paths_file), "--no-show"]
    )
    assert result.exit_code == 1
    assert "cannot combine" in result.output.lower()


def test_paths_from_nonexistent_file(sample_tree: Path) -> None:
    result = runner.invoke(
        app, ["map", "--paths-from", "/nonexistent/__dirplot_test_paths__.txt", "--no-show"]
    )
    assert result.exit_code == 1
    assert "does not exist" in result.output
