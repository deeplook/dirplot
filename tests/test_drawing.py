"""Tests for PIL-based draw_node and display functions."""

import io
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from dirplot.colors import assign_colors
from dirplot.display import display_inline, display_window
from dirplot.render_png import draw_node
from dirplot.scanner import Node
from tests.test_display import _no_tty


def _make_draw(w: int = 100, h: int = 100) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (w, h), color=(26, 26, 46))
    return img, ImageDraw.Draw(img)


def _font() -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=9)


def _px(img: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    arr = np.array(img)
    return tuple(arr[y, x, :3].tolist())  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# draw_node — file tiles
# ---------------------------------------------------------------------------


def test_draw_node_skips_tiny_rect() -> None:
    img, draw = _make_draw()
    bg = _px(img, 5, 5)
    node = Node(name="f.py", path=Path("f.py"), size=10, is_dir=False, extension=".py")
    draw_node(draw, node, 0, 0, 0, 0, {}, _font())
    # Nothing drawn — interior should still be background
    assert _px(img, 5, 5) == bg


def test_draw_node_file_border_is_dark_not_white() -> None:
    img, draw = _make_draw(50, 50)
    node = Node(name="f.py", path=Path("f.py"), size=10, is_dir=False, extension=".py")
    color_map = assign_colors([".py"])
    draw_node(draw, node, 0, 0, 50, 50, color_map, _font())
    rgba = color_map[".py"]
    fill = (int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))
    dark = (max(0, fill[0] - 60), max(0, fill[1] - 60), max(0, fill[2] - 60))
    # Edge pixels are the darkened outline colour, not white (no dir-style white border)
    assert _px(img, 0, 0) == dark, "top-left corner should be the dark outline, not white"
    assert _px(img, 49, 49) == dark, "bottom-right corner should be the dark outline, not white"
    # Interior pixel away from the label should be the fill colour
    assert _px(img, 2, 2) == fill, "interior (away from label) should be the fill colour"


def test_draw_node_file_interior_is_fill_color() -> None:
    img, draw = _make_draw(50, 50)
    node = Node(name="f.py", path=Path("f.py"), size=10, is_dir=False, extension=".py")
    color_map = assign_colors([".py"])
    draw_node(draw, node, 0, 0, 50, 50, color_map, _font())
    rgba = color_map[".py"]
    expected = (int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))
    assert _px(img, 5, 5) == expected, "corner should be the file colour"


# ---------------------------------------------------------------------------
# draw_node — directory tiles
# ---------------------------------------------------------------------------


def test_draw_node_dir_white_outer_border() -> None:
    img, draw = _make_draw(80, 60)
    child = Node(name="f.py", path=Path("f.py"), size=100, is_dir=False, extension=".py")
    node = Node(name="src", path=Path("src"), size=100, is_dir=True, children=[child])
    color_map = assign_colors([".py"])
    draw_node(draw, node, 0, 0, 80, 60, color_map, _font())
    # Outer edge pixels must be white
    assert _px(img, 0, 0) == (255, 255, 255), "top-left should be white"
    assert _px(img, 79, 0) == (255, 255, 255), "top-right should be white"
    assert _px(img, 0, 59) == (255, 255, 255), "bottom-left should be white"
    assert _px(img, 79, 59) == (255, 255, 255), "bottom-right should be white"


def test_draw_node_dir_black_inner_border() -> None:
    img, draw = _make_draw(80, 60)
    child = Node(name="f.py", path=Path("f.py"), size=100, is_dir=False, extension=".py")
    node = Node(name="src", path=Path("src"), size=100, is_dir=True, children=[child])
    color_map = assign_colors([".py"])
    draw_node(draw, node, 0, 0, 80, 60, color_map, _font())
    # Pixel just inside the white border must be black (inner border)
    assert _px(img, 1, 1) == (0, 0, 0), "pixel (1,1) should be black inner border"
    assert _px(img, 78, 1) == (0, 0, 0)
    assert _px(img, 1, 58) == (0, 0, 0)
    assert _px(img, 78, 58) == (0, 0, 0)


def test_draw_node_dir_too_small_for_inner_border() -> None:
    """A 3×3 dir is large enough for the outer border but too small for the inner one."""
    img, draw = _make_draw(10, 10)
    node = Node(name="src", path=Path("src"), size=100, is_dir=True)
    draw_node(draw, node, 0, 0, 3, 3, {}, _font())  # should not raise


def test_draw_node_dir_inner_area_too_small() -> None:
    """Very narrow dir: inner content collapses — no error raised."""
    img, draw = _make_draw(10, 100)
    child = Node(name="f.py", path=Path("f.py"), size=100, is_dir=False, extension=".py")
    node = Node(name="src", path=Path("src"), size=100, is_dir=True, children=[child])
    draw_node(draw, node, 0, 0, 3, 100, {}, _font())  # should not raise


# ---------------------------------------------------------------------------
# display_window
# ---------------------------------------------------------------------------


def test_display_window(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_img = MagicMock()
    monkeypatch.setattr("PIL.Image.open", lambda _buf: mock_img)
    display_window(io.BytesIO(b"\x89PNG\r\n\x1a\n"))
    mock_img.show.assert_called_once()


# ---------------------------------------------------------------------------
# display_inline
# ---------------------------------------------------------------------------


def test_display_inline(capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    buf = io.BytesIO(b"fake-png-data")
    with _no_tty():
        display_inline(buf)
    written = capsys.readouterr().out
    assert "\x1b]1337;" in written
    assert "fake-png-data" not in written  # data is base64-encoded
    assert written.endswith("\a")
