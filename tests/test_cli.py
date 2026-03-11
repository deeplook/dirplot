"""Tests for the Typer CLI entry point."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_cli_not_a_directory(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("hello")
    result = runner.invoke(app, ["map", str(f), "--no-show"])
    assert result.exit_code == 1
    assert "Not a directory" in result.output


def test_cli_bad_colormap(sample_tree: Path) -> None:
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show", "--colormap", "not_a_cmap"])
    assert result.exit_code == 1
    assert "Unknown colormap" in result.output


def test_cli_runs_successfully(sample_tree: Path) -> None:
    result = runner.invoke(app, ["map", str(sample_tree), "--no-show"])
    assert result.exit_code == 0
    assert "Found" in result.output
    assert "files" in result.output


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


def test_main_module() -> None:
    """__main__.py delegates to app."""
    from dirplot.__main__ import main

    with patch("dirplot.__main__.app") as mock_app:
        main()
        mock_app.assert_called_once()
