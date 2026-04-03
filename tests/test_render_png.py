"""Tests for treemap rendering."""

import io
import shutil
from pathlib import Path

import pytest
import squarify
from PIL import Image

from dirplot.colors import assign_colors
from dirplot.render_png import _label_color, build_metadata, create_treemap, write_mp4
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


def test_treemap_tile_colors(tmp_path: Path) -> None:
    """With cushion disabled, each file tile's pixels must match the expected fill color.

    Two files with distinct Linguist-mapped extensions and equal sizes are placed in a
    flat directory. squarify is used to replicate draw_node's interior geometry so we
    know where each tile lands. Pixels are sampled from the corner regions of each tile
    (away from the center where a label may be rendered).
    """
    # Files sorted by name → a.js first, b.py second in the squarify layout
    (tmp_path / "a.js").write_bytes(b"x" * 1000)
    (tmp_path / "b.py").write_bytes(b"x" * 1000)

    width, height, font_size = 400, 200, 12
    root = build_tree(tmp_path)
    buf = create_treemap(
        root, width_px=width, height_px=height, font_size=font_size, colormap="tab20", cushion=False
    )
    img = Image.open(buf)

    # Expected fill colors (same call as create_treemap → assign_colors)
    color_map = assign_colors([".js", ".py"], "tab20")

    def to_rgb(ext: str) -> tuple[int, int, int]:
        r, g, b, _ = color_map[ext]
        return int(r * 255), int(g * 255), int(b * 255)

    # Replicate draw_node's interior geometry for the root directory.
    # header_h = font.size + 4; for a FreeType font font.size == the requested size.
    header_h = font_size + 4
    ix, iy = 2, 2 + header_h
    iw = width - 3
    ih = height - 3 - header_h

    sizes = [1000, 1000]  # a.js, b.py (sorted)
    normed = squarify.normalize_sizes(sizes, iw, ih)
    rects = squarify.squarify(normed, ix, iy, iw, ih)

    for rect, ext in zip(rects, [".js", ".py"], strict=False):
        rx = round(rect["x"])
        ry = round(rect["y"])
        rw = round(rect["x"] + rect["dx"]) - rx - 1  # draw_node passes rw-1 to child
        rh = round(rect["y"] + rect["dy"]) - ry - 1
        expected = to_rgb(ext)

        # Sample from two corner regions (top-left and bottom-right quadrants)
        # to avoid the center where label text may overlay the fill color.
        margin = max(3, rw // 8)
        sample_points = [
            (rx + margin, ry + margin),
            (rx + rw - 1 - margin, ry + rh - 1 - margin),
        ]
        for px, py in sample_points:
            actual = img.getpixel((px, py))[:3]
            assert actual == expected, (
                f"Tile for {ext} at ({px},{py}): expected RGB{expected}, got RGB{actual}"
            )


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


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

EXPECTED_METADATA_KEYS = {"Date", "Software", "URL", "Python", "OS", "Command"}


def test_build_metadata_keys() -> None:
    """build_metadata returns all expected keys."""
    meta = build_metadata()
    assert set(meta.keys()) == EXPECTED_METADATA_KEYS


def test_build_metadata_values_nonempty() -> None:
    """build_metadata values are all non-empty strings."""
    for key, value in build_metadata().items():
        assert isinstance(value, str) and value, f"metadata[{key!r}] is empty"


def test_build_metadata_software_contains_version() -> None:
    """Software field contains 'dirplot' and a version string."""
    software = build_metadata()["Software"]
    assert software.startswith("dirplot ")
    version_part = software.split(" ", 1)[1]
    assert all(c.isdigit() or c == "." for c in version_part)


def test_build_metadata_url() -> None:
    meta = build_metadata()
    assert meta["URL"] == "https://github.com/deeplook/dirplot"


def test_png_metadata_embedded() -> None:
    """PNG output contains all expected metadata keys as iTXt chunks."""
    example = Path(__file__).parent / "example"
    root = build_tree(example)
    buf = create_treemap(root, width_px=400, height_px=300)
    info = Image.open(buf).info
    for key in EXPECTED_METADATA_KEYS:
        assert key in info, f"PNG missing metadata key {key!r}"


def test_png_metadata_software_value() -> None:
    """PNG Software metadata starts with 'dirplot'."""
    example = Path(__file__).parent / "example"
    root = build_tree(example)
    buf = create_treemap(root, width_px=400, height_px=300)
    info = Image.open(buf).info
    assert info["Software"].startswith("dirplot ")


# ── write_mp4 ────────────────────────────────────────────────────────────────


def _make_png_frame(color: tuple[int, int, int], width: int = 64, height: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not found")
def test_write_mp4_produces_file(tmp_path: Path) -> None:
    """write_mp4 creates a non-empty .mp4 file from PNG frames."""
    frames = [_make_png_frame((255, 0, 0)), _make_png_frame((0, 255, 0))]
    durations = [500, 500]
    out = tmp_path / "out.mp4"
    write_mp4(out, frames, durations)
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not found")
def test_write_mp4_respects_crf(tmp_path: Path) -> None:
    """Lower CRF produces a larger (higher-quality) file."""
    frames = [_make_png_frame((r, 100, 100)) for r in range(0, 256, 32)]
    durations = [200] * len(frames)
    out_hq = tmp_path / "hq.mp4"
    out_lq = tmp_path / "lq.mp4"
    write_mp4(out_hq, frames, durations, crf=0)
    write_mp4(out_lq, frames, durations, crf=51)
    assert out_hq.stat().st_size > out_lq.stat().st_size


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not found")
def test_write_mp4_libx265(tmp_path: Path) -> None:
    """write_mp4 works with libx265 codec."""
    frames = [_make_png_frame((0, 0, 255)), _make_png_frame((255, 255, 0))]
    out = tmp_path / "out.mp4"
    write_mp4(out, frames, [300, 300], codec="libx265", crf=28)
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not found")
def test_write_mp4_odd_dimensions(tmp_path: Path) -> None:
    """write_mp4 handles odd pixel dimensions (pads to even via ffmpeg -vf scale)."""
    frames = [_make_png_frame((128, 128, 128), width=65, height=63)]
    out = tmp_path / "out.mp4"
    write_mp4(out, frames, [500])
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg/ffprobe not found",
)
def test_write_mp4_metadata_embedded(tmp_path: Path) -> None:
    """Metadata passed to write_mp4 is readable via ffprobe."""
    import json
    import subprocess

    meta = {"Software": "dirplot test", "URL": "https://example.com", "Command": "dirplot test"}
    out = tmp_path / "out.mp4"
    write_mp4(out, [_make_png_frame((0, 128, 0))], [500], metadata=meta)

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(out)],
        capture_output=True,
        check=True,
    )
    tags = json.loads(result.stdout).get("format", {}).get("tags", {})
    for key, value in meta.items():
        assert tags.get(key) == value, f"MP4 missing or wrong metadata for {key!r}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not found")
def test_write_mp4_no_metadata_omits_movflags(tmp_path: Path) -> None:
    """write_mp4 without metadata produces a valid file and doesn't break."""
    out = tmp_path / "out.mp4"
    write_mp4(out, [_make_png_frame((255, 0, 0))], [500], metadata=None)
    assert out.exists()
    assert out.stat().st_size > 0
