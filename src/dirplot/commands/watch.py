"""The ``watch`` command: regenerate treemap on filesystem changes."""

import signal
import time
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.defaults import DEFAULT_COLORMAP, DEFAULT_FONT_SIZE
from dirplot.terminal import default_canvas_size


@app.command(name="watch")
def watch_cmd(
    paths: list[Path] = typer.Argument(..., help="Directories to watch"),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    font_size: int = typer.Option(
        DEFAULT_FONT_SIZE, "--font-size", help="Directory label font size in pixels"
    ),
    colormap: str = typer.Option(DEFAULT_COLORMAP, "--colormap", help="Matplotlib colormap"),
    size: str | None = typer.Option(
        None, "--size", help="Output size as WIDTHxHEIGHT", metavar="WIDTHxHEIGHT"
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
    event_log: Path | None = typer.Option(
        None,
        "--event-log",
        help="Write all raw events as JSONL to this file on exit",
        metavar="FILE",
    ),
    snapshot: Path | None = typer.Option(
        None,
        "--snapshot",
        help="Write the current treemap as a PNG to this file on each filesystem change.",
        metavar="FILE",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
) -> None:
    """Watch one or more directories and regenerate the treemap on every file change."""
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

    if size is not None:
        try:
            w_str, h_str = size.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(f"Invalid --size '{size}'. Expected WIDTHxHEIGHT.", err=True)
            raise typer.Exit(1) from None
    else:
        width_px, height_px = default_canvas_size()

    excluded = frozenset(exclude)
    roots = [path.resolve() for path in paths]

    handler = TreemapEventHandler(
        roots,
        output=snapshot,
        exclude=excluded,
        width_px=width_px,
        height_px=height_px,
        font_size=font_size,
        colormap=colormap,
        cushion=cushion,
        logscale=logscale,
        debounce=debounce,
        event_log=event_log,
        depth=depth,
        dark=dark,
    )

    observer = Observer()
    try:
        # Generate an initial treemap immediately
        roots_str = ", ".join(str(r) for r in roots)
        if not quiet:
            typer.echo(f"Scanning {roots_str} ...", err=True)
        handler._regenerate()

        for root in roots:
            observer.schedule(handler, str(root), recursive=True)
        observer.start()
        if not quiet:
            snapshot_info = f" → {snapshot}" if snapshot else ""
            typer.echo(f"Watching {roots_str}{snapshot_info}  (Ctrl-C to stop)", err=True)

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        handler.flush()
        if observer.is_alive():
            observer.stop()
            observer.join()
