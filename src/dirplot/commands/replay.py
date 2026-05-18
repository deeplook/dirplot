"""The ``replay`` command: replay a JSONL filesystem event log as an animated treemap."""

import io
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.defaults import DEFAULT_COLORMAP, DEFAULT_FONT_SIZE
from dirplot.filters import matches_exclude
from dirplot.helpers.animation import (
    proportional_durations,
    resolve_fade_color,
    worker_ignore_sigint,
)
from dirplot.helpers.highlights import resolve_highlight_specs
from dirplot.terminal import default_canvas_size

_REPLAY_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot replay events.jsonl -o replay.apng"
    "  [dim]# 60-second buckets, 500 ms/frame, APNG[/dim]\n\n"
    "  dirplot replay events.jsonl -o replay.mp4 --total-duration 30"
    "  [dim]# MP4, proportional timing, 30 s animation[/dim]\n\n"
    "  dirplot replay events.jsonl -o replay.mp4 --crf 18"
    "  [dim]# MP4, higher quality[/dim]\n\n"
    "  dirplot replay events.jsonl -o replay.mp4 --codec libx265 --crf 28"
    "  [dim]# H.265, smaller file[/dim]\n\n"
    "  dirplot replay events.jsonl -o replay.apng --bucket 10 --frame-duration 200"
    "  [dim]# finer-grained 10-second buckets[/dim]\n\n"
    "  dirplot replay events.jsonl -o replay.mp4 --total-duration 30 --fade-out"
    "  [dim]# fade to black at the end[/dim]\n\n"
    "  dirplot replay events.jsonl -o replay.apng --total-duration 30"
    "  --fade-out --fade-out-color white  [dim]# fade to white (light mode)[/dim]"
)


