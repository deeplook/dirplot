"""The ``watch`` command: regenerate treemap on filesystem changes."""

import time
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.defaults import DEFAULT_COLORMAP, DEFAULT_FONT_SIZE
from dirplot.terminal import default_canvas_size

_WATCH_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot watch src --output events.jsonl  [dim]# record events for replay[/dim]\n\n"
    "  dirplot watch src tests --output events.jsonl  [dim]# watch multiple directories[/dim]\n\n"
    "  dirplot watch src --output events.jsonl --append  [dim]# append to existing log[/dim]\n\n"
    "  dirplot watch . --output events.jsonl --snapshot treemap.png"
    "  [dim]# log + live snapshot[/dim]\n\n"
    "  dirplot watch . --snapshot treemap.png --debounce 1.0  [dim]# snapshot only[/dim]\n\n"
    "  dirplot watch . --highlight '**/*.py@orange'  [dim]# highlight Python files[/dim]\n\n"
    "  dirplot watch . --include src  [dim]# show only the src subtree[/dim]"
)


@app.command(name="watch", epilog=_WATCH_EPILOG)
def watch_cmd(
    paths: list[Path] = typer.Argument(..., help="Directories to watch"),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Write filesystem events as JSONL to this file, flushed after each regeneration. "
            "Use with `dirplot replay` to turn the recording into an animation."
        ),
        metavar="FILE",
    ),
    append: bool = typer.Option(
        False,
        "--append/--no-append",
        help="Append to an existing --output file instead of truncating it on startup.",
    ),
    snapshot: Path | None = typer.Option(
        None,
        "--snapshot",
        help=(
            "Also write the current treemap as a PNG or SVG on each change. "
            "Convenient for small trees; avoid on large directories as rendering adds latency."
        ),
        metavar="FILE",
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    include: list[str] = typer.Option(
        [],
        "--include",
        help=(
            "Show only this subtree (repeatable; supports nested paths like src/fonts). "
            "Allowlist complement to --exclude."
        ),
    ),
    highlight: list[str] = typer.Option(
        [],
        "--highlight",
        "-H",
        help=(
            "Highlight matching paths with a coloured border (repeatable). "
            "Accepts exact paths or glob patterns including ** (e.g. src/**/*.py). "
            "Append @color to set the border colour (e.g. '**/*.py@orange'); "
            "defaults to red."
        ),
    ),
    font_size: int = typer.Option(
        DEFAULT_FONT_SIZE, "--font-size", help="Directory label font size in pixels"
    ),
    colormap: str = typer.Option(DEFAULT_COLORMAP, "--colormap", help="Matplotlib colormap"),
    canvas: str | None = typer.Option(
        None, "--canvas", help="Output size as WIDTHxHEIGHT", metavar="WIDTHxHEIGHT"
    ),
    size_filter: list[str] | None = typer.Option(
        None,
        "--size",
        "-S",
        help=(
            "Filter files by size range (e.g. 10M..500M, 100M.., ..50K, 1G). "
            "Repeatable — multiple ranges are combined with OR logic."
        ),
        metavar="RANGE",
    ),
    keep_empty_dirs: bool = typer.Option(
        False,
        "--keep-empty-dirs",
        help="Retain directories that become empty after --size filtering.",
    ),
    cushion: bool = typer.Option(
        True, "--cushion/--no-cushion", help="Apply van Wijk cushion shading"
    ),
    dark: bool = typer.Option(True, "--dark/--light", help="Dark background (default) or light"),
    logscale: float = typer.Option(
        0.0,
        "--log-scale",
        help="Log-scale compression ratio (max/min ratio). 0 disables; must be > 1 to enable.",
        show_default=True,
    ),
    depth: int | None = typer.Option(
        None,
        "--depth",
        help="Maximum recursion depth (same as for map)",
    ),
    debounce: float = typer.Option(
        0.5,
        "--debounce",
        help="Seconds of quiet after last event before regenerating (0 to disable)",
        show_default=True,
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
) -> None:
    """Watch directories and record filesystem events as JSONL for later replay.

    Use `dirplot replay` to turn the recording into an animated treemap.
    Pass --snapshot to also write a live PNG/SVG on each change (best for small trees).

    Example: dirplot watch src --output events.jsonl
    """
    from dirplot.watch import TreemapEventHandler

    try:
        from watchdog.observers import Observer
    except ImportError:
        typer.echo("Error: watchdog is required. Run: pip install watchdog", err=True)
        raise typer.Exit(1) from None

    for path in paths:
        if not path.exists() or not path.is_dir():
            typer.echo(f"Error: not a directory: {path}", err=True)
            raise typer.Exit(1)

    if logscale != 0 and logscale <= 1:
        typer.echo("Error: --log-scale must be > 1 (or 0 to disable).", err=True)
        raise typer.Exit(1)

    if debounce < 0:
        typer.echo("Error: --debounce must be >= 0.", err=True)
        raise typer.Exit(1)

    if canvas is not None:
        try:
            w_str, h_str = canvas.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(f"Invalid --canvas '{canvas}'. Expected WIDTHxHEIGHT.", err=True)
            raise typer.Exit(1) from None
        if width_px == 0 or height_px == 0:
            typer.echo(
                f"Invalid --canvas '{canvas}': width and height must both be positive.", err=True
            )
            raise typer.Exit(1)
    else:
        width_px, height_px = default_canvas_size()

    parsed_size_ranges = None
    if size_filter:
        from dirplot.filters import parse_size_range

        parsed_size_ranges = []
        for spec in size_filter:
            try:
                parsed_size_ranges.append(parse_size_range(spec))
            except ValueError as exc:
                typer.echo(f"Invalid --size value: {exc}", err=True)
                raise typer.Exit(1) from exc

    excluded = frozenset(exclude)
    roots = [path.resolve() for path in paths]

    handler = TreemapEventHandler(
        roots,
        snapshot=snapshot,
        exclude=excluded,
        width_px=width_px,
        height_px=height_px,
        font_size=font_size,
        colormap=colormap,
        cushion=cushion,
        logscale=logscale,
        debounce=debounce,
        output=output,
        append_output=append,
        depth=depth,
        dark=dark,
        size_ranges=parsed_size_ranges,
        keep_empty_dirs=keep_empty_dirs,
        highlight_specs=highlight or None,
        include=set(include) if include else None,
    )

    observer = Observer()
    try:
        roots_str = ", ".join(str(r) for r in roots)
        if not quiet:
            typer.echo(f"Scanning {roots_str} ...", err=True)
        handler._regenerate()

        for root in roots:
            observer.schedule(handler, str(root), recursive=True)
        observer.start()
        if not quiet:
            output_info = f" → {output}" if output else ""
            snapshot_info = f" (snapshot: {snapshot})" if snapshot else ""
            typer.echo(
                f"Watching {roots_str}{output_info}{snapshot_info}  (Ctrl-C to stop)", err=True
            )

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        handler.flush()
        if observer.is_alive():
            observer.stop()
            observer.join()
