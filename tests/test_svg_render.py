"""Tests for SVG treemap rendering."""

import io
from pathlib import Path

import pytest

from dirplot.scanner import build_tree
from dirplot.svg_render import (
    _hex,
    _label_color,
    _make_cushion_gradient,
    _truncate,
    _wrap,
    create_treemap_svg,
)

# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


def test_hex_white() -> None:
    assert _hex((1.0, 1.0, 1.0, 1.0)) == "#ffffff"


def test_hex_black() -> None:
    assert _hex((0.0, 0.0, 0.0, 1.0)) == "#000000"


def test_hex_color() -> None:
    assert _hex((1.0, 0.0, 0.0, 1.0)) == "#ff0000"


def test_label_color_light_background() -> None:
    assert _label_color((1.0, 1.0, 1.0, 1.0)) == "#000000"
    assert _label_color((0.8, 0.8, 0.8, 1.0)) == "#000000"


def test_label_color_dark_background() -> None:
    assert _label_color((0.0, 0.0, 0.0, 1.0)) == "#ffffff"
    assert _label_color((0.2, 0.2, 0.2, 1.0)) == "#ffffff"


def test_wrap_short_name() -> None:
    """A name that fits in one line is returned as a single-element list."""
    result = _wrap("short.py", font_size=12, max_w=200)
    assert result == ["short.py"]


def test_wrap_long_name() -> None:
    """A name that doesn't fit is split into multiple lines."""
    result = _wrap("very_long_filename_that_needs_wrapping.py", font_size=12, max_w=80)
    assert len(result) > 1
    # All characters appear in the output
    assert "".join(result) == "very_long_filename_that_needs_wrapping.py"


def test_wrap_splits_at_delimiter() -> None:
    """Wrap should prefer splitting at delimiter characters."""
    result = _wrap("some.long.name", font_size=12, max_w=50)
    # Should split somewhere at a dot
    joined = "".join(result)
    assert joined == "some.long.name"


def test_truncate_short() -> None:
    assert _truncate("hi.py", font_size=12, max_w=200) == "hi.py"


def test_truncate_long() -> None:
    result = _truncate("very_long_filename.py", font_size=12, max_w=50)
    assert result.endswith("\u2026")
    assert len(result) < len("very_long_filename.py")


# ---------------------------------------------------------------------------
# Integration tests for create_treemap_svg
# ---------------------------------------------------------------------------


