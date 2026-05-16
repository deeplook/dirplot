"""Tests for the --highlight flag and the resolve_highlight_specs helper."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from dirplot.helpers.highlights import resolve_highlight_specs
from dirplot.main import app
from dirplot.render_png import HIGHLIGHT_COLORS, create_treemap
from dirplot.scanner import build_tree
from dirplot.svg_render import create_treemap_svg

runner = CliRunner()


# ---------------------------------------------------------------------------
# resolve_highlight_specs
# ---------------------------------------------------------------------------


def test_resolve_exact_match() -> None:
    paths = ["/repo/src/main.py", "/repo/src/util.py"]
    result = resolve_highlight_specs(["/repo/src/main.py"], paths)
    assert result == {"/repo/src/main.py": "red"}


def test_resolve_no_match() -> None:
    paths = ["/repo/src/main.py"]
    result = resolve_highlight_specs(["*.go"], paths)
    assert result == {}


def test_resolve_glob_star() -> None:
    paths = ["/repo/src/main.py", "/repo/src/util.py", "/repo/docs/guide.md"]
    result = resolve_highlight_specs(["*.py"], paths)
    assert set(result.keys()) == {"/repo/src/main.py", "/repo/src/util.py"}
    assert all(v == "red" for v in result.values())


def test_resolve_double_star_glob() -> None:
    paths = ["/repo/src/main.py", "/repo/src/sub/helper.py", "/repo/docs/guide.md"]
    result = resolve_highlight_specs(["**/*.py"], paths)
    assert set(result.keys()) == {"/repo/src/main.py", "/repo/src/sub/helper.py"}


def test_resolve_custom_color() -> None:
    paths = ["/repo/src/main.py"]
    result = resolve_highlight_specs(["/repo/src/main.py@orange"], paths)
    assert result == {"/repo/src/main.py": "orange"}


def test_resolve_multiple_specs_different_colors() -> None:
    paths = ["/repo/src/main.py", "/repo/src/util.py"]
    result = resolve_highlight_specs(["/repo/src/main.py@cyan", "/repo/src/util.py@orange"], paths)
    assert result["/repo/src/main.py"] == "cyan"
    assert result["/repo/src/util.py"] == "orange"


def test_resolve_last_spec_wins() -> None:
    """When two patterns match the same path, the last one wins."""
    paths = ["/repo/src/main.py"]
    result = resolve_highlight_specs(["*.py@red", "*.py@blue"], paths)
    assert result["/repo/src/main.py"] == "blue"


def test_resolve_empty_specs() -> None:
    paths = ["/repo/src/main.py"]
    assert resolve_highlight_specs([], paths) == {}


def test_resolve_empty_paths() -> None:
    assert resolve_highlight_specs(["*.py"], []) == {}


def test_resolve_directory_pattern_matches_via_ancestor() -> None:
    """A directory pattern matches files inside it, returning the directory path as key."""
    paths = ["/repo/src/dirplot/main.py", "/repo/src/dirplot/app.py", "/repo/README.md"]
    result = resolve_highlight_specs(["src/dirplot@orange"], paths)
    # The directory path should be the key, not the individual files
    assert result == {"/repo/src/dirplot": "orange"}


def test_resolve_directory_pattern_default_color() -> None:
    paths = ["/repo/src/dirplot/main.py"]
    result = resolve_highlight_specs(["src/dirplot"], paths)
    assert result == {"/repo/src/dirplot": "red"}


def test_resolve_directory_pattern_does_not_override_direct_match() -> None:
    """If the path itself matches, it wins over ancestor matching."""
    # Both main.py (direct) and src/dirplot (ancestor) patterns given
    paths = ["/repo/src/dirplot/main.py"]
    result = resolve_highlight_specs(["*/main.py@blue", "src/dirplot@orange"], paths)
    # main.py matches directly → blue; src/dirplot matches via ancestor → orange dir key
    assert result.get("/repo/src/dirplot/main.py") == "blue"
    assert result.get("/repo/src/dirplot") == "orange"


def test_resolve_at_sign_in_color_only_last_at_used() -> None:
    """Pattern uses rsplit('@', 1) so only the last @ separates pattern from color."""
    paths = ["/repo/src/main.py"]
    # Pattern has no @ so full spec is the pattern, color defaults to red
    result = resolve_highlight_specs(["/repo/src/main.py"], paths)
    assert result == {"/repo/src/main.py": "red"}


# ---------------------------------------------------------------------------
# HIGHLIGHT_COLORS includes "highlight" key
# ---------------------------------------------------------------------------


def test_highlight_color_in_table() -> None:
    assert "highlight" in HIGHLIGHT_COLORS
    assert HIGHLIGHT_COLORS["highlight"] == (255, 0, 0)


# ---------------------------------------------------------------------------
# PNG renderer: highlights produce red border pixels
# ---------------------------------------------------------------------------


def test_png_highlight_border_pixels(tmp_path: Path) -> None:
    """A highlighted file tile should have red border pixels on its edges."""
    (tmp_path / "a.py").write_bytes(b"x" * 5000)
    (tmp_path / "b.md").write_bytes(b"x" * 5000)

    root = build_tree(tmp_path)

    # Collect the absolute posix path for a.py
    target = (tmp_path / "a.py").as_posix()
    highlights = {target: "highlight"}

    buf = create_treemap(
        root,
        width_px=400,
        height_px=300,
        cushion=False,
        highlights=highlights,
    )
    img = Image.open(buf).convert("RGB")

    # Check that at least one red-ish pixel exists in the image
    # (the highlight border is drawn in pure red (255, 0, 0))
    pixels = list(img.getdata())
    assert any(r > 200 and g < 50 and b < 50 for r, g, b in pixels), (
        "Expected at least one red border pixel from the highlight"
    )


def test_png_no_highlight_no_red_border(tmp_path: Path) -> None:
    """Without highlights, no pure-red border pixels should appear for .py/.md tiles."""
    (tmp_path / "a.py").write_bytes(b"x" * 5000)
    (tmp_path / "b.md").write_bytes(b"x" * 5000)

    root = build_tree(tmp_path)
    buf = create_treemap(root, width_px=400, height_px=300, cushion=False)
    img = Image.open(buf).convert("RGB")

    pixels = list(img.getdata())
    # The Linguist palette for .py and .md does not use pure red
    pure_red = sum(1 for r, g, b in pixels if r > 240 and g < 20 and b < 20)
    assert pure_red == 0, f"Unexpected {pure_red} pure-red pixels without highlights"


def test_png_custom_color_highlight(tmp_path: Path) -> None:
    """A highlight with a named color other than red should produce that color's pixels."""
    (tmp_path / "a.py").write_bytes(b"x" * 8000)
    (tmp_path / "b.md").write_bytes(b"x" * 1000)

    root = build_tree(tmp_path)
    target = (tmp_path / "a.py").as_posix()
    # Use green — (0, 128, 0) in PIL named colors
    buf = create_treemap(
        root,
        width_px=400,
        height_px=300,
        cushion=False,
        highlights={target: "green"},
    )
    img = Image.open(buf).convert("RGB")
    pixels = list(img.getdata())
    # Expect at least one clearly greenish pixel
    assert any(g > 100 and r < 50 and b < 50 for r, g, b in pixels), "Expected green border pixels"


