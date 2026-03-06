"""CLI entry point."""

from pathlib import Path

import matplotlib.pyplot as plt
import typer

from dirplot import __version__
from dirplot.display import display_inline, display_window
from dirplot.render import create_treemap
from dirplot.scanner import apply_log_sizes, build_tree, collect_extensions
from dirplot.terminal import get_terminal_pixel_size

app = typer.Typer(
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot .  [dim]# open in system viewer[/dim]\n\n"
    "  dirplot . --no-show --output treemap.png  [dim]# save to file[/dim]\n\n"
    "  dirplot . --inline  [dim]# render inline (iTerm2 / Kitty / Ghostty)[/dim]\n\n"
    "  dirplot . --legend  [dim]# show extension colour legend[/dim]\n\n"
    "  dirplot . --exclude .venv --exclude .git  [dim]# skip paths[/dim]\n\n"
    "  dirplot . --colormap Set2 --font-size 14  [dim]# custom colours and label size[/dim]\n\n"
    "  dirplot . --size 1920x1080 --no-show --output out.png  [dim]# fixed resolution[/dim]\n\n"
    "  dirplot . --no-header --inline  [dim]# suppress info lines before the plot[/dim]\n\n"
    "  dirplot . --no-cushion  [dim]# makes tiles look flat[/dim]"
)


@app.command(epilog=_EPILOG)
def main(
    root: Path = typer.Argument(..., help="Root directory to map"),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output PNG path (optional)"),
    show: bool = typer.Option(True, "--show/--no-show", help="Display the image after rendering"),
    inline: bool = typer.Option(
        False,
        "--inline",
        help="Show in terminal (auto-detects iTerm2/Kitty protocol) instead of a separate window",
    ),
    legend: bool = typer.Option(False, "--legend/--no-legend", help="Show extension legend"),
    font_size: int = typer.Option(
        12, "--font-size", "-s", help="Directory label font size in pixels (default: 12)"
    ),
    colormap: str = typer.Option(
        "tab20",
        "--colormap",
        "-c",
        help=(
            "Matplotlib colormap for file-extension colours (default: tab20). "
            "The default uses the GitHub Linguist palette for known extensions; "
            "any other colormap overrides Linguist and applies to all extensions. "
            "Qualitative maps (tab10, tab20, Set1-3, Paired, Accent, Dark2, Pastel1-2) "
            "give distinct hues. "
            "Sequential maps (viridis, plasma, inferno, Blues, Greens, …) "
            "blend across a gradient. "
            "Diverging maps (coolwarm, RdBu, Spectral, …) "
            "have two contrasting hues. "
            "Run with an invalid name to see all options."
        ),
    ),
    exclude: list[Path] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    size: str | None = typer.Option(
        None,
        "--size",
        help="Output size as WIDTHxHEIGHT in pixels (e.g. 1920x1080). Defaults to terminal size.",
        metavar="WIDTHxHEIGHT",
    ),
    header: bool = typer.Option(
        True, "--header/--no-header", help="Print info lines before rendering (default: on)"
    ),
    cushion: bool = typer.Option(
        True,
        "--cushion/--no-cushion",
        help="Apply van Wijk cushion shading: gives each tile a raised 3-D look.",
    ),
    log: bool = typer.Option(
        False,
        "--log/--no-log",
        help="Use log of file sizes for layout, making small files more visible.",
    ),
) -> None:
    """Create a nested treemap bitmap for a directory tree."""
    if colormap not in plt.colormaps():
        valid = ", ".join(sorted(plt.colormaps()))
        typer.echo(f"Unknown colormap '{colormap}'. Valid options:\n{valid}", err=True)
        raise typer.Exit(1)
    if not root.exists():
        typer.echo(f"Path does not exist: {root}", err=True)
        raise typer.Exit(1)
    if not root.is_dir():
        typer.echo(f"Not a directory: {root}", err=True)
        raise typer.Exit(1)

    excluded = frozenset(p.resolve() for p in exclude)
    if header:
        typer.echo(f"Scanning {root} ...")
    root_node = build_tree(root.resolve(), excluded)
    if log:
        apply_log_sizes(root_node)
    total_files = len(collect_extensions(root_node))
    if header:
        typer.echo(f"Found {total_files:,} files, total size: {root_node.size:,} bytes")

    if size is not None:
        try:
            w_str, h_str = size.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(
                f"Invalid --size value '{size}'. Expected format: WIDTHxHEIGHT (e.g. 1920x1080)",
                err=True,
            )
            raise typer.Exit(1) from None
        if header:
            typer.echo(f"Output size: {width_px}x{height_px}px")
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px
        if header:
            typer.echo(f"Terminal size: {width_px}x{height_px}px")

    buf = create_treemap(root_node, width_px, height_px, font_size, colormap, legend, cushion)

    if output is not None:
        output.write_bytes(buf.read())
        if header:
            typer.echo(f"Saved dirplot to {output}")
        buf.seek(0)

    if show:
        if inline:
            display_inline(buf)
        else:
            display_window(buf)
