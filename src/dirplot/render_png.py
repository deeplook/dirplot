"""Treemap layout and PNG rendering."""

import io
import math
import platform
import struct
import sys
import zlib
from collections import defaultdict
from datetime import datetime, timezone
from importlib.metadata import version as _pkg_version
from pathlib import Path

import numpy as np
import squarify
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from dirplot.colors import RGBAColor, assign_colors
from dirplot.scanner import Node, collect_extensions, count_nodes, max_depth

DIRPLOT_URL = "https://github.com/deeplook/dirplot"


def build_metadata() -> dict[str, str]:
    """Return a dict of metadata fields to embed in PNG/SVG output."""
    return {
        "Date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Software": f"dirplot {_pkg_version('dirplot')}",
        "URL": DIRPLOT_URL,
        "Python": sys.version.split()[0],
        "OS": f"{platform.system()} {platform.release()}",
        "Command": " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
    }


SWATCH_PX = 8  # legend colour swatch size in pixels
LEG_PAD = 3  # legend internal padding in pixels

_FONTS_DIR = Path(__file__).parent / "fonts"
_FONT_REGULAR = _FONTS_DIR / "JetBrainsMono-Regular.ttf"
_FONT_BOLD = _FONTS_DIR / "JetBrainsMono-Bold.ttf"
_FONT_ITALIC = _FONTS_DIR / "JetBrainsMono-Italic.ttf"
_FONT_BOLD_ITALIC = _FONTS_DIR / "JetBrainsMono-BoldItalic.ttf"


