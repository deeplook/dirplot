"""Treemap layout and SVG rendering using drawsvg."""

import html
import io
from collections import defaultdict

import drawsvg
import squarify

from dirplot.colors import RGBAColor, assign_colors
from dirplot.render import _human_bytes
from dirplot.scanner import Node, collect_extensions, count_nodes

_CHAR_ASPECT = 0.6  # approximate width/height ratio for monospace font
_FONT_FAMILY = "JetBrains Mono, Consolas, monospace"

SWATCH_PX = 8
LEG_PAD = 3

# Van Wijk cushion: brightness ranges from ×0.80 (bottom-right) to ×1.20 (top-left).
# We approximate this with a diagonal overlay: white at opacity=0.20 blends into
# black at opacity=0.20, with a transparent midpoint so the center is unchanged.
_CUSHION_HIGHLIGHT = 0.20  # white overlay opacity at top-left
_CUSHION_SHADOW = 0.20  # black overlay opacity at bottom-right

# ---------------------------------------------------------------------------
# Interactive effects: CSS + JS
# ---------------------------------------------------------------------------

_HOVER_CSS = """\
.tile {
    cursor: pointer;
    transition: filter 0.10s ease;
}
.tile:hover {
    filter: brightness(1.22) drop-shadow(0 0 3px rgba(255,255,255,0.45));
}
.dir-tile {
    cursor: default;
    transition: filter 0.10s ease;
}
.dir-tile:hover {
    filter: brightness(1.18);
}
"""