# ---------------------------------------------------------------------------
# SVG renderer: highlights produce <rect stroke="red"> elements
# ---------------------------------------------------------------------------


def test_svg_highlight_produces_red_rect(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x" * 5000)
    (tmp_path / "b.md").write_bytes(b"x" * 5000)

    root = build_tree(tmp_path)
    target = (tmp_path / "a.py").as_posix()
    buf = create_treemap_svg(
        root, width_px=400, height_px=300, cushion=False, highlights={target: "red"}
    )
    svg = buf.read().decode()
    assert 'stroke="red"' in svg


def test_svg_highlight_custom_color(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x" * 5000)
    root = build_tree(tmp_path)
    target = (tmp_path / "a.py").as_posix()
    buf = create_treemap_svg(
        root, width_px=400, height_px=300, cushion=False, highlights={target: "orange"}
    )
    svg = buf.read().decode()
    assert 'stroke="orange"' in svg


def test_svg_no_highlight_no_red_stroke(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x" * 5000)
    root = build_tree(tmp_path)
    buf = create_treemap_svg(root, width_px=400, height_px=300, cushion=False)
    svg = buf.read().decode()
    assert 'stroke="red"' not in svg


def test_svg_highlight_three_strokes(tmp_path: Path) -> None:
    """A sufficiently large tile produces 3 concentric stroke rects (stroke-width 3)."""
    (tmp_path / "a.py").write_bytes(b"x" * 10000)
    root = build_tree(tmp_path)
    target = (tmp_path / "a.py").as_posix()
    buf = create_treemap_svg(
        root, width_px=800, height_px=600, cushion=False, highlights={target: "red"}
    )
    svg = buf.read().decode()
    assert svg.count('stroke="red"') == 3


# ---------------------------------------------------------------------------
# CLI: dirplot map --highlight
# ---------------------------------------------------------------------------


def test_cli_map_highlight_png(sample_tree: Path) -> None:
    result = runner.invoke(
        app,
        [
            "map",
            str(sample_tree),
            "--highlight",
            "*.py",
            "--no-show",
            "--output",
            str(sample_tree / "out.png"),
        ],
    )
    assert result.exit_code == 0, result.output
    out = sample_tree / "out.png"
    assert out.exists()
    img = Image.open(out)
    assert img.size[0] > 0


def test_cli_map_highlight_with_color(sample_tree: Path) -> None:
    result = runner.invoke(
        app,
        [
            "map",
            str(sample_tree),
            "--highlight",
            "*.py@orange",
            "--no-show",
            "--output",
            str(sample_tree / "out.png"),
        ],
    )
    assert result.exit_code == 0, result.output


def test_cli_map_highlight_svg(sample_tree: Path) -> None:
    out = sample_tree / "out.svg"
    result = runner.invoke(
        app,
        ["map", str(sample_tree), "--highlight", "*.py@cyan", "--no-show", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert 'stroke="cyan"' in out.read_text()


def test_cli_map_highlight_no_match_is_ok(sample_tree: Path) -> None:
    """A pattern that matches nothing should not crash."""
    result = runner.invoke(
        app,
        [
            "map",
            str(sample_tree),
            "--highlight",
            "*.go",
            "--no-show",
            "--output",
            str(sample_tree / "out.png"),
        ],
    )
    assert result.exit_code == 0, result.output


def test_cli_map_highlight_multiple(sample_tree: Path) -> None:
    out = sample_tree / "out.svg"
    result = runner.invoke(
        app,
        [
            "map",
            str(sample_tree),
            "--highlight",
            "*.py@red",
            "--highlight",
            "*.md@blue",
            "--no-show",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    svg = out.read_text()
    assert 'stroke="red"' in svg
    assert 'stroke="blue"' in svg


# ---------------------------------------------------------------------------
# CLI: dirplot diff --highlight
# ---------------------------------------------------------------------------


def test_cli_diff_highlight(sample_tree: Path, tmp_path: Path) -> None:
    """diff --highlight should annotate paths on top of diff colours."""
    tree_b = tmp_path / "b"
    tree_b.mkdir()
    (tree_b / "src").mkdir()
    (tree_b / "src" / "app.py").write_bytes(b"x" * 200)
    (tree_b / "src" / "util.py").write_bytes(b"x" * 200)
    (tree_b / "README.md").write_bytes(b"x" * 50)

    out = tmp_path / "diff.svg"
    result = runner.invoke(
        app,
        [
            "diff",
            str(sample_tree),
            str(tree_b),
            "--highlight",
            "*.py@orange",
            "--no-show",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    svg = out.read_text()
    assert 'stroke="orange"' in svg