def _font(size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    size = max(6, size)
    if bold and italic:
        path = _FONT_BOLD_ITALIC
    elif bold:
        path = _FONT_BOLD
    elif italic:
        path = _FONT_ITALIC
    else:
        path = _FONT_REGULAR
    return ImageFont.truetype(str(path), size=size)


def _human_bytes(n: int) -> str:
    """Return a human-readable byte count: '4.0 MB', '1.2 GB', etc."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"  # unreachable but satisfies type checkers


def _label_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Return black or white text color based on the background luminance."""
    gray = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return (0, 0, 0) if gray >= 128 else (255, 255, 255)


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return int(bb[2] - bb[0])


def _fit_font(
    name: str,
    draw: ImageDraw.ImageDraw,
    max_size: int,
    max_w: int,
    max_h: int,
) -> tuple[ImageFont.FreeTypeFont, str]:
    """Return (font, wrapped_label) at the largest size ≤ max_size where the
    wrapped text fits within max_w × max_h pixels.

    Uses one textbbox measurement at max_size to estimate n_lines after
    wrapping, then calculates the required font size directly — no loop.
    """
    if max_h < 6 or max_w < 4:
        ffont = _font(6)
        return ffont, _wrap(name, draw, ffont, max_w)
    # Step 1: estimate fsize from single-line measurement at max_size
    ffont = _font(max_size)
    bb = draw.textbbox((0, 0), name, font=ffont)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    n_lines = max(1, math.ceil(tw / max_w))
    fsize = max(6, min(max_size, int(max_h / n_lines * max_size / max(th, 1))))
    # Steps 2-3: wrap and measure actual height; correct up to twice if still overflowing
    for _ in range(2):
        ffont = _font(fsize)
        label = _wrap(name, draw, ffont, max_w)
        bb = draw.textbbox((0, 0), label, font=ffont, spacing=0)
        actual_h = bb[3] - bb[1]
        if actual_h <= max_h or actual_h == 0:
            return ffont, label
        fsize = max(6, int(fsize * max_h / actual_h))
    # Text can't fit even at minimum size — skip the label to avoid overflow
    return _font(fsize), ""


def _wrap(name: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    """Wrap *name* into lines that each fit within *max_w* pixels."""
    if max_w < 4:
        return ""
    if _text_w(draw, name, font) <= max_w:
        return name
    delimiters = "._ -"
    lines: list[str] = []
    remaining = name
    while remaining:
        if _text_w(draw, remaining, font) <= max_w:
            lines.append(remaining)
            break
        # Binary-search the longest prefix that fits
        lo, hi = 1, len(remaining)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _text_w(draw, remaining[:mid], font) <= max_w:
                lo = mid
            else:
                hi = mid - 1
        chunk = remaining[:lo]
        split = max((chunk.rfind(d) for d in delimiters), default=-1)
        if split > 0:
            lines.append(remaining[:split])
            remaining = remaining[split:]
        else:
            lines.append(chunk)
            remaining = remaining[lo:]
    return "\n".join(lines)


def _truncate(
    name: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_w: int
) -> str:
    """Truncate *name* with an ellipsis so it fits within *max_w* pixels on one line."""
    if max_w < 4:
        return ""
    if _text_w(draw, name, font) <= max_w:
        return name
    ellipsis = "…"
    lo, hi = 0, len(name)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _text_w(draw, name[:mid] + ellipsis, font) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return name[:lo] + ellipsis


def _truncate_breadcrumb(
    name: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_w: int
) -> str:
    """Truncate a breadcrumb label (`` / ``-separated parts) to fit *max_w* pixels.

    Tries the full label first, then collapses middle segments to ``…``, and
    finally falls back to ``_truncate`` for plain names or when even the
    ``first / … / last`` form is too long.
    """
    parts = name.split(" / ")
    if len(parts) <= 1:
        return _truncate(name, draw, font, max_w)
    if _text_w(draw, name, font) <= max_w:
        return name
    candidate = parts[0] + " / … / " + parts[-1]
    if _text_w(draw, candidate, font) <= max_w:
        return candidate
    return _truncate(candidate, draw, font, max_w)


def _cushion_brightness(w: int, h: int, scale: float = 1.0) -> NDArray[np.float32]:
    """Return a (h, w) float32 brightness map for van Wijk cushion shading."""
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    gx, gy = np.meshgrid(xs, ys)
    Ix, Iy = 0.12 * scale / w, 0.12 * scale / h
    nx = Ix * (w - 1 - 2 * gx)
    ny = Iy * (h - 1 - 2 * gy)
    lx, ly, lz = 1.0, 1.0, 1.2
    mag = (lx**2 + ly**2 + lz**2) ** 0.5
    lx, ly, lz = lx / mag, ly / mag, lz / mag
    brightness = nx * lx + ny * ly + lz
    np.clip(brightness, 0.0, None, out=brightness)
    brightness /= float(brightness.mean())
    return brightness  # type: ignore[no-any-return]


def _apply_cushion(img: Image.Image, x: int, y: int, w: int, h: int) -> None:
    """Apply van Wijk-style quadratic cushion shading to a tile in-place (PIL path)."""
    if w < 4 or h < 4:
        return
    brightness = _cushion_brightness(w, h)
    tile = img.crop((x, y, x + w, y + h))
    arr = np.array(tile, dtype=np.float32)
    arr[:, :, :3] *= brightness[:, :, np.newaxis]
    np.clip(arr, 0, 255, out=arr)
    img.paste(Image.fromarray(arr.astype(np.uint8)), (x, y))


def _apply_cushion_inplace(
    arr: np.ndarray, x: int, y: int, w: int, h: int, scale: float = 1.0
) -> None:
    """Apply van Wijk cushion shading directly to a region of a numpy (H, W, 3) array.

    Avoids the PIL crop/paste round-trip of :func:`_apply_cushion`.  Call this
    after converting the full image to numpy once, then converting back once —
    much cheaper than one PIL round-trip per tile when there are many tiles.
    """
    if w < 4 or h < 4:
        return
    brightness = _cushion_brightness(w, h, scale)
    region = arr[y : y + h, x : x + w].astype(np.float32)
    region *= brightness[:, :, np.newaxis]
    np.clip(region, 0, 255, out=region)
    arr[y : y + h, x : x + w] = region.astype(np.uint8)


def draw_node(
    draw: ImageDraw.ImageDraw,
    node: Node,
    x: int,
    y: int,
    w: int,
    h: int,
    color_map: dict[str, RGBAColor],
    font: ImageFont.FreeTypeFont,
    font_size: int = 12,
    cushion: bool = True,
    img: Image.Image | None = None,
    root_label: str | None = None,
    rect_map: dict[str, tuple[int, int, int, int]] | None = None,
    dir_rect_map: dict[str, tuple[int, int, int, int]] | None = None,
    dark: bool = True,
) -> None:
    """Recursively draw *node* and its children into *draw*.

    Args:
        draw: PIL ImageDraw to draw into.
        node: Current tree node.
        x, y: Top-left corner in pixels.
        w, h: Width and height in pixels.
        color_map: Extension → RGBA colour mapping.
        font: Font for directory name labels.
        root_label: When set, overrides the directory header label for this
            (root) node only; children always use their own name.
        rect_map: When provided, populated with ``str(path) → (x, y, w, h)``
            for every leaf node drawn.
    """
    if w < 2 or h < 2:
        return

    if not node.is_dir:
        if rect_map is not None:
            rect_map[node.path.as_posix()] = (x, y, w, h)
        rgba = color_map.get(node.extension, (0.5, 0.5, 0.5, 1.0))
        rgb = (int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=rgb)
        if cushion and img is not None:
            _apply_cushion(img, x, y, w, h)
        # 1-px border so adjacent same-colored tiles always have a visible boundary
        if w >= 3 and h >= 3:
            border = (max(0, rgb[0] - 60), max(0, rgb[1] - 60), max(0, rgb[2] - 60))
            draw.rectangle([x, y, x + w - 1, y + h - 1], outline=border)
        # Adaptive label: largest font that fits the tile without overflow
        if w > 20 and h > 10:
            # Try horizontal first
            ffont_h, label_h = _fit_font(node.name, draw, font_size + 2, w - 4, h - 4)
            # For tall narrow tiles, also try vertical; prefer whichever wraps less
            use_vertical = False
            if h >= w * 2 and img is not None:
                ffont_v, label_v = _fit_font(node.name, draw, font_size + 2, h - 4, w - 4)
                if label_v:
                    h_lines = label_h.count("\n") + 1 if label_h else 999
                    v_lines = label_v.count("\n") + 1
                    if v_lines < h_lines or (v_lines == h_lines and ffont_v.size > ffont_h.size):
                        use_vertical = True
            if use_vertical:
                # Tall, narrow tile — rotate label 90° CCW so it runs along the height
                tmp = Image.new("RGBA", (h, w), (0, 0, 0, 0))
                ImageDraw.Draw(tmp).text(
                    (h // 2, w // 2),
                    label_v,
                    fill=_label_color(rgb),
                    font=ffont_v,
                    anchor="mm",
                    align="center",
                    spacing=0,
                )
                rotated = tmp.rotate(90, expand=True)
                assert img is not None
                img.paste(rotated, (x, y), mask=rotated)
            else:
                # Horizontal label: available text-run = w-4, constraining dim = h-4
                draw.text(
                    (x + w // 2, y + h // 2),
                    label_h,
                    fill=_label_color(rgb),
                    font=ffont_h,
                    anchor="mm",
                    align="center",
                    spacing=0,
                )
        return

    if dir_rect_map is not None:
        dir_rect_map[str(node.path)] = (x, y, w, h)

    # Directory: 1-px outer border + 1-px inner border (colours swap in light mode)
    outer_col = (255, 255, 255) if dark else (0, 0, 0)
    inner_col = (0, 0, 0) if dark else (255, 255, 255)
    draw.rectangle([x, y, x + w - 1, y + h - 1], outline=outer_col, width=1)
    if w >= 4 and h >= 4:
        draw.rectangle([x + 1, y + 1, x + w - 2, y + h - 2], outline=inner_col, width=1)

    # Header label — height driven by the font size
    header_h = font.size + 4
    if h > 2 + header_h:
        label = _truncate_breadcrumb(
            root_label if root_label is not None else node.name, draw, font, w - 8
        )
        header_text_col = (224, 224, 224) if dark else (32, 32, 32)
        draw.text(
            (x + w // 2, y + 2 + header_h // 2),
            label,
            fill=header_text_col,
            font=font,
            anchor="mm",
            align="center",
        )

    # Inner content area: starts just inside the 2-px border, ends ON the
    # right/bottom inner-border pixel so the pre-fill and the inner border
    # share that pixel rather than stacking two black pixels there.
    ix = x + 2
    iy = y + 2 + header_h
    iw = w - 3
    ih = h - 3 - header_h

    if iw < 2 or ih < 2:
        return

    positive_children = [c for c in node.children if c.size > 0]
    if not positive_children:
        return

    sizes = [c.size for c in positive_children]
    normed = squarify.normalize_sizes(sizes, iw, ih)
    rects = squarify.squarify(normed, ix, iy, iw, ih)

    # Background provides the 1-px separator between adjacent children
    sep_col = (0, 0, 0) if dark else (255, 255, 255)
    draw.rectangle([ix, iy, ix + iw - 1, iy + ih - 1], fill=sep_col)

    for rect, child in zip(rects, positive_children, strict=False):
        rx = round(rect["x"])
        ry = round(rect["y"])
        rw = round(rect["x"] + rect["dx"]) - rx
        rh = round(rect["y"] + rect["dy"]) - ry
        draw_node(
            draw,
            child,
            rx,
            ry,
            rw - 1,
            rh - 1,
            color_map,
            font,
            font_size,
            cushion,
            img,
            rect_map=rect_map,
            dir_rect_map=dir_rect_map,
            dark=dark,
        )


def _collect_ext_counts(node: Node) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)

    def _walk(n: Node) -> None:
        if not n.is_dir:
            counts[n.extension] += 1
        for c in n.children:
            _walk(c)

    _walk(node)
    return dict(counts)


def _best_corner(root_node: Node, width_px: int, height_px: int) -> str:
    """Return the corner string for the largest top-level tile."""
    positive = [c for c in root_node.children if c.size > 0]
    if not positive:
        return "lower-right"
    pad, header_h = 2, 16
    iw = width_px - 2 * pad
    ih = height_px - 2 * pad - header_h
    normed = squarify.normalize_sizes([c.size for c in positive], iw, ih)
    rects = squarify.squarify(normed, pad, pad, iw, ih)
    corners = {
        "upper-left": (1, 1),
        "upper-right": (width_px - 2, 1),
        "lower-left": (1, height_px - 2),
        "lower-right": (width_px - 2, height_px - 2),
    }
    best, best_area = "lower-right", -1.0
    for loc, (px, py) in corners.items():
        for r in rects:
            if r["x"] <= px <= r["x"] + r["dx"] and r["y"] <= py <= r["y"] + r["dy"]:
                area = r["dx"] * r["dy"]
                if area > best_area:
                    best_area, best = area, loc
                break
    return best


def _draw_legend(
    draw: ImageDraw.ImageDraw,
    ext_counts: dict[str, int],
    color_map: dict[str, RGBAColor],
    width_px: int,
    height_px: int,
    corner: str,
    font: ImageFont.FreeTypeFont,
    max_rows: int = 20,
    dark: bool = True,
) -> None:
    margin = 4
    bb = draw.textbbox((0, 0), "Ag", font=font)
    text_h = bb[3] - bb[1]
    row_h = max(SWATCH_PX, text_h) + LEG_PAD
    rows_that_fit = max(1, int((height_px - 2 * margin - LEG_PAD * 2 - row_h) // row_h))
    limit = min(max_rows, rows_that_fit)

    ranked = sorted(ext_counts, key=lambda e: (-ext_counts[e], e))
    top = ranked[:limit]
    n_more = len(ranked) - limit
    if not top:
        return

    more_label = f"(+{n_more})" if n_more > 0 else ""

    label_w = max(_text_w(draw, ext, font) for ext in top)
    if more_label:
        label_w = max(label_w, _text_w(draw, more_label, font))
    count_w = max(_text_w(draw, str(ext_counts[e]), font) for e in top)
    box_w = SWATCH_PX + LEG_PAD + label_w + LEG_PAD + count_w + LEG_PAD * 2
    n_rows = len(top) + (1 if more_label else 0)
    box_h = n_rows * row_h + LEG_PAD * 2

    bx = (width_px - box_w - margin) if "right" in corner else margin
    by = (height_px - box_h - margin) if "lower" in corner else margin

    leg_bg = (20, 20, 36) if dark else (240, 240, 240)
    leg_border = (80, 80, 80) if dark else (160, 160, 160)
    leg_ext_text = (220, 220, 220) if dark else (40, 40, 40)
    leg_count_text = (160, 160, 160) if dark else (80, 80, 80)
    leg_more_text = (120, 120, 120) if dark else (100, 100, 100)
    leg_swatch_outline = (255, 255, 255) if dark else (0, 0, 0)
    draw.rectangle([bx, by, bx + box_w - 1, by + box_h - 1], fill=leg_bg)
    draw.rectangle([bx, by, bx + box_w - 1, by + box_h - 1], outline=leg_border, width=1)

    for ri, ext in enumerate(top):
        rgba = color_map.get(ext, (0.5, 0.5, 0.5, 1.0))
        rgb = (int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))
        ex = bx + LEG_PAD
        row_mid = by + LEG_PAD + ri * row_h + (row_h - LEG_PAD) // 2
        sy = row_mid - SWATCH_PX // 2
        draw.rectangle(
            [ex, sy, ex + SWATCH_PX - 1, sy + SWATCH_PX - 1],
            fill=rgb,
            outline=leg_swatch_outline,
            width=1,
        )
        draw.text(
            (ex + SWATCH_PX + LEG_PAD, row_mid),
            ext,
            fill=leg_ext_text,
            font=font,
            anchor="lm",
        )
        draw.text(
            (bx + box_w - LEG_PAD, row_mid),
            str(ext_counts[ext]),
            fill=leg_count_text,
            font=font,
            anchor="rm",
        )

    if more_label:
        row_mid = by + LEG_PAD + len(top) * row_h + (row_h - LEG_PAD) // 2
        draw.text(
            (bx + LEG_PAD + SWATCH_PX + LEG_PAD, row_mid),
            more_label,
            fill=leg_more_text,
            font=font,
            anchor="lm",
        )


HIGHLIGHT_COLORS: dict[str, tuple[int, int, int]] = {
    "created": (0, 220, 0),
    "modified": (0, 128, 255),
    "deleted": (255, 0, 0),
    "moved": (255, 165, 0),
}

HIGHLIGHT_BORDER = 3  # pixels


def _draw_highlights(
    draw: ImageDraw.ImageDraw,
    rect_map: dict[str, tuple[int, int, int, int]],
    highlights: dict[str, str],
) -> None:
    """Draw coloured borders around tiles whose paths appear in *highlights*.

    *highlights* maps ``str(path) → event_type`` where event_type is one of
    ``"created"``, ``"modified"``, ``"deleted"``, or ``"moved"``.

    For deleted files (not in *rect_map*), the parent directory is
    highlighted instead.
    """
    for path, event_type in highlights.items():
        if path not in rect_map:
            continue
        x, y, w, h = rect_map[path]
        color = HIGHLIGHT_COLORS.get(event_type, (255, 255, 0))
        border = min(HIGHLIGHT_BORDER, w // 3, h // 3)
        if border < 1:
            continue
        for i in range(border):
            draw.rectangle(
                [x + i, y + i, x + w - 1 - i, y + h - 1 - i],
                outline=color,
            )


def _build_root_label(
    name: str,
    n_files: int,
    n_dirs: int,
    total_bytes: int,
    depth: int,
    logscale: float,
    title_suffix: str | None,
    draw: "ImageDraw.ImageDraw",
    font: "ImageFont.FreeTypeFont",
    max_w: int,
) -> str:
    """Return the longest root-header label that fits within *max_w* pixels.

    Fields are dropped in order of decreasing priority until the text fits:
    1. Full label with raw bytes, logscale, and title_suffix
    2. Drop raw byte count
    3. Drop logscale indicator
    4. Drop title_suffix
    5. Drop depth
    6. Drop dir count
    7. Fallback plain truncation
    """
    human = _human_bytes(total_bytes)
    ls = f"  logscale:{logscale:g}×" if logscale > 1 else ""
    sf = f"  [{title_suffix}]" if title_suffix else ""

    candidates = [
        f"{name} \u2014 {n_files:,} files, {n_dirs:,} dirs,"
        f" {human} ({total_bytes:,} bytes), depth: {depth}{ls}{sf}",
        f"{name} \u2014 {n_files:,} files, {n_dirs:,} dirs, {human}, depth: {depth}{ls}{sf}",
        f"{name} \u2014 {n_files:,} files, {n_dirs:,} dirs, {human}, depth: {depth}{sf}",
        f"{name} \u2014 {n_files:,} files, {n_dirs:,} dirs, {human}, depth: {depth}",
        f"{name} \u2014 {n_files:,} files, {n_dirs:,} dirs, {human}",
        f"{name} \u2014 {n_files:,} files, {human}",
    ]
    for candidate in candidates:
        if _text_w(draw, candidate, font) <= max_w:
            return candidate
    return _truncate(candidates[-1], draw, font, max_w)


def create_treemap(
    root_node: Node,
    width_px: int,
    height_px: int,
    font_size: int = 12,
    colormap: str = "tab20",
    legend: int | None = None,
    cushion: bool = True,
    tree_depth: int | None = None,
    highlights: dict[str, str] | None = None,
    rect_map_out: dict[str, tuple[int, int, int, int]] | None = None,
    title_suffix: str | None = None,
    progress: float | None = None,
    dark: bool = True,
    logscale: float = 0.0,
) -> io.BytesIO:
    """Render a nested squarified treemap and return it as a PNG in a BytesIO buffer.

    Args:
        root_node: Root of the directory tree.
        width_px: Output image width in pixels.
        height_px: Output image height in pixels.
        font_size: Directory label font size in pixels.
        colormap: Matplotlib colormap name for file-extension colours.
        legend: Max entries in the file-count legend, or None to disable.
        highlights: Optional mapping of ``str(path) → event_type`` for tiles
            that should receive a coloured border (created/modified/deleted).
        rect_map_out: When provided, populated with ``str(path) → (x, y, w, h)``
            for every node drawn. Useful for highlighting tiles in a later pass.

    Returns:
        BytesIO containing the rendered PNG, seeked to position 0.
    """
    exts = collect_extensions(root_node)
    color_map = assign_colors(exts, colormap)

    canvas_bg = (26, 26, 46) if dark else (255, 255, 255)
    img = Image.new("RGB", (width_px, height_px), color=canvas_bg)
    idraw = ImageDraw.Draw(img)
    font = _font(font_size, bold=True)

    n_files, n_dirs = count_nodes(root_node)
    total_bytes = root_node.original_size if root_node.original_size > 0 else root_node.size
    depth = tree_depth if tree_depth is not None else max_depth(root_node)
    root_label = _build_root_label(
        root_node.name,
        n_files,
        n_dirs,
        total_bytes,
        depth,
        logscale,
        title_suffix,
        idraw,
        font,
        width_px - 8,
    )
    # Always collect tile positions — needed for batch cushion and/or highlights.
    _tile_rects: dict[str, tuple[int, int, int, int]] = {}
    _dir_rects: dict[str, tuple[int, int, int, int]] = {}
    draw_node(
        idraw,
        root_node,
        0,
        0,
        width_px,
        height_px,
        color_map,
        font,
        font_size,
        False,  # cushion deferred: applied in one batch pass below
        img,
        root_label=root_label,
        rect_map=_tile_rects,
        dir_rect_map=_dir_rects,
        dark=dark,
    )

    # Batch cushion: directories first at half strength (broad, structural shading),
    # then leaf file tiles at full strength (per-file detail).
    if cushion and (_tile_rects or _dir_rects):
        arr = np.array(img)
        for tx, ty, tw, th in _dir_rects.values():
            _apply_cushion_inplace(arr, tx, ty, tw, th, scale=0.5)
        for tx, ty, tw, th in _tile_rects.values():
            _apply_cushion_inplace(arr, tx, ty, tw, th)
        img = Image.fromarray(arr)
        idraw = ImageDraw.Draw(img)

    if rect_map_out is not None:
        rect_map_out.update(_tile_rects)
        rect_map_out.update(_dir_rects)

    if highlights:
        _draw_highlights(idraw, {**_tile_rects, **_dir_rects}, highlights)

    if progress is not None:
        clipped = max(0.0, min(1.0, progress))
        filled = round(clipped * width_px)
        # Draw dark track across the full width first, then overlay the filled portion.
        # Without the track the bar is invisible because the root-tile border is white.
        idraw.rectangle([(0, 0), (width_px - 1, 1)], fill=(50, 50, 70))
        if filled > 0:
            idraw.rectangle([(0, 0), (filled - 1, 1)], fill=(255, 255, 255))

    if legend is not None:
        overlay_font = _font(max(6, font_size - 2))
        corner = _best_corner(root_node, width_px, height_px)
        ext_counts = _collect_ext_counts(root_node)
        _draw_legend(
            idraw, ext_counts, color_map, width_px, height_px, corner, overlay_font, legend, dark
        )

    pnginfo = PngImagePlugin.PngInfo()
    for key, value in build_metadata().items():
        pnginfo.add_itxt(key, value)

    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=pnginfo)
    buf.seek(0)
    return buf


# ── Streaming APNG writer ─────────────────────────────────────────────────────
# Works directly with PNG binary chunks so no PIL Image objects need to be held
# in memory beyond a single frame at a time.

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _apng_make_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _apng_iter_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Return (chunk_type, chunk_data) pairs from raw PNG bytes."""
    pos = 8  # skip PNG signature
    chunks = []
    while pos + 12 <= len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        chunks.append((chunk_type, chunk_data))
    return chunks


def write_apng(output: Path, frame_bytes: list[bytes], durations_ms: list[int]) -> None:
    """Write *frame_bytes* as an APNG file, processing one frame at a time.

    Avoids loading all frames as decoded PIL Images simultaneously — each frame
    is processed as compressed PNG bytes and written directly as APNG chunks.
    For a single frame, ``output`` is written as a plain PNG with no APNG chunks.
    """
    n = len(frame_bytes)
    if n == 1:
        output.write_bytes(frame_bytes[0])
        return

    seq = 0
    with open(output, "wb") as f:
        f.write(_PNG_SIG)

        # Collect IHDR and standard colour-space chunks from the first frame.
        ihdr_data = b""
        pre_idat: list[tuple[bytes, bytes]] = []
        for chunk_type, chunk_data in _apng_iter_chunks(frame_bytes[0]):
            if chunk_type == b"IHDR":
                ihdr_data = chunk_data
                pre_idat.append((chunk_type, chunk_data))
            elif chunk_type in {b"pHYs", b"sRGB", b"gAMA", b"cHRM", b"iCCP"}:
                pre_idat.append((chunk_type, chunk_data))
            elif chunk_type == b"IDAT":
                break

        for chunk_type, chunk_data in pre_idat:
            f.write(_apng_make_chunk(chunk_type, chunk_data))

        # acTL – animation control (num_frames, num_plays=0 → loop forever)
        f.write(_apng_make_chunk(b"acTL", struct.pack(">II", n, 0)))

        width, height = struct.unpack_from(">II", ihdr_data)

        for i, (frame_data, duration_ms) in enumerate(zip(frame_bytes, durations_ms, strict=False)):
            # fcTL – frame control
            fctl = struct.pack(
                ">IIIIIHHbb",
                seq,
                width,
                height,
                0,
                0,
                duration_ms,
                1000,  # delay = duration_ms / 1000 s
                0,
                0,  # dispose_op=NONE, blend_op=SOURCE
            )
            f.write(_apng_make_chunk(b"fcTL", fctl))
            seq += 1

            for chunk_type, chunk_data in _apng_iter_chunks(frame_data):
                if chunk_type == b"IDAT":
                    if i == 0:
                        f.write(_apng_make_chunk(b"IDAT", chunk_data))
                    else:
                        f.write(_apng_make_chunk(b"fdAT", struct.pack(">I", seq) + chunk_data))
                        seq += 1

        f.write(_apng_make_chunk(b"IEND", b""))


def _frames_as_rgba(frame_bytes: list[bytes]) -> list[bytes]:
    """Re-encode *frame_bytes* as RGBA PNGs (required before adding a transparent fade)."""
    result = []
    for fb in frame_bytes:
        img = Image.open(io.BytesIO(fb)).convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result.append(buf.getvalue())
    return result


def make_fade_out_frames(
    last_frame: bytes,
    n_frames: int = 4,
    duration_ms: int = 1000,
    target_color: tuple[int, int, int] | tuple[int, int, int, int] = (0, 0, 0),
) -> tuple[list[bytes], list[int]]:
    """Return *n_frames* PNG frames that fade *last_frame* toward *target_color*.

    When *target_color* is a 4-tuple whose alpha component is 0 the frames are
    RGBA PNGs that fade to fully transparent.  All other colours produce RGB
    frames.  Call :func:`_frames_as_rgba` on the existing animation frames
    before appending transparent fade frames so that every frame in the APNG
    shares the same colour type.

    Returns ``(frames, per_frame_durations_ms)`` where durations sum to
    *duration_ms*.
    """
    fade_transparent = len(target_color) == 4 and target_color[3] == 0
    src = Image.open(io.BytesIO(last_frame)).convert("RGBA")

    frames: list[bytes] = []
    for i in range(1, n_frames + 1):
        ratio = i / n_frames  # 0.25 … 1.0
        if fade_transparent:
            faded = src.copy()
            alpha_ch = faded.split()[3].point(lambda a, r=ratio: int(a * (1.0 - r)))
            faded.putalpha(alpha_ch)
        else:
            overlay = Image.new("RGBA", src.size, (*target_color[:3], int(255 * ratio)))
            faded = Image.alpha_composite(src, overlay).convert("RGB")
        buf = io.BytesIO()
        faded.save(buf, format="PNG")
        frames.append(buf.getvalue())

    frame_dur = max(1, duration_ms // n_frames)
    durations = [frame_dur] * n_frames
    # Absorb any rounding residual into the last frame.
    durations[-1] = max(1, duration_ms - frame_dur * (n_frames - 1))
    return frames, durations


def write_mp4(
    output: Path,
    frame_bytes: list[bytes],
    durations_ms: list[int],
    crf: int = 23,
    codec: str = "libx264",
    metadata: dict[str, str] | None = None,
) -> None:
    """Write *frame_bytes* as an MP4 video file using ffmpeg.

    Args:
        output: Destination ``.mp4`` (or ``.mov``) path.
        frame_bytes: Sequence of PNG-encoded frames.
        durations_ms: Per-frame display duration in milliseconds.
        crf: Constant Rate Factor controlling quality.  Lower = better quality
            and larger file.  Typical range: 0 (lossless) – 51 (worst).
            Default 23 is a good balance for flat-colour treemaps.
            For ``libx265`` the perceptually equivalent default is 28.
        codec: FFmpeg video codec.  ``"libx264"`` (H.264, default) is the most
            compatible; ``"libx265"`` (H.265/HEVC) gives ~40 % smaller files at
            the same perceived quality.
        metadata: Optional key/value pairs to embed as MP4 metadata atoms
            (passed to ffmpeg via ``-metadata key=value``).

    Raises:
        RuntimeError: If ffmpeg is not found on PATH or exits non-zero.
    """
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found on PATH.  Install it to write MP4 files:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Linux:  apt install ffmpeg  /  dnf install ffmpeg"
        )

    with tempfile.TemporaryDirectory(prefix="dirplot-mp4-") as tmpdir:
        tmp = Path(tmpdir)
        lines: list[str] = []
        for i, (png_bytes, dur_ms) in enumerate(zip(frame_bytes, durations_ms, strict=True)):
            frame_path = tmp / f"frame{i:06d}.png"
            frame_path.write_bytes(png_bytes)
            lines.append(f"file '{frame_path}'\n")
            lines.append(f"duration {dur_ms / 1000:.6f}\n")
        # The concat demuxer ignores the duration of the last entry; repeat the
        # last frame so ffmpeg has a file reference to close the stream cleanly.
        if frame_bytes:
            lines.append(f"file '{tmp / f'frame{len(frame_bytes) - 1:06d}.png'}'\n")

        concat_file = tmp / "concat.txt"
        concat_file.write_text("".join(lines))

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            codec,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            # libx264/libx265 require even dimensions
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        ]
        if metadata:
            cmd += ["-movflags", "use_metadata_tags"]
            for key, value in metadata.items():
                cmd += ["-metadata", f"{key}={value}"]
        cmd.append(str(output))
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg exited with code {result.returncode}:\n"
                f"{result.stderr.decode(errors='replace')}"
            )