@app.command(name="replay", epilog=_REPLAY_EPILOG)
def replay_cmd(
    event_log: Path = typer.Argument(..., help="JSONL event log produced by fswatched.py"),
    output: Path = typer.Option(..., "--output", "-o", help="Output file (.png or .apng)"),
    bucket: float = typer.Option(
        60.0,
        "--bucket",
        help="Time bucket size in seconds: one frame per bucket",
        show_default=True,
    ),
    frame_duration: int = typer.Option(
        500, "--frame-duration", help="Frame display duration in ms (default: 500)"
    ),
    total_duration: float | None = typer.Option(
        None,
        "--total-duration",
        help=(
            "Target total animation length in seconds. Frames are shown proportionally"
            " to the real time gaps between buckets. Overrides --frame-duration."
        ),
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    font_size: int = typer.Option(
        DEFAULT_FONT_SIZE, "--font-size", help="Directory label font size in pixels"
    ),
    colormap: str = typer.Option(DEFAULT_COLORMAP, "--colormap", help="Matplotlib colormap"),
    size: str | None = typer.Option(
        None, "--size", help="Output size as WIDTHxHEIGHT", metavar="WIDTHxHEIGHT"
    ),
    cushion: bool = typer.Option(True, "--cushion/--no-cushion", help="Apply cushion shading"),
    dark: bool = typer.Option(True, "--dark/--light", help="Dark background (default) or light"),
    logscale: float = typer.Option(
        0.0,
        "--log-scale",
        help="Log-scale compression ratio (max/min ratio). 0 disables; must be > 1 to enable.",
        show_default=True,
    ),
    depth: int | None = typer.Option(None, "--depth", help="Maximum directory depth"),
    workers: int | None = typer.Option(
        None,
        "--workers",
        help="Parallel render workers (default: all CPU cores)",
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
        help="Append a fade-out sequence at the end of the animation",
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
    highlight: list[str] = typer.Option(
        [],
        "--highlight",
        "-H",
        help=(
            "Highlight matching paths with a coloured border in every frame (repeatable). "
            "Accepts exact paths or glob patterns including ** (e.g. src/**/*.py). "
            "Append @color to set the border colour (e.g. '**/*.py@orange'); "
            "defaults to red."
        ),
    ),
) -> None:
    """Replay a JSONL filesystem event log as an animated treemap."""
    from dirplot.replay_scanner import (
        _render_replay_frame_worker,
        apply_events,
        bucket_events,
        parse_events,
    )

    if workers is not None and workers <= 0:
        typer.echo("Error: --workers must be a positive integer.", err=True)
        raise typer.Exit(1)

    if not event_log.exists():
        typer.echo(f"Error: event log not found: {event_log}", err=True)
        raise typer.Exit(1)

    if output.suffix.lower() not in {".png", ".apng", ".mp4", ".mov"}:
        typer.echo("Error: --output must be a .png, .apng, .mp4, or .mov file.", err=True)
        raise typer.Exit(1)

    if size is not None:
        try:
            w_str, h_str = size.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(f"Invalid --size '{size}'. Expected WIDTHxHEIGHT.", err=True)
            raise typer.Exit(1) from None
        if width_px == 0 or height_px == 0:
            typer.echo(
                f"Invalid --size '{size}': width and height must both be positive.", err=True
            )
            raise typer.Exit(1)
    else:
        width_px, height_px = default_canvas_size()

    if not quiet:
        typer.echo(f"Reading events from {event_log} ...", err=True)
    events = parse_events(event_log)
    if not events:
        typer.echo("Error: no events found in event log.", err=True)
        raise typer.Exit(1)

    # Derive common root from all paths in the event log
    all_paths = [e[2] for e in events] + [e[3] for e in events if e[3]]
    common_root = Path(os.path.commonpath(all_paths))
    if not common_root.is_dir():
        common_root = common_root.parent
    if not quiet:
        typer.echo(f"Common root: {common_root}", err=True)

    excluded = frozenset(exclude)

    # Build initial files dict by statting only paths that appear in the event log
    files: dict[str, int] = {}
    for _ts, _type, path_str, dest_str in events:
        for p_str in (path_str, dest_str) if dest_str else (path_str,):
            p = Path(p_str)
            if not p_str.startswith(str(common_root)):
                continue
            if (
                matches_exclude(str(p.relative_to(common_root)).replace(os.sep, "/"), excluded)
                or not p.is_file()
            ):
                continue
            try:
                rel = str(p.relative_to(common_root)).replace(os.sep, "/")
                files[rel] = max(1, p.stat().st_size)
            except (OSError, ValueError):
                pass
    if not quiet:
        typer.echo(f"  {len(files)} unique files from event log", err=True)

    buckets = bucket_events(events, bucket)
    if not quiet:
        typer.echo(
            f"Grouped {len(events)} events into {len(buckets)} frame(s) ({bucket:.0f}s buckets) ...",  # noqa: E501
            err=True,
        )

    # Pre-compute per-frame durations
    if total_duration is not None:
        if total_duration <= 0:
            typer.echo("Error: --total-duration must be positive.", err=True)
            raise typer.Exit(1)
        timestamps = [ts for ts, _ in buckets]
        gaps: list[float] = [
            max(1.0, float(timestamps[j + 1] - timestamps[j])) for j in range(len(timestamps) - 1)
        ]
        gaps.append(gaps[-1] if gaps else 1.0)
        total_ms = total_duration * 1000
        frame_durations = proportional_durations(gaps, total_ms)
        min_d, max_d = min(frame_durations), max(frame_durations)
        if not quiet:
            typer.echo(
                f"  Proportional timing: {min_d}–{max_d} ms/frame"
                f" (total ~{sum(frame_durations) / 1000:.1f}s)",
                err=True,
            )
    else:
        frame_durations = [frame_duration] * len(buckets)

    # Phase 1: sequential pass — apply events bucket by bucket, collect snapshots
    Snapshot = tuple[int, float, dict[str, int], dict[str, str], dict[str, str]]
    snapshots: list[Snapshot] = []

    for i, (ts, bucket_evs) in enumerate(buckets):
        highlights = apply_events(files, common_root, bucket_evs, excluded)
        deletions = {p: v for p, v in highlights.items() if v == "deleted"}
        cur_hl = {p: v for p, v in highlights.items() if v != "deleted"}
        if highlight:
            abs_paths = [(common_root / rel).as_posix() for rel in files]
            cur_hl.update(resolve_highlight_specs(highlight, abs_paths))
        snapshots.append((i, ts, dict(files), cur_hl, deletions))

    # Phase 2: parallel render
    total = len(snapshots)
    n_workers = min(workers if workers is not None else (os.cpu_count() or 1), total)
    if not quiet:
        typer.echo(f"Rendering {total} frame(s) using {n_workers} worker(s) ...", err=True)

    total_anim_ms = sum(frame_durations)
    cumulative_ms = 0.0
    frame_progress: dict[int, float] = {}
    for orig_i, *_ in snapshots:
        cumulative_ms += frame_durations[orig_i]
        frame_progress[orig_i] = cumulative_ms / total_anim_ms

    render_args = [
        (
            str(common_root),
            files_copy,
            cur_hl,
            ts,
            orig_i,
            frame_progress[orig_i],
            depth,
            logscale,
            width_px,
            height_px,
            font_size,
            colormap,
            cushion,
            dark,
        )
        for orig_i, ts, files_copy, cur_hl, _del in snapshots
    ]

    raw: dict[int, tuple[bytes, dict[str, tuple[int, int, int, int]]]] = {}

    try:
        with ProcessPoolExecutor(max_workers=n_workers, initializer=worker_ignore_sigint) as pool:
            futures = {
                pool.submit(_render_replay_frame_worker, args): args[4] for args in render_args
            }
            for done, future in enumerate(as_completed(futures), 1):
                orig_i, png_bytes, rect_map = future.result()
                raw[orig_i] = (png_bytes, rect_map)
                if not quiet:
                    typer.echo(f"  Rendered {done}/{total}", err=True)
    except KeyboardInterrupt:
        typer.echo("\nInterrupted.", err=True)
        raise typer.Exit(1) from None

    # Phase 3: assemble ordered frames, patch deletions onto prior frame
    frame_bytes: list[bytes] = []
    final_durations: list[int] = []

    for j, (orig_i, _ts, _files, _hl, deletions) in enumerate(snapshots):
        if deletions and j > 0:
            prev_bytes, prev_rect = raw[snapshots[j - 1][0]]
            from PIL import Image, ImageDraw

            from dirplot.render_png import _draw_highlights

            prev_img = Image.open(io.BytesIO(prev_bytes)).convert("RGB")
            _draw_highlights(ImageDraw.Draw(prev_img), prev_rect, deletions)
            buf = io.BytesIO()
            prev_img.save(buf, format="PNG")
            frame_bytes[-1] = buf.getvalue()
        frame_bytes.append(raw[orig_i][0])
        final_durations.append(frame_durations[orig_i])

    if fade_out and frame_bytes:
        from dirplot.render_png import _frames_as_rgba, make_fade_out_frames

        fade_color = resolve_fade_color(fade_out_color, dark)
        fade_transparent = len(fade_color) == 4 and fade_color[3] == 0
        if fade_transparent and output.suffix.lower() in {".mp4", ".mov"}:
            fade_color = (0, 0, 0) if dark else (255, 255, 255)
            fade_transparent = False
        if fade_transparent:
            frame_bytes = _frames_as_rgba(frame_bytes)
        n_fo = fade_out_frames
        if n_fo is None:
            n_fo = max(1, round(fade_out_duration * 4))
        extra, extra_durs = make_fade_out_frames(
            frame_bytes[-1],
            n_frames=n_fo,
            duration_ms=int(fade_out_duration * 1000),
            target_color=fade_color,
        )
        frame_bytes.extend(extra)
        final_durations.extend(extra_durs)

    if output.suffix.lower() in {".mp4", ".mov"}:
        from dirplot.render_png import build_metadata, write_mp4

        write_mp4(
            output, frame_bytes, final_durations, crf=crf, codec=codec, metadata=build_metadata()
        )
    else:
        from dirplot.render_png import write_apng

        write_apng(output, frame_bytes, final_durations)
    if not quiet:
        typer.echo(
            f"Wrote {len(frame_bytes)}-frame {output.suffix.upper()[1:]} → {output}", err=True
        )
