"""The ``watch`` command: regenerate treemap on filesystem changes."""

import signal
import time
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.helpers.animation import resolve_fade_color
from dirplot.terminal import get_terminal_pixel_size


@app.command(name="watch")
def watch_cmd(
    paths: list[Path] = typer.Argument(..., help="Directories to watch"),
    output: Path = typer.Option(
        ..., "--output", "-o", help="Output file (.png, .apng, .mp4, or .svg)"
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    font_size: int = typer.Option(12, "--font-size", help="Directory label font size in pixels"),
    colormap: str = typer.Option("tab20", "--colormap", help="Matplotlib colormap"),
    size: str | None = typer.Option(
        None, "--size", help="Output size as WIDTHxHEIGHT", metavar="WIDTHxHEIGHT"
    ),
    cushion: bool = typer.Option(
        True, "--cushion/--no-cushion", help="Apply van Wijk cushion shading"
    ),
    dark: bool = typer.Option(True, "--dark/--light", help="Dark background (default) or light"),
    animate: bool = typer.Option(
        False,
        "--animate/--no-animate",
        help="Build an animated APNG or MP4 by appending each new frame",
    ),
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
    crf: int = typer.Option(
        23,
        "--crf",
        help="MP4 quality: Constant Rate Factor (0=lossless, 51=worst; default 23). "
        "Ignored for APNG output.",
        show_default=True,
    ),
    codec: str = typer.Option(
        "libx264",
        "--codec",
        help="MP4 video codec: libx264 (H.264, default) or libx265 (H.265, smaller files). "
        "Ignored for APNG output.",
    ),
    fade_out: bool = typer.Option(
        False,
        "--fade-out/--no-fade-out",
        help="Append a fade-out sequence at the end of the animation (--animate only)",
    ),
    fade_out_duration: float = typer.Option(
        1.0,
        "--fade-out-duration",
        help="Total duration of the fade-out in seconds",
        show_default=True,
    ),
    fade_out_frames: int | None = typer.Option(
        None,
        "--fade-out-frames",
        help="Number of equidistant frames in the fade-out (default: 4 per second of duration)",
    ),
    fade_out_color: str = typer.Option(
        "auto",
        "--fade-out-color",
        help=(
            "Target colour for the fade-out: 'auto' (black in dark mode, white in light mode), "
            "'transparent' (APNG only), a CSS colour name, or a hex code"
        ),
        metavar="COLOR",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
) -> None:
    """Watch one or more directories and regenerate the treemap on every file change.

    With [bold]--animate[/bold] and a [bold].mp4[/bold] output path, frames are written
    as an MP4 video on exit (requires ffmpeg). Use [bold]--crf[/bold] and
    [bold]--codec[/bold] to control quality and codec.
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

    if animate and output.suffix.lower() == ".svg":
        typer.echo("Error: --animate requires a PNG, MP4, or MOV output file.", err=True)
        raise typer.Exit(1)

    if size is not None:
        try:
            w_str, h_str = size.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(f"Invalid --size '{size}'. Expected WIDTHxHEIGHT.", err=True)
            raise typer.Exit(1) from None
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px

    excluded = frozenset(exclude)
    roots = [path.resolve() for path in paths]

    handler = TreemapEventHandler(
        roots,
        output,
        exclude=excluded,
        width_px=width_px,
        height_px=height_px,
        font_size=font_size,
        colormap=colormap,
        cushion=cushion,
        animate=animate,
        logscale=logscale,
        debounce=debounce,
        event_log=event_log,
        depth=depth,
        crf=crf,
        codec=codec,
        dark=dark,
        fade_out=fade_out,
        fade_out_duration=fade_out_duration,
        fade_out_frames=fade_out_frames,
        fade_out_color=resolve_fade_color(fade_out_color, dark) if fade_out else (0, 0, 0),
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
            typer.echo(f"Watching {roots_str} → {output}  (Ctrl-C to stop)", err=True)

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        # Ignore further Ctrl-C so flush() can finish writing the APNG.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        handler.flush()
        if observer.is_alive():
            observer.stop()
            observer.join()
