"""Simplified treemap command using the rendering pipeline."""

from __future__ import annotations

from pathlib import Path

import typer

from dirplot.app import app
from dirplot.defaults import DEFAULT_COLORMAP, DEFAULT_FONT_SIZE
from dirplot.pipeline import PipelineConfig, RenderingPipeline


def _parse_size(size_str: str | None) -> tuple[int, int] | None:
    """Parse 'WIDTHxHEIGHT' string to tuple."""
    if size_str is None:
        return None
    try:
        w_str, h_str = size_str.lower().split("x", 1)
        return int(w_str), int(h_str)
    except ValueError:
        raise typer.BadParameter(
            f"Invalid size format: {size_str}. Expected WIDTHxHEIGHT"
        ) from None


@app.command(name="map-pipeline", hidden=True)
def map_pipeline(
    roots: list[str] = typer.Argument(
        default=None,
        help="Root(s) to map: directories, archives, or remote URLs",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output file (use .svg for SVG output)"
    ),
    show: bool | None = typer.Option(None, "--show/--no-show", help="Display after rendering"),
    inline: bool = typer.Option(False, "--inline", help="Show inline in terminal"),
    size: str | None = typer.Option(None, "--size", help="Output size as WIDTHxHEIGHT"),
    font_size: int = typer.Option(DEFAULT_FONT_SIZE, "--font-size"),
    colormap: str = typer.Option(DEFAULT_COLORMAP, "--colormap"),
    exclude: list[str] = typer.Option([], "--exclude", "-e"),
    include: list[str] = typer.Option([], "--include"),
    depth: int | None = typer.Option(None, "--depth"),
    logscale: float = typer.Option(0.0, "--log-scale"),
    no_breadcrumbs: bool = typer.Option(False, "--no-breadcrumbs"),
    no_cushion: bool = typer.Option(False, "--no-cushion"),
    light: bool = typer.Option(False, "--light", help="Use light background"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Create a treemap using the simplified pipeline.

    This is a demonstration of the new pipeline architecture.
    """
    if not roots:
        typer.echo("Error: at least one path is required", err=True)
        raise typer.Exit(1)

    def log(msg: str) -> None:
        if not quiet:
            typer.echo(msg, err=True)

    config = PipelineConfig(
        roots=roots,
        exclude=frozenset(exclude),
        depth=depth,
        include=set(include),
        breadcrumbs=not no_breadcrumbs,
        logscale=logscale,
        size=_parse_size(size),
        font_size=font_size,
        colormap=colormap,
        cushion=not no_cushion,
        dark=not light,
        format="svg" if (output and output.suffix == ".svg") else "png",
        output=output,
        show=show if show is not None else (output is None or output.suffix != ".svg"),
        inline=inline,
        log_callback=log,
    )

    pipeline = RenderingPipeline(config)

    try:
        pipeline.run()
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
