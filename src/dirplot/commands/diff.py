"""The ``diff`` command: treemap of two directory trees with diff highlights."""

from __future__ import annotations

import time
import webbrowser
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.display import display_inline, display_window
from dirplot.terminal import get_terminal_pixel_size

# Border colours for diff status — applied to file tile borders only.
# Fill colours remain the standard Linguist/colormap palette.
DIFF_COLORS: dict[str, str] = {
    "removed": "deleted",  # red   — in A but not in B
    "added": "created",  # green — in B but not in A
    "changed": "modified",  # blue  — in both, but size differs
}

_DIFF_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot diff src/ build/  [dim]# compare two local directories[/dim]\n\n"
    "  dirplot diff v1/ v2/ --output diff.png  [dim]# save to file[/dim]\n\n"
    "  dirplot diff v1/ v2/ --no-show --output diff.svg  [dim]# SVG output[/dim]\n\n"
    "  dirplot diff v1/ v2/ --size 1920x1080  [dim]# fixed resolution[/dim]\n\n"
    "  dirplot diff v1/ v2/ --depth 3  [dim]# limit directory depth[/dim]\n\n"
    "\n[bold]Highlight colours (borders only)[/bold]\n\n"
    "  [green]green[/green]  — added (in B, not in A)\n"
    "  [red]red[/red]    — removed (in A, not in B)\n"
    "  [blue]blue[/blue]   — changed (in both, but size differs in B)\n"
)