# JavaScript for the floating SVG tooltip.
# Reads data-* attributes set on .tile and .dir-tile elements.
_TOOLTIP_JS = """\
(function () {
  var TIP_W = 226, TIP_H = 58;

  function humanSize(b) {
    b = +b;
    if (b < 1024)       return b + '\u202fB';
    if (b < 1048576)    return (b / 1024).toFixed(1) + '\u202fKB';
    if (b < 1073741824) return (b / 1048576).toFixed(1) + '\u202fMB';
    return (b / 1073741824).toFixed(2) + '\u202fGB';
  }

  var tip, tipL0, tipL1, tipL2;

  function init() {
    tip  = document.getElementById('_dp_tip');
    tipL0 = document.getElementById('_dp_tip_l0');
    tipL1 = document.getElementById('_dp_tip_l1');
    tipL2 = document.getElementById('_dp_tip_l2');
    if (!tip) return;

    document.querySelectorAll('.tile, .dir-tile').forEach(function (el) {
      el.addEventListener('mouseenter', onEnter);
      el.addEventListener('mousemove',  onMove);
      el.addEventListener('mouseleave', onLeave);
    });
  }

  function toSVGPt(evt) {
    var svg = evt.currentTarget.ownerSVGElement || evt.currentTarget;
    var pt  = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }

  function place(evt) {
    var sp  = toSVGPt(evt);
    var svg = evt.currentTarget.ownerSVGElement || evt.currentTarget;
    var vb  = svg.viewBox.baseVal;
    var tx  = sp.x + 14, ty = sp.y + 14;
    if (tx + TIP_W + 4 > vb.width)  tx = sp.x - TIP_W - 6;
    if (ty + TIP_H + 4 > vb.height) ty = sp.y - TIP_H - 6;
    tip.setAttribute('transform', 'translate(' + tx + ',' + ty + ')');
  }

  function onEnter(evt) {
    var d = evt.currentTarget.dataset;
    var isDir = d.isDir === '1';
    tipL0.textContent = d.name + (isDir ? '/' : '');
    if (isDir) {
      tipL1.textContent = humanSize(d.size) + ' total';
      tipL2.textContent = (+d.count) + ' item' + (+d.count !== 1 ? 's' : '');
    } else {
      tipL1.textContent = humanSize(d.size);
      tipL2.textContent = d.ext || '(no extension)';
    }
    place(evt);
    tip.setAttribute('visibility', 'visible');
  }

  function onMove(evt)  { place(evt); }
  function onLeave()    { tip.setAttribute('visibility', 'hidden'); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""


def _append_tooltip_element(d: drawsvg.Drawing, font_size: int) -> None:
    """Add a reusable floating SVG tooltip group to *d* (must be last element)."""
    fs = max(9, font_size - 1)
    tip = drawsvg.Group(id="_dp_tip", visibility="hidden", pointer_events="none")
    tip.append(
        drawsvg.Rectangle(
            0,
            0,
            226,
            58,
            id="_dp_tip_bg",
            fill="#141424",
            rx=4,
            stroke="#606070",
            stroke_width=1,
            fill_opacity=0.72,
        )
    )
    tip.append(
        drawsvg.Text(
            "",
            fs,
            10,
            fs + 4,
            id="_dp_tip_l0",
            fill="#e8e8e8",
            font_family=_FONT_FAMILY,
            font_weight="bold",
        )
    )
    tip.append(
        drawsvg.Text(
            "",
            fs - 1,
            10,
            fs + 4 + fs + 3,
            id="_dp_tip_l1",
            fill="#a0a8b0",
            font_family=_FONT_FAMILY,
        )
    )
    tip.append(
        drawsvg.Text(
            "",
            fs - 1,
            10,
            fs + 4 + (fs + 3) * 2,
            id="_dp_tip_l2",
            fill="#707880",
            font_family=_FONT_FAMILY,
        )
    )
    d.append(tip)


# ---------------------------------------------------------------------------
# Cushion gradient
# ---------------------------------------------------------------------------


def _make_cushion_gradient() -> drawsvg.LinearGradient:
    """Return a diagonal gradient that approximates the van Wijk cushion shading.

    Uses ``gradientUnits="objectBoundingBox"`` so the same object scales to any
    tile rectangle without redefinition.
    """
    grad: drawsvg.LinearGradient = drawsvg.LinearGradient(
        0, 0, 1, 1, gradientUnits="objectBoundingBox"
    )
    grad.add_stop(0.0, "white", _CUSHION_HIGHLIGHT)  # top-left highlight
    grad.add_stop(0.5, "black", 0.0)  # transparent centre — no tint
    grad.add_stop(1.0, "black", _CUSHION_SHADOW)  # bottom-right shadow
    return grad


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------


def _hex(rgba: RGBAColor) -> str:
    r, g, b = int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def _label_color(rgba: RGBAColor) -> str:
    """Return black or white text color based on the background luminance."""
    gray = 0.299 * rgba[0] * 255 + 0.587 * rgba[1] * 255 + 0.114 * rgba[2] * 255
    return "#000000" if gray >= 128 else "#ffffff"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _wrap(name: str, font_size: int, max_w: float) -> list[str]:
    """Wrap *name* into lines fitting *max_w*, approximating monospace char width."""
    char_w = font_size * _CHAR_ASPECT
    max_chars = max(1, int(max_w / char_w))
    if len(name) <= max_chars:
        return [name]
    delimiters = "._ -"
    lines: list[str] = []
    remaining = name
    while remaining:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            break
        chunk = remaining[:max_chars]
        split = max((chunk.rfind(d) for d in delimiters), default=-1)
        if split > 0:
            lines.append(remaining[:split])
            remaining = remaining[split:]
        else:
            lines.append(chunk)
            remaining = remaining[max_chars:]
    return lines


def _truncate(name: str, font_size: int, max_w: float) -> str:
    """Truncate *name* with an ellipsis so it fits within *max_w*."""
    char_w = font_size * _CHAR_ASPECT
    max_chars = max(1, int(max_w / char_w))
    if len(name) <= max_chars:
        return name
    return name[: max(0, max_chars - 1)] + "\u2026"


# ---------------------------------------------------------------------------
# Recursive draw
# ---------------------------------------------------------------------------


def _draw_node_svg(
    d: drawsvg.Drawing,
    node: Node,
    x: float,
    y: float,
    w: float,
    h: float,
    color_map: dict[str, RGBAColor],
    font_size: int = 12,
    cushion_grad: drawsvg.LinearGradient | None = None,
    root_label: str | None = None,
) -> None:
    """Recursively draw *node* and its children into *d*."""
    if w < 2 or h < 2:
        return

    if not node.is_dir:
        rgba = color_map.get(node.extension, (0.5, 0.5, 0.5, 1.0))
        fill = _hex(rgba)

        display_size = node.original_size if node.original_size > 0 else node.size
        dark = (max(0, rgba[0] - 0.24), max(0, rgba[1] - 0.24), max(0, rgba[2] - 0.24))
        stroke = _hex((*dark, 1.0)) if w >= 3 and h >= 3 else "none"
        rect = drawsvg.Rectangle(
            x,
            y,
            w,
            h,
            fill=fill,
            stroke=stroke,
            stroke_width="1",
            class_="tile",
            data_name=html.escape(node.name),
            data_size=str(display_size),
            data_ext=html.escape(node.extension),
            data_is_dir="0",
        )
        d.append(rect)

        if cushion_grad is not None and w >= 4 and h >= 4:
            d.append(drawsvg.Rectangle(x, y, w, h, fill=cushion_grad, pointer_events="none"))

        if w > 20 and h > 10:
            fsize = max(6, min(font_size + 2, int(w // 10)))
            text_fill = _label_color(rgba)
            lines = _wrap(node.name, fsize, w - 4)

            clip = drawsvg.ClipPath()
            clip.append(drawsvg.Rectangle(x + 1, y + 1, w - 2, h - 2))
            d.append(clip)

            if len(lines) == 1:
                d.append(
                    drawsvg.Text(
                        lines[0],
                        fsize,
                        x + w / 2,
                        y + h / 2,
                        text_anchor="middle",
                        dominant_baseline="middle",
                        fill=text_fill,
                        font_family=_FONT_FAMILY,
                        clip_path=clip,
                        pointer_events="none",
                    )
                )
            else:
                line_h = fsize * 1.2
                total_h = len(lines) * line_h
                ty = y + h / 2 - total_h / 2 + fsize * 0.85
                t = drawsvg.Text(
                    "",
                    fsize,
                    x + w / 2,
                    ty,
                    text_anchor="middle",
                    fill=text_fill,
                    font_family=_FONT_FAMILY,
                    clip_path=clip,
                    pointer_events="none",
                )
                for i, line in enumerate(lines):
                    t.append(drawsvg.TSpan(line, x=x + w / 2, dy="0" if i == 0 else "1.2em"))
                d.append(t)
        return

    # Directory: 1-px white outer border + 1-px black inner border
    d.append(drawsvg.Rectangle(x, y, w, h, fill="none", stroke="white", stroke_width=1))
    if w >= 4 and h >= 4:
        d.append(
            drawsvg.Rectangle(
                x + 1, y + 1, w - 2, h - 2, fill="none", stroke="black", stroke_width=1
            )
        )

    header_h = font_size + 4
    if h > 2 + header_h:
        # Header background — also acts as the hover + tooltip target for the dir
        n_children = len(node.children)
        display_size = node.original_size if node.original_size > 0 else node.size
        hdr = drawsvg.Rectangle(
            x + 2,
            y + 2,
            w - 4,
            header_h,
            fill="#1c1c2e",
            class_="dir-tile",
            data_name=html.escape(node.name),
            data_size=str(display_size),
            data_is_dir="1",
            data_count=str(n_children),
            data_ext="",
        )
        d.append(hdr)

        label = _truncate(root_label if root_label is not None else node.name, font_size, w - 8)
        hclip = drawsvg.ClipPath()
        hclip.append(drawsvg.Rectangle(x + 2, y + 2, w - 4, header_h))
        d.append(hclip)
        d.append(
            drawsvg.Text(
                label,
                font_size,
                x + w / 2,
                y + 2 + header_h / 2,
                text_anchor="middle",
                dominant_baseline="middle",
                fill="#e0e0e0",
                font_family=_FONT_FAMILY,
                font_weight="bold",
                clip_path=hclip,
                pointer_events="none",
            )
        )

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

    # Black background provides 1-px separator between adjacent children
    d.append(drawsvg.Rectangle(ix, iy, iw, ih, fill="black"))

    for rect, child in zip(rects, positive_children, strict=False):
        rx = round(rect["x"])
        ry = round(rect["y"])
        rw = round(rect["x"] + rect["dx"]) - rx - 1
        rh = round(rect["y"] + rect["dy"]) - ry - 1
        _draw_node_svg(d, child, rx, ry, rw, rh, color_map, font_size, cushion_grad)


# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------


def _draw_legend_svg(
    d: drawsvg.Drawing,
    ext_counts: dict[str, int],
    color_map: dict[str, RGBAColor],
    width_px: int,
    height_px: int,
    font_size: int,
    corner: str,
    max_rows: int = 20,
) -> None:
    margin = 4
    char_w = font_size * _CHAR_ASPECT
    row_h = max(SWATCH_PX, font_size) + LEG_PAD
    rows_that_fit = max(1, (height_px - 2 * margin - LEG_PAD * 2 - row_h) // row_h)
    limit = min(max_rows, rows_that_fit)

    ranked = sorted(ext_counts, key=lambda e: (-ext_counts[e], e))
    top = ranked[:limit]
    n_more = len(ranked) - limit
    if not top:
        return

    more_label = f"(+{n_more})" if n_more > 0 else ""

    label_w = max(len(ext) * char_w for ext in top)
    if more_label:
        label_w = max(label_w, len(more_label) * char_w)
    count_w = max(len(str(ext_counts[e])) * char_w for e in top)
    box_w = SWATCH_PX + LEG_PAD + label_w + LEG_PAD + count_w + LEG_PAD * 2
    n_rows = len(top) + (1 if more_label else 0)
    box_h = n_rows * row_h + LEG_PAD * 2

    bx = (width_px - box_w - margin) if "right" in corner else margin
    by = (height_px - box_h - margin) if "lower" in corner else margin

    d.append(drawsvg.Rectangle(bx, by, box_w, box_h, fill="#141424"))
    d.append(drawsvg.Rectangle(bx, by, box_w, box_h, fill="none", stroke="#505050", stroke_width=1))

    for ri, ext in enumerate(top):
        rgba = color_map.get(ext, (0.5, 0.5, 0.5, 1.0))
        fill = _hex(rgba)
        ex = bx + LEG_PAD
        row_mid = by + LEG_PAD + ri * row_h + (row_h - LEG_PAD) / 2
        sy = row_mid - SWATCH_PX / 2
        d.append(
            drawsvg.Rectangle(
                ex, sy, SWATCH_PX, SWATCH_PX, fill=fill, stroke="white", stroke_width=1
            )
        )
        d.append(
            drawsvg.Text(
                ext,
                font_size,
                ex + SWATCH_PX + LEG_PAD,
                row_mid,
                text_anchor="start",
                dominant_baseline="middle",
                fill="#dcdcdc",
                font_family=_FONT_FAMILY,
            )
        )
        d.append(
            drawsvg.Text(
                str(ext_counts[ext]),
                font_size,
                bx + box_w - LEG_PAD,
                row_mid,
                text_anchor="end",
                dominant_baseline="middle",
                fill="#a0a0a0",
                font_family=_FONT_FAMILY,
            )
        )

    if more_label:
        row_mid = by + LEG_PAD + len(top) * row_h + (row_h - LEG_PAD) / 2
        d.append(
            drawsvg.Text(
                more_label,
                font_size,
                bx + LEG_PAD + SWATCH_PX + LEG_PAD,
                row_mid,
                text_anchor="start",
                dominant_baseline="middle",
                fill="#787878",
                font_family=_FONT_FAMILY,
            )
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_treemap_svg(
    root_node: Node,
    width_px: int,
    height_px: int,
    font_size: int = 12,
    colormap: str = "tab20",
    legend: int | None = None,
    cushion: bool = True,
) -> io.BytesIO:
    """Render a nested squarified treemap and return it as SVG in a BytesIO buffer.

    The output is an interactive SVG:

    * **Native tooltips** — ``<title>`` on every tile; shown by the browser on hover.
    * **CSS hover highlight** — tiles brighten and gain a soft glow on mouse-over.
    * **Floating tooltip panel** — JS-driven panel that tracks the cursor and shows
      name, size (human-readable), and file type / item count.

    Cushion shading is approximated via a diagonal SVG gradient overlay that
    matches the van Wijk quadratic surface lighting used in the PNG renderer
    (×1.20 highlight at top-left, ×0.80 shadow at bottom-right).

    Args:
        root_node: Root of the directory tree.
        width_px: Output image width in pixels.
        height_px: Output image height in pixels.
        font_size: Directory label font size in pixels.
        colormap: Matplotlib colormap name for file-extension colours.
        legend: Whether to draw an extension colour legend.
        cushion: Apply van Wijk-style cushion shading via a gradient overlay.

    Returns:
        BytesIO containing the rendered SVG, seeked to position 0.
    """
    exts = collect_extensions(root_node)
    color_map = assign_colors(exts, colormap)

    d: drawsvg.Drawing = drawsvg.Drawing(width_px, height_px)

    # 1. CSS hover effects
    d.append_css(_HOVER_CSS)

    # 2. Background
    d.append(drawsvg.Rectangle(0, 0, width_px, height_px, fill="#1a1a2e"))

    # 3. Optional cushion gradient (defined once, reused by all tiles)
    cushion_grad: drawsvg.LinearGradient | None = None
    if cushion:
        cushion_grad = _make_cushion_gradient()
        d.append(cushion_grad)

    # 4. Treemap tiles
    n_files, n_dirs = count_nodes(root_node)
    total_bytes = root_node.original_size if root_node.original_size > 0 else root_node.size
    root_label = (
        f"{root_node.name} \u2014 {n_files:,} files, {n_dirs:,} dirs,"
        f" {_human_bytes(total_bytes)} ({total_bytes:,} bytes)"
    )
    _draw_node_svg(
        d,
        root_node,
        0,
        0,
        width_px,
        height_px,
        color_map,
        font_size,
        cushion_grad,
        root_label=root_label,
    )

    # 5. Optional legend
    if legend is not None:
        overlay_font = max(6, font_size - 2)
        ext_counts = _collect_ext_counts(root_node)
        _draw_legend_svg(
            d, ext_counts, color_map, width_px, height_px, overlay_font, "lower-right", legend
        )

    # 6. Floating tooltip element — must be last so it renders above all tiles
    _append_tooltip_element(d, font_size)

    # 8. Tooltip JavaScript
    d.append_javascript(_TOOLTIP_JS)

    svg_content = d.as_svg()
    buf = io.BytesIO(svg_content.encode("utf-8"))
    buf.seek(0)
    return buf
