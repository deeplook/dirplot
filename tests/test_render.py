"""Tests for treemap rendering."""

import io
from pathlib import Path

from PIL import Image

from dirplot.render import _label_color, create_treemap
from dirplot.scanner import build_tree


def test_label_color_light_background() -> None:
    """Light colors (high luminance) should get black text."""
    assert _label_color((255, 255, 255)) == (0, 0, 0)  # white bg → black text
    assert _label_color((200, 200, 200)) == (0, 0, 0)  # light gray → black text


def test_label_color_dark_background() -> None:
    """Dark colors (low luminance) should get white text."""
    assert _label_color((0, 0, 0)) == (255, 255, 255)  # black bg → white text
    assert _label_color((50, 50, 50)) == (255, 255, 255)  # dark gray → white text


def test_label_color_boundary() -> None:
    """Colors near the 128 luminance boundary switch sides correctly."""
    assert _label_color((200, 200, 200)) == (0, 0, 0)  # clearly light → black
    assert _label_color((100, 100, 100)) == (255, 255, 255)  # clearly dark → white


def test_create_treemap_returns_png(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    buf = create_treemap(root, width_px=320, height_px=240)
    assert isinstance(buf, io.BytesIO)
    header = buf.read(8)
    assert header == b"\x89PNG\r\n\x1a\n", "Buffer should start with PNG magic bytes"


def test_create_treemap_custom_colormap(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    buf = create_treemap(root, width_px=320, height_px=240, colormap="viridis")
    buf.seek(0)
    assert buf.read(8) == b"\x89PNG\r\n\x1a\n"


def test_create_treemap_scale(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    buf = create_treemap(root, width_px=320, height_px=240, font_size=18)
    buf.seek(0)
    assert buf.read(8) == b"\x89PNG\r\n\x1a\n"


def test_create_treemap_empty_dir(tmp_path: Path) -> None:
    """An empty directory should not raise."""
    root = build_tree(tmp_path)
    buf = create_treemap(root, width_px=320, height_px=240)
    buf.seek(0)
    assert buf.read(8) == b"\x89PNG\r\n\x1a\n"


def test_treemap_exact_dimensions(sample_tree: Path) -> None:
    """Saved PNG must be exactly width_px × height_px — no right/bottom margin trimming."""
    root = build_tree(sample_tree)
    for w, h in [(200, 150), (320, 240), (101, 73)]:
        buf = create_treemap(root, width_px=w, height_px=h)
        img = Image.open(buf)
        assert img.size == (w, h), f"Expected {w}×{h}, got {img.size}"


def test_treemap_legend(sample_tree: Path) -> None:
    """legend=True should produce a valid PNG of the correct size."""
    root = build_tree(sample_tree)
    buf = create_treemap(root, width_px=320, height_px=240, legend=True)
    img = Image.open(buf)
    assert img.size == (320, 240)


def test_treemap_visual() -> None:
    """Render tests/example/ and save the result for manual inspection.

    Output: tests/visual_sample.png
    """
    example = Path(__file__).parent / "example"
    root = build_tree(example)
    buf = create_treemap(root, width_px=800, height_px=500, legend=True)

    out = Path(__file__).parent / "example_dirplot.png"
    out.write_bytes(buf.read())

    assert out.exists()
    img = Image.open(out)
    assert img.size == (800, 500)