@app.command(name="diff", epilog=_DIFF_EPILOG)
def diff_cmd(
    tree_a: str = typer.Argument(..., metavar="A", help="Source tree (baseline)"),
    tree_b: str = typer.Argument(..., metavar="B", help="Target tree (comparison)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Save image to file"),
    fmt: str | None = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format: png or svg (inferred from --output extension if omitted)",
        metavar="FORMAT",
    ),
    show: bool = typer.Option(True, "--show/--no-show", help="Display the image after rendering"),
    inline: bool = typer.Option(
        False,
        "--inline",
        help="Show in terminal (auto-detects iTerm2/Kitty protocol) instead of a separate window",
    ),
    font_size: int = typer.Option(12, "--font-size", help="Directory label font size in pixels"),
    colormap: str = typer.Option(
        "tab20",
        "--colormap",
        help="Colormap for file-extension fill colours (default: tab20 uses Linguist palette)",
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    depth: int | None = typer.Option(None, "--depth", help="Maximum directory depth"),
    size: str | None = typer.Option(
        None, "--size", help="Output dimensions as WIDTHxHEIGHT", metavar="WIDTHxHEIGHT"
    ),
    cushion: bool = typer.Option(True, "--cushion/--no-cushion", help="Van Wijk cushion shading"),
    dark: bool = typer.Option(True, "--dark/--light", help="Dark background (default) or light"),
    log_scale: float = typer.Option(
        0.0,
        "--log-scale",
        help="Log-scale compression ratio (> 1 to enable)",
        show_default=True,
    ),
    context: bool = typer.Option(
        True,
        "--context/--no-context",
        help="Include unchanged files for context. --no-context shows only diff files.",
    ),
    header: bool = typer.Option(True, "--header/--no-header", help="Print info lines to stderr"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output"),
) -> None:
    """Compare two directory trees A and B as a treemap with diff highlights.

    Files are sized by their size in B (the target tree). Borders indicate
    diff status: [green]green[/green] = added, [red]red[/red] = removed,
    [blue]blue[/blue] = changed (size differs).
    Unchanged files show no border. Use --no-context to hide them entirely.
    """
    import sys

    import cmap as _cmap_lib

    from dirplot.git_scanner import build_node_tree
    from dirplot.render_png import create_treemap
    from dirplot.scanner import apply_log_sizes, build_tree
    from dirplot.svg_render import create_treemap_svg

    def _info(msg: str) -> None:
        if not quiet:
            typer.echo(msg, err=True)

    # Validate colormap
    _valid_cmaps = set(_cmap_lib.Catalog().short_keys())
    if colormap not in _valid_cmaps:
        valid = ", ".join(sorted(_valid_cmaps))
        typer.echo(f"Unknown colormap '{colormap}'. Valid options:\n{valid}", err=True)
        raise typer.Exit(1)

    path_a = Path(tree_a)
    path_b = Path(tree_b)

    for label, p in (("A", path_a), ("B", path_b)):
        if not p.exists():
            typer.echo(f"Error: tree {label} not found: {p}", err=True)
            raise typer.Exit(1)
        if not p.is_dir():
            typer.echo(f"Error: tree {label} is not a directory: {p}", err=True)
            raise typer.Exit(1)

    excluded = frozenset(Path(e).resolve() for e in exclude)

    # Scan both trees
    t0 = time.monotonic()
    _info(f"Scanning A: {path_a} ...")
    node_a = build_tree(path_a, exclude=excluded, depth=depth)
    _info(f"Scanning B: {path_b} ...")
    node_b = build_tree(path_b, exclude=excluded, depth=depth)
    t_scan = time.monotonic() - t0
    _info(f"Scanned in {t_scan:.1f}s")

    # Build flat file maps {rel_path: size}
    def _flatten(node: object, prefix: str = "") -> dict[str, int]:
        from dirplot.scanner import Node as ScanNode

        n: ScanNode = node  # type: ignore[assignment]
        result: dict[str, int] = {}
        if not n.is_dir:
            result[prefix] = n.size
        else:
            for child in n.children:
                child_prefix = f"{prefix}/{child.name}" if prefix else child.name
                result.update(_flatten(child, child_prefix))
        return result

    files_a = _flatten(node_a)
    files_b = _flatten(node_b)

    # Compute diff highlights keyed by absolute path in B's tree
    # (highlights uses absolute paths matching the renderer's rect_map keys)
    highlights: dict[str, str] = {}
    all_keys = set(files_a) | set(files_b)
    for rel in all_keys:
        abs_path = str((path_b / rel).resolve())
        if rel in files_a and rel not in files_b:
            highlights[abs_path] = DIFF_COLORS["removed"]
        elif rel not in files_a and rel in files_b:
            highlights[abs_path] = DIFF_COLORS["added"]
        elif rel in files_a and rel in files_b and files_a[rel] != files_b[rel]:
            highlights[abs_path] = DIFF_COLORS["changed"]

    n_removed = sum(1 for v in highlights.values() if v == DIFF_COLORS["removed"])
    n_added = sum(1 for v in highlights.values() if v == DIFF_COLORS["added"])
    n_changed = sum(1 for v in highlights.values() if v == DIFF_COLORS["changed"])
    _info(f"Diff: {n_added} added, {n_removed} removed, {n_changed} changed")

    # Build combined node tree sized by B.
    # With --context: include all files (unchanged for context + diff files).
    # With --no-context: include only files that changed, were added, or were removed.
    changed_keys = {
        rel
        for rel in set(files_a) | set(files_b)
        if rel not in files_b  # removed
        or rel not in files_a  # added
        or files_a[rel] != files_b[rel]  # changed
    }
    if context:
        combined_files = dict(files_b)
        for rel in files_a:
            if rel not in combined_files:
                combined_files[rel] = files_a[rel]
    else:
        combined_files = {
            rel: (files_b[rel] if rel in files_b else files_a[rel]) for rel in changed_keys
        }

    root_node = build_node_tree(path_b, combined_files, depth)

    if log_scale > 1:
        apply_log_sizes(root_node, log_scale)

    # Resolve output size
    to_stdout = output is not None and str(output) == "-"
    if size is not None:
        try:
            w_str, h_str = size.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(f"Invalid --size '{size}'. Expected WIDTHxHEIGHT.", err=True)
            raise typer.Exit(1) from None
        _info(f"Output size: {width_px}x{height_px}px")
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px
        _info(f"Terminal size: {width_px}x{height_px}px")

    # Resolve format
    if fmt is not None:
        if fmt not in ("png", "svg"):
            typer.echo(f"Unknown format '{fmt}'. Valid options: png, svg", err=True)
            raise typer.Exit(1)
        use_svg = fmt == "svg"
    elif output is not None and output.suffix.lower() == ".svg":
        use_svg = True
    else:
        use_svg = False

    title_suffix = f"{path_a.name} → {path_b.name}"

    t_render_start = time.monotonic()
    if use_svg:
        buf = create_treemap_svg(
            root_node, width_px, height_px, font_size, colormap, None, cushion, depth, dark
        )
    else:
        buf = create_treemap(
            root_node,
            width_px,
            height_px,
            font_size,
            colormap,
            None,
            cushion,
            depth,
            highlights=highlights,
            title_suffix=title_suffix,
            dark=dark,
            logscale=log_scale,
        )
    t_render = time.monotonic() - t_render_start

    if output is not None:
        if to_stdout:
            sys.stdout.buffer.write(buf.read())
            buf.seek(0)
        else:
            output.write_bytes(buf.read())
            _info(f"Saved diff to {output}  [{t_render:.1f}s]")
            buf.seek(0)

    if show and not to_stdout:
        if use_svg:
            if output is not None:
                webbrowser.open(output.resolve().as_uri())
            else:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
                    tmp.write(buf.read())
                    webbrowser.open(Path(tmp.name).resolve().as_uri())
        elif inline:
            display_inline(buf)
        else:
            display_window(buf, title=f"dirplot diff: {title_suffix}")
