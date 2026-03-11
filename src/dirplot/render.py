"""Treemap layout and PNG rendering."""

import io
from collections import defaultdict
from pathlib import Path

import numpy as np
import squarify
from PIL import Image, ImageDraw, ImageFont

from dirplot.colors import RGBAColor, assign_colors
from dirplot.scanner import Node, collect_extensions

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


def _label_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Return black or white text color based on the background luminance."""
    gray = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return (0, 0, 0) if gray >= 128 else (255, 255, 255)


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return int(bb[2] - bb[0])


def _wrap(name: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    """Wrap *name* into lines that each fit within *max_w* pixels."""
    if max_w < 4 or _text_w(draw, name, font) <= max_w:
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
    if max_w < 4 or _text_w(draw, name, font) <= max_w:
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


def _apply_cushion(img: Image.Image, x: int, y: int, w: int, h: int) -> None:
    """Apply van Wijk-style quadratic cushion shading to a tile in-place."""
    if w < 4 or h < 4:
        return
    xs = np.arange(w, dtype=float)
    ys = np.arange(h, dtype=float)
    gx, gy = np.meshgrid(xs, ys)

    # Quadratic surface: h = Ix*(gx)*(w-1-gx) + Iy*(gy)*(h-1-gy)
    # Surface normal components (un-normalized): (-dh/dx, -dh/dy, 1)
    # Use Ix = C/w (not C/w²) so edge slope is size-independent: same visible
    # shading depth on large tiles as on small ones.
    Ix, Iy = 0.12 / w, 0.12 / h
    nx = Ix * (w - 1 - 2 * gx)
    ny = Iy * (h - 1 - 2 * gy)

    # Light direction: top-left, slightly above the surface
    lx, ly, lz = 1.0, 1.0, 1.2
    mag = (lx**2 + ly**2 + lz**2) ** 0.5
    lx, ly, lz = lx / mag, ly / mag, lz / mag

    brightness = nx * lx + ny * ly + lz  # dot(normal, light)
    brightness = np.clip(brightness, 0.0, None)
    brightness /= brightness.mean()  # preserve average luminance

    tile = img.crop((x, y, x + w, y + h))
    arr = np.array(tile, dtype=float)
    arr[:, :, :3] *= brightness[:, :, np.newaxis]
    np.clip(arr, 0, 255, out=arr)
    img.paste(Image.fromarray(arr.astype(np.uint8)), (x, y))


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
) -> None:
    """Recursively draw *node* and its children into *draw*.

    Args:
        draw: PIL ImageDraw to draw into.
        node: Current tree node.
        x, y: Top-left corner in pixels.
        w, h: Width and height in pixels.
        color_map: Extension → RGBA colour mapping.
        font: Font for directory name labels.
        scale: Global font scale factor.
    """
    if w < 2 or h < 2:
        return

    if not node.is_dir:
        rgba = color_map.get(node.extension, (0.5, 0.5, 0.5, 1.0))
        rgb = (int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=rgb)
        if cushion and img is not None:
            _apply_cushion(img, x, y, w, h)
        # 1-px border so adjacent same-colored tiles always have a visible boundary
        if w >= 3 and h >= 3:
            dark = (max(0, rgb[0] - 60), max(0, rgb[1] - 60), max(0, rgb[2] - 60))
            draw.rectangle([x, y, x + w - 1, y + h - 1], outline=dark)
        # Adaptive label: font size scales with tile size, capped by scale factor
        if w > 20 and h > 10:
            fsize = max(6, min(font_size + 2, w // 10))
            ffont = _font(fsize)
            label = _wrap(node.name, draw, ffont, w - 4)
            draw.text(
                (x + w // 2, y + h // 2),
                label,
                fill=_label_color(rgb),
                font=ffont,
                anchor="mm",
                align="center",
            )
        return

    # Directory: 1-px white outer border + 1-px black inner border
    draw.rectangle([x, y, x + w - 1, y + h - 1], outline=(255, 255, 255), width=1)
    if w >= 4 and h >= 4:
        draw.rectangle([x + 1, y + 1, x + w - 2, y + h - 2], outline=(0, 0, 0), width=1)

    # Header label — height driven by the font size
    header_h = font.size + 4
    if h > 2 + header_h:
        label = _truncate(node.name, draw, font, w - 8)
        draw.text(
            (x + w // 2, y + 2 + header_h // 2),
            label,
            fill=(224, 224, 224),
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

    # Black background provides the 1-px separator between adjacent children
    draw.rectangle([ix, iy, ix + iw - 1, iy + ih - 1], fill=(0, 0, 0))

    for rect, child in zip(rects, positive_children, strict=False):
        rx = round(rect["x"])
        ry = round(rect["y"])
        rw = round(rect["x"] + rect["dx"]) - rx
        rh = round(rect["y"] + rect["dy"]) - ry
        draw_node(draw, child, rx, ry, rw - 1, rh - 1, color_map, font, font_size, cushion, img)


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
) -> None:
    margin = 4
    bb = draw.textbbox((0, 0), "Ag", font=font)
    text_h = bb[3] - bb[1]
    row_h = max(SWATCH_PX, text_h) + LEG_PAD
    rows_that_fit = max(1, (height_px - 2 * margin - LEG_PAD * 2 - row_h) // row_h)
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

    draw.rectangle([bx, by, bx + box_w - 1, by + box_h - 1], fill=(20, 20, 36))
    draw.rectangle([bx, by, bx + box_w - 1, by + box_h - 1], outline=(80, 80, 80), width=1)

    for ri, ext in enumerate(top):
        rgba = color_map.get(ext, (0.5, 0.5, 0.5, 1.0))
        rgb = (int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))
        ex = bx + LEG_PAD
        row_mid = by + LEG_PAD + ri * row_h + (row_h - LEG_PAD) // 2
        sy = row_mid - SWATCH_PX // 2
        draw.rectangle(
            [ex, sy, ex + SWATCH_PX - 1, sy + SWATCH_PX - 1],
            fill=rgb,
            outline=(255, 255, 255),
            width=1,
        )
        draw.text(
            (ex + SWATCH_PX + LEG_PAD, row_mid),
            ext,
            fill=(220, 220, 220),
            font=font,
            anchor="lm",
        )
        draw.text(
            (bx + box_w - LEG_PAD, row_mid),
            str(ext_counts[ext]),
            fill=(160, 160, 160),
            font=font,
            anchor="rm",
        )

    if more_label:
        row_mid = by + LEG_PAD + len(top) * row_h + (row_h - LEG_PAD) // 2
        draw.text(
            (bx + LEG_PAD + SWATCH_PX + LEG_PAD, row_mid),
            more_label,
            fill=(120, 120, 120),
            font=font,
            anchor="lm",
        )


def create_treemap(
    root_node: Node,
    width_px: int,
    height_px: int,
    font_size: int = 12,
    colormap: str = "tab20",
    legend: int | None = None,
    cushion: bool = True,
) -> io.BytesIO:
    """Render a nested squarified treemap and return it as a PNG in a BytesIO buffer.

    Args:
        root_node: Root of the directory tree.
        width_px: Output image width in pixels.
        height_px: Output image height in pixels.
        font_size: Directory label font size in pixels.
        colormap: Matplotlib colormap name for file-extension colours.
        legend: Max entries in the file-count legend, or None to disable.

    Returns:
        BytesIO containing the rendered PNG, seeked to position 0.
    """
    exts = collect_extensions(root_node)
    color_map = assign_colors(exts, colormap)

    img = Image.new("RGB", (width_px, height_px), color=(26, 26, 46))
    idraw = ImageDraw.Draw(img)
    font = _font(font_size, bold=True)

    draw_node(idraw, root_node, 0, 0, width_px, height_px, color_map, font, font_size, cushion, img)

    if legend is not None:
        overlay_font = _font(max(6, font_size - 2))
        corner = _best_corner(root_node, width_px, height_px)
        ext_counts = _collect_ext_counts(root_node)
        _draw_legend(
            idraw, ext_counts, color_map, width_px, height_px, corner, overlay_font, legend
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