def test_create_treemap_svg_returns_bytesio(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    assert isinstance(buf, io.BytesIO)


def test_create_treemap_svg_valid_xml(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    assert content.startswith("<?xml")
    assert "<svg" in content
    assert "</svg>" in content


def test_create_treemap_svg_dimensions(sample_tree: Path) -> None:
    """The SVG viewBox and width/height must match the requested dimensions."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert 'width="400"' in content
    assert 'height="300"' in content


def test_create_treemap_svg_background(sample_tree: Path) -> None:
    """The SVG should contain the dark background color."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    assert "#1a1a2e" in content


def test_create_treemap_svg_empty_dir(tmp_path: Path) -> None:
    """An empty directory should produce valid SVG without raising."""
    root = build_tree(tmp_path)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    assert "<svg" in content


def test_create_treemap_svg_custom_colormap(sample_tree: Path) -> None:
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240, colormap="viridis")
    content = buf.read().decode("utf-8")
    assert "<svg" in content


def test_create_treemap_svg_legend(sample_tree: Path) -> None:
    """legend=True should produce SVG that includes extension labels."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=400, height_px=300, legend=True)
    content = buf.read().decode("utf-8")
    assert "<svg" in content
    # Legend should contain some extension text
    assert ".md" in content or ".py" in content


def test_create_treemap_svg_contains_rects(sample_tree: Path) -> None:
    """Each file should be represented as a <rect> element."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert content.count("<rect") >= 3  # at least the bg + a few tiles


def test_create_treemap_svg_seeked_to_zero(sample_tree: Path) -> None:
    """The returned buffer must be seeked to position 0."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    assert buf.tell() == 0


def test_create_treemap_svg_file_extension_colors(tmp_path: Path) -> None:
    """Known extensions should use Linguist palette colors in the SVG."""
    (tmp_path / "a.js").write_bytes(b"x" * 1000)
    (tmp_path / "b.py").write_bytes(b"x" * 1000)

    root = build_tree(tmp_path)
    buf = create_treemap_svg(root, width_px=400, height_px=200)
    content = buf.read().decode("utf-8")

    # JavaScript is #f1e05a in Linguist palette; Python is #3572A5
    assert "#f1e05a" in content.lower() or "f1e05a" in content.lower()
    assert "#3572a5" in content.lower() or "3572a5" in content.lower()


def test_create_treemap_svg_save_to_file(sample_tree: Path, tmp_path: Path) -> None:
    """The SVG buffer can be written to a file and read back."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    out = tmp_path / "treemap.svg"
    out.write_bytes(buf.read())
    content = out.read_text()
    assert "<svg" in content


# ---------------------------------------------------------------------------
# Interactive effects tests
# ---------------------------------------------------------------------------


def test_no_native_title_tooltips(tmp_path: Path) -> None:
    """Native <title> elements must not be present (replaced by JS tooltip)."""
    (tmp_path / "app.py").write_bytes(b"x" * 500)
    root = build_tree(tmp_path)
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert "<title>" not in content


def test_tooltip_background_is_semitransparent(sample_tree: Path) -> None:
    """The tooltip background rect must use fill-opacity < 1 so the treemap shows through."""
    import re

    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    bg_pos = content.find('id="_dp_tip_bg"')
    assert bg_pos != -1, "_dp_tip_bg not found"
    tag_start = content.rfind("<rect", 0, bg_pos)
    tag_end = content.index("/>", tag_start) + 2
    tag = content[tag_start:tag_end]
    mo = re.search(r'fill-opacity="([0-9.]+)"', tag)
    assert mo, "fill-opacity attribute missing on tooltip background"
    assert float(mo.group(1)) < 1.0


def test_css_hover_class_on_file_tiles(tmp_path: Path) -> None:
    """File tile <rect> elements must carry class='tile'."""
    (tmp_path / "main.py").write_bytes(b"x" * 800)
    root = build_tree(tmp_path)
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert 'class="tile"' in content


def test_css_hover_class_on_dir_tiles(sample_tree: Path) -> None:
    """Directory header <rect> elements must carry class='dir-tile'."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert 'class="dir-tile"' in content


def test_css_style_block_present(sample_tree: Path) -> None:
    """The SVG must contain a <style> block with .tile and .dir-tile rules."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    assert "<style>" in content
    assert ".tile" in content
    assert ".dir-tile" in content
    assert "brightness" in content  # hover filter


def test_data_attributes_on_file_tile(tmp_path: Path) -> None:
    """File tiles must carry data-name, data-size, data-ext, data-is-dir attributes."""
    (tmp_path / "readme.md").write_bytes(b"x" * 250)
    root = build_tree(tmp_path)
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert 'data-name="readme.md"' in content
    assert 'data-size="250"' in content
    assert 'data-ext=".md"' in content
    assert 'data-is-dir="0"' in content


def test_log_mode_tooltip_shows_original_size(tmp_path: Path) -> None:
    """With --log, data-size must still show the original byte count, not the log value."""
    from dirplot.scanner import apply_log_sizes

    size = 100_000
    (tmp_path / "big.py").write_bytes(b"x" * size)
    root = build_tree(tmp_path)
    apply_log_sizes(root)
    # After log transform, node.size is a small integer (~11); original_size stays 100_000
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert f'data-size="{size}"' in content, "tooltip must show original bytes, not log value"


def test_log_mode_dir_tooltip_shows_original_size(sample_tree: Path) -> None:
    """With --log, directory header data-size must show the real total, not the log sum."""
    from dirplot.scanner import apply_log_sizes

    root = build_tree(sample_tree)
    real_total = root.size  # capture before log transform
    apply_log_sizes(root)
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert f'data-size="{real_total}"' in content, "dir tooltip must show original total bytes"


def test_data_attributes_on_dir_tile(sample_tree: Path) -> None:
    """Directory header tiles must carry data-is-dir='1' and data-count."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=400, height_px=300)
    content = buf.read().decode("utf-8")
    assert 'data-is-dir="1"' in content
    assert "data-count=" in content


def test_floating_tooltip_element_present(sample_tree: Path) -> None:
    """The SVG must contain the JS tooltip group with its three text lines."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    assert 'id="_dp_tip"' in content
    assert 'id="_dp_tip_l0"' in content
    assert 'id="_dp_tip_l1"' in content
    assert 'id="_dp_tip_l2"' in content


def test_floating_tooltip_hidden_by_default(sample_tree: Path) -> None:
    """The tooltip group must start with visibility='hidden'."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    assert 'id="_dp_tip"' in content
    tip_tag_start = content.rfind("<g", 0, content.index('id="_dp_tip"'))
    tip_tag = content[tip_tag_start : content.index(">", tip_tag_start) + 1]
    assert "hidden" in tip_tag


def test_javascript_block_present(sample_tree: Path) -> None:
    """The SVG must contain an embedded <script> with the tooltip JS."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    assert "<script>" in content
    assert "humanSize" in content
    assert "_dp_tip" in content
    assert "mouseenter" in content


def test_tooltip_element_is_last_visible_group(sample_tree: Path) -> None:
    """The tooltip group must appear after all tile rects so it renders on top."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240)
    content = buf.read().decode("utf-8")
    # Find the start of the tooltip group; all tile rects should precede it
    tip_pos = content.find('id="_dp_tip"')
    # The last tile rect (carries class="tile" or class="dir-tile") must be before the tooltip
    last_tile_pos = max(content.rfind('class="tile"'), content.rfind('class="dir-tile"'))
    assert tip_pos > last_tile_pos, "Tooltip group must come after the last tile rect"


@pytest.mark.parametrize("w,h", [(200, 150), (320, 240), (101, 73)])
def test_create_treemap_svg_various_sizes(sample_tree: Path, w: int, h: int) -> None:
    """SVG rendering should succeed for various canvas sizes."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=w, height_px=h)
    content = buf.read().decode("utf-8")
    assert f'width="{w}"' in content
    assert f'height="{h}"' in content


# ---------------------------------------------------------------------------
# Cushion gradient tests
# ---------------------------------------------------------------------------


def test_cushion_gradient_structure() -> None:
    """Cushion gradient must be diagonal, objectBoundingBox, with 3 stops."""
    import drawsvg

    grad = _make_cushion_gradient()
    assert isinstance(grad, drawsvg.LinearGradient)
    d = drawsvg.Drawing(10, 10)
    d.append(grad)
    svg = d.as_svg()
    assert 'gradientUnits="objectBoundingBox"' in svg
    assert svg.count("<stop") == 3


def test_cushion_gradient_stops() -> None:
    """First stop is white highlight, last stop is black shadow."""
    import drawsvg

    grad = _make_cushion_gradient()
    d = drawsvg.Drawing(10, 10)
    d.append(grad)
    svg = d.as_svg()
    assert "stop-color" in svg
    assert 'stop-color="white"' in svg
    assert 'stop-color="black"' in svg


def test_cushion_on_produces_linearGradient(sample_tree: Path) -> None:
    """With cushion=True (default) the SVG must contain a linearGradient."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240, cushion=True)
    content = buf.read().decode("utf-8")
    assert "linearGradient" in content


def test_cushion_off_omits_linearGradient(sample_tree: Path) -> None:
    """With cushion=False the SVG must not contain a linearGradient."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=320, height_px=240, cushion=False)
    content = buf.read().decode("utf-8")
    assert "linearGradient" not in content


def test_cushion_gradient_is_defined_once(sample_tree: Path) -> None:
    """The cushion gradient must be defined exactly once in <defs> regardless of tile count."""
    root = build_tree(sample_tree)
    buf = create_treemap_svg(root, width_px=400, height_px=300, cushion=True)
    content = buf.read().decode("utf-8")
    assert content.count("linearGradient") == 2  # one open tag, one close tag


def test_cushion_no_cushion_same_structure(sample_tree: Path) -> None:
    """Cushion on/off should produce the same number of <rect> elements (gradient is extra)."""
    root = build_tree(sample_tree)
    buf_on = create_treemap_svg(root, width_px=320, height_px=240, cushion=True)
    buf_off = create_treemap_svg(root, width_px=320, height_px=240, cushion=False)
    # With cushion, each file tile gets an extra overlay rect → more rects overall
    count_on = buf_on.read().decode().count("<rect")
    count_off = buf_off.read().decode().count("<rect")
    assert count_on > count_off


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

EXPECTED_METADATA_KEYS = {"Date", "Software", "URL", "Python", "OS", "Command"}


def test_svg_has_metadata_element(sample_tree: Path) -> None:
    """SVG output contains a <metadata> block."""
    root = build_tree(sample_tree)
    svg = create_treemap_svg(root, width_px=400, height_px=300).read().decode()
    assert "<metadata>" in svg
    assert "</metadata>" in svg


def test_svg_metadata_has_all_keys(sample_tree: Path) -> None:
    """SVG metadata block contains all expected dirplot: fields."""
    root = build_tree(sample_tree)
    svg = create_treemap_svg(root, width_px=400, height_px=300).read().decode()
    for key in EXPECTED_METADATA_KEYS:
        assert f"<dirplot:{key}>" in svg, f"SVG missing metadata field {key!r}"


def test_svg_metadata_software_value(sample_tree: Path) -> None:
    """SVG Software metadata starts with 'dirplot'."""
    import re

    root = build_tree(sample_tree)
    svg = create_treemap_svg(root, width_px=400, height_px=300).read().decode()
    match = re.search(r"<dirplot:Software>([^<]+)</dirplot:Software>", svg)
    assert match and match.group(1).startswith("dirplot ")


def test_svg_metadata_url(sample_tree: Path) -> None:
    """SVG URL metadata points to the dirplot GitHub repo."""
    root = build_tree(sample_tree)
    svg = create_treemap_svg(root, width_px=400, height_px=300).read().decode()
    assert "<dirplot:URL>https://github.com/deeplook/dirplot</dirplot:URL>" in svg


def test_svg_metadata_well_formed(sample_tree: Path) -> None:
    """SVG output with metadata is well-formed XML."""
    import xml.etree.ElementTree as ET

    root = build_tree(sample_tree)
    svg = create_treemap_svg(root, width_px=400, height_px=300).read().decode()
    ET.fromstring(svg)  # raises if not well-formed
