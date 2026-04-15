"""CLI entry point."""

import re
import signal
import sys
import time
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime as _datetime
from pathlib import Path

import matplotlib.pyplot as plt
import typer

from dirplot import __version__
from dirplot.archives import PasswordRequired, build_tree_archive, is_archive_path
from dirplot.display import display_inline, display_window
from dirplot.docker import build_tree_docker, is_docker_path, parse_docker_path
from dirplot.github import (
    _gh_cli_token,
    build_tree_github,
    count_commits_github,
    is_github_path,
    parse_github_path,
)
from dirplot.k8s import build_tree_pod, is_pod_path, parse_pod_path
from dirplot.pathlist import parse_pathlist
from dirplot.render_png import create_treemap
from dirplot.s3 import build_tree_s3, is_s3_path, make_s3_client, parse_s3_path
from dirplot.scanner import (
    Node,
    apply_breadcrumbs,
    apply_log_sizes,
    build_tree,
    build_tree_multi,
    collect_extensions,
    max_depth,
    prune_to_subtrees,
)
from dirplot.ssh import build_tree_ssh, connect, is_ssh_path, parse_ssh_path
from dirplot.svg_render import create_treemap_svg
from dirplot.terminal import get_terminal_pixel_size, get_terminal_size

app = typer.Typer(
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode="rich",
)


def _worker_ignore_sigint() -> None:
    """Initializer for ProcessPoolExecutor workers: ignore SIGINT so Ctrl-C is
    handled only by the main process and workers exit cleanly on shutdown."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _proportional_durations(gaps: list[float], total_ms: float, floor_ms: int = 200) -> list[int]:
    """Convert time *gaps* into integer frame durations that sum to *total_ms*.

    Each frame gets a duration proportional to its gap.  Frames whose
    proportional share would fall below *floor_ms* are raised to that floor;
    the remaining frames are scaled down so the total still equals *total_ms*.
    A final rounding correction is applied to the longest frame so the integer
    sum matches exactly.
    """
    total_gap = sum(gaps)
    proportional = [g / total_gap * total_ms for g in gaps]

    # Apply floor
    raw = [max(float(floor_ms), p) for p in proportional]

    # If flooring inflated the total, scale down the non-floored frames to compensate.
    raw_sum = sum(raw)
    if raw_sum > total_ms:
        floored_budget = floor_ms * sum(1 for p in proportional if p < floor_ms)
        non_floored_sum = sum(v for p, v in zip(proportional, raw, strict=False) if p >= floor_ms)
        available = total_ms - floored_budget
        if available > 0 and non_floored_sum > 0:
            scale = available / non_floored_sum
            raw = [
                v if p < floor_ms else v * scale for p, v in zip(proportional, raw, strict=False)
            ]
        # else: every frame is at the floor — can't compress further, accept slight overage

    durations = [max(floor_ms, min(65535, round(d))) for d in raw]

    # Absorb integer-rounding residual into the longest frame.
    residual = round(total_ms) - sum(durations)
    if residual and durations:
        idx = max(range(len(durations)), key=lambda i: durations[i])
        durations[idx] = max(floor_ms, durations[idx] + residual)

    return durations


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def _resolve_fade_color(
    color_str: str, dark: bool
) -> tuple[int, int, int] | tuple[int, int, int, int]:
    """Resolve a --fade-out-color string to an RGB or RGBA tuple.

    ``"auto"`` returns black (dark mode) or white (light mode).
    ``"transparent"`` returns ``(0, 0, 0, 0)``.
    Any other string is parsed by PIL's ``ImageColor.getrgb()``.
    """
    if color_str == "auto":
        return (0, 0, 0) if dark else (255, 255, 255)
    if color_str.lower() == "transparent":
        return (0, 0, 0, 0)
    from PIL import ImageColor

    try:
        return ImageColor.getrgb(color_str)
    except (ValueError, AttributeError):
        typer.echo(
            f"Error: invalid --fade-out-color {color_str!r}. "
            "Use a colour name, hex code, or 'transparent'.",
            err=True,
        )
        raise typer.Exit(1) from None


@app.callback(invoke_without_command=True)
def _app_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot map .  [dim]# open in system viewer[/dim]\n\n"
    "  dirplot map . --no-show --output treemap.png  [dim]# save to file[/dim]\n\n"
    "  dirplot map github://owner/repo  [dim]# map a GitHub repo[/dim]\n\n"
    "  dirplot map . --inline  [dim]# render inline (iTerm2 / Kitty / Ghostty)[/dim]\n\n"
    "  dirplot map . --legend 20  [dim]# show file-count legend (top 20)[/dim]\n\n"
    "  dirplot map . --exclude .venv --exclude .git  [dim]# skip paths[/dim]\n\n"
    "  dirplot map . --colormap Set2 --font-size 14  [dim]# custom colours and label size[/dim]\n\n"
    "  dirplot map . --size 1920x1080 --no-show --output out.png  [dim]# fixed resolution[/dim]\n\n"
    "  dirplot map . --no-header --inline  [dim]# suppress info lines before the plot[/dim]\n\n"
    "  dirplot map . --no-cushion  [dim]# makes tiles look flat[/dim]\n\n"
    "  dirplot map archive.zip  [dim]# map a zip archive without unpacking[/dim]\n\n"
    "  dirplot map release.tar.gz --depth 2  [dim]# limit depth into a tarball[/dim]\n\n"
    "  dirplot map app.jar --exclude META-INF  [dim]# skip a member directory[/dim]\n\n"
    "  dirplot map src tests  [dim]# map two subtrees under their common parent[/dim]\n\n"
    "  dirplot map . --subtree src --subtree tests  [dim]# same result, explicit root[/dim]"
)


@app.command(name="termsize")
def termsize() -> None:
    """Show the current terminal size in characters and pixels."""
    cols, rows, width_px, height_px = get_terminal_size()
    typer.echo(f"Characters : {cols} cols × {rows} rows")
    typer.echo(f"Pixels     : {width_px} × {height_px}")


@app.command(name="watch")
def watch_cmd(
    paths: list[Path] = typer.Argument(..., help="Directories to watch"),
    output: Path = typer.Option(
        ..., "--output", "-o", help="Output file (.png, .apng, .mp4, or .svg)"
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    font_size: int = typer.Option(12, "--font-size", help="Directory label font size in pixels"),
    colormap: str = typer.Option("tab20", "--colormap", "-c", help="Matplotlib colormap"),
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
    log: bool = typer.Option(
        False,
        "--log/--no-log",
        help="Use log of file sizes for layout, making small files more visible",
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

    excluded = frozenset(Path(e).resolve() for e in exclude)
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
        log=log,
        debounce=debounce,
        event_log=event_log,
        depth=depth,
        crf=crf,
        codec=codec,
        dark=dark,
        fade_out=fade_out,
        fade_out_duration=fade_out_duration,
        fade_out_frames=fade_out_frames,
        fade_out_color=_resolve_fade_color(fade_out_color, dark) if fade_out else (0, 0, 0),
    )

    observer = Observer()
    try:
        # Generate an initial treemap immediately
        roots_str = ", ".join(str(r) for r in roots)
        typer.echo(f"Scanning {roots_str} ...", err=True)
        handler._regenerate()

        for root in roots:
            observer.schedule(handler, str(root), recursive=True)
        observer.start()
        typer.echo(f"Watching {roots_str} → {output}  (Ctrl-C to stop)")

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


_LAST_RE = re.compile(r"^(\d+)(mo|m|h|d|w)$")


def parse_last_period(value: str) -> _datetime:
    """Parse a human period string into an absolute UTC datetime.

    Units: m=minutes, h=hours, d=days, w=weeks, mo=months (30d each).
    Examples: '10d', '24h', '2w', '1mo', '30m'
    """
    from datetime import datetime, timedelta, timezone

    match = _LAST_RE.match(value.strip().lower())
    if not match:
        raise ValueError(
            f"Invalid --last value {value!r}. "
            "Expected a number + unit: h, d, w, mo  (e.g. 24h, 10d, 2w, 1mo)."
        )
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400, "mo": 30 * 86400}[unit]
    return datetime.now(tz=timezone.utc) - timedelta(seconds=amount * seconds)


def _run_vcs_animation(
    repo: Path,
    snapshots: list[tuple[int, str, int, dict[str, int], dict[str, str], dict[str, str]]],
    commit_durations: list[int],
    output: Path,
    *,
    width_px: int,
    height_px: int,
    font_size: int,
    colormap: str,
    depth: int | None,
    log_scale: bool,
    cushion: bool,
    dark: bool,
    workers: int | None,
    crf: int,
    codec: str,
    fade_out: bool,
    fade_out_duration: float,
    fade_out_frames: int | None,
    fade_out_color: str,
) -> None:
    """Render *snapshots* to an animated APNG or MP4 at *output*.

    Phases 2–4 of the VCS animation pipeline: parallel frame rendering,
    deletion-highlight patching, and output writing.  Shared by ``git_cmd``
    and ``hg_cmd``; the VCS-specific Phase 1 (collecting snapshots) is
    handled by each command.
    """
    import io
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from dirplot.git_scanner import _render_frame_worker
    from dirplot.render_png import _draw_highlights

    # ── Phase 2: parallel render ──────────────────────────────────────────
    total = len(snapshots)
    n_workers = min(workers if workers is not None else (os.cpu_count() or 1), total)
    typer.echo(f"Rendering {total} frame(s) using {n_workers} worker(s) ...", err=True)

    # Per-frame progress: fraction of total animation time elapsed after each
    # frame plays.  With proportional timing this reflects real bursts; with
    # fixed durations it is the same as linear.
    total_anim_ms = sum(commit_durations)
    cumulative_ms = 0.0
    frame_progress: dict[int, float] = {}
    for orig_i, *_ in snapshots:
        cumulative_ms += commit_durations[orig_i]
        frame_progress[orig_i] = cumulative_ms / total_anim_ms

    render_args = [
        (
            str(repo),
            files_copy,
            cur_hl,
            sha,
            ts,
            orig_i,
            frame_progress[orig_i],
            depth,
            log_scale,
            width_px,
            height_px,
            font_size,
            colormap,
            cushion,
            dark,
        )
        for orig_i, sha, ts, files_copy, cur_hl, _del in snapshots
    ]

    # raw[orig_i] = (png_bytes, rect_map) as returned by the worker
    raw: dict[int, tuple[bytes, dict[str, tuple[int, int, int, int]]]] = {}

    try:
        with ProcessPoolExecutor(max_workers=n_workers, initializer=_worker_ignore_sigint) as pool:
            futures = {pool.submit(_render_frame_worker, args): args[5] for args in render_args}
            for done, future in enumerate(as_completed(futures), 1):
                orig_i, png_bytes, rect_map = future.result()
                raw[orig_i] = (png_bytes, rect_map)
                typer.echo(f"  Rendered {done}/{total}", err=True)
    except KeyboardInterrupt:
        typer.echo("\nInterrupted.", err=True)
        raise typer.Exit(1) from None

    # ── Phase 3: assemble ordered frames, patch deletions ─────────────────
    frame_bytes: list[bytes] = []
    frame_durations: list[int] = []

    for j, (orig_i, _sha, _ts, _files, _hl, deletions) in enumerate(snapshots):
        if deletions and j > 0:
            # Draw deletion highlights onto the previous frame.
            prev_bytes, prev_rect = raw[snapshots[j - 1][0]]
            from PIL import Image, ImageDraw

            prev_img = Image.open(io.BytesIO(prev_bytes)).convert("RGB")
            _draw_highlights(ImageDraw.Draw(prev_img), prev_rect, deletions)
            buf = io.BytesIO()
            prev_img.save(buf, format="PNG")
            frame_bytes[-1] = buf.getvalue()
        frame_bytes.append(raw[orig_i][0])
        frame_durations.append(commit_durations[orig_i])

    # ── Phase 4: write output ─────────────────────────────────────────────
    if fade_out and frame_bytes:
        from dirplot.render_png import _frames_as_rgba, make_fade_out_frames

        fade_color = _resolve_fade_color(fade_out_color, dark)
        fade_transparent = len(fade_color) == 4 and fade_color[3] == 0
        if fade_transparent and output.suffix.lower() in {".mp4", ".mov"}:
            fade_color = (0, 0, 0) if dark else (255, 255, 255)
            fade_transparent = False
        if fade_transparent:
            frame_bytes = _frames_as_rgba(frame_bytes)
        extra, extra_durs = make_fade_out_frames(
            frame_bytes[-1],
            n_frames=fade_out_frames
            if fade_out_frames is not None
            else max(1, round(fade_out_duration * 4)),
            duration_ms=int(fade_out_duration * 1000),
            target_color=fade_color,
        )
        frame_bytes.extend(extra)
        frame_durations.extend(extra_durs)

    if output.suffix.lower() in {".mp4", ".mov"}:
        from dirplot.render_png import build_metadata, write_mp4

        write_mp4(
            output,
            frame_bytes,
            frame_durations,
            crf=crf,
            codec=codec,
            metadata=build_metadata(),
        )
    else:
        from dirplot.render_png import write_apng

        write_apng(output, frame_bytes, frame_durations)
    fmt = output.suffix.upper()[1:]
    typer.echo(f"Wrote {len(frame_bytes)}-frame {fmt} → {output}", err=True)


_GIT_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot git . -o history.apng --animate"
    "  [dim]# full history, APNG[/dim]\n\n"
    "  dirplot git . -o history.mp4 --animate"
    "  [dim]# full history, MP4 (H.264, CRF 23)[/dim]\n\n"
    "  dirplot git . -o history.mp4 --animate --crf 18 --codec libx265"
    "  [dim]# high-quality H.265[/dim]\n\n"
    "  dirplot git .@my-branch -o history.mp4 --animate"
    "  [dim]# specific local branch[/dim]\n\n"
    "  dirplot git . -o history.mp4 --animate --range v1.0..HEAD"
    "  [dim]# explicit revision range[/dim]\n\n"
    "  dirplot git . -o history.mp4 --animate --last 30d"
    "  [dim]# last 30 days of commits[/dim]\n\n"
    "  dirplot git github://owner/repo -o history.mp4 --animate --max-commits 50"
    "  [dim]# GitHub repo[/dim]"
)


@app.command(name="git", epilog=_GIT_EPILOG)
def git_cmd(
    repo_arg: str = typer.Argument(
        ".",
        help=(
            "Git repository path (optionally suffixed with @ref, e.g. .@my-branch),"
            " github://owner/repo[@branch], or https://github.com/owner/repo"
        ),
    ),
    output: Path = typer.Option(..., "--output", "-o", help="Output PNG file"),
    revision_range: str | None = typer.Option(
        None,
        "--range",
        "-r",
        help=(
            "Git revision range (e.g. main~50..main). "
            "When using a GitHub URL with --max-commits, "
            "ensure the clone depth covers the range's base commit."
        ),
    ),
    max_commits: int | None = typer.Option(
        None, "--max-commits", "-n", help="Maximum number of commits to process"
    ),
    last: str | None = typer.Option(
        None,
        "--last",
        help="Show commits within a time period (e.g. 10d, 24h, 2w, 1mo). "
        "May be combined with --max-commits.",
        metavar="PERIOD",
    ),
    exclude: list[str] = typer.Option(
        [], "--exclude", "-e", help="Top-level paths to exclude (repeatable)"
    ),
    font_size: int = typer.Option(12, "--font-size", help="Directory label font size in pixels"),
    colormap: str = typer.Option("tab20", "--colormap", "-c", help="Matplotlib colormap"),
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
        help="Build an animated APNG or MP4 from all commits",
    ),
    log: bool = typer.Option(False, "--log/--no-log", help="Use log of file sizes for layout"),
    depth: int | None = typer.Option(None, "--depth", help="Maximum directory depth"),
    frame_duration: int = typer.Option(
        1000,
        "--frame-duration",
        help="Frame display duration in ms when not using --total-duration",
    ),
    total_duration: float | None = typer.Option(
        None,
        "--total-duration",
        help=(
            "Target total animation length in seconds.  Frames are shown proportionally"
            " to the real time gaps between commits.  Overrides --frame-duration."
        ),
    ),
    workers: int | None = typer.Option(
        None,
        "--workers",
        "-w",
        help="Parallel render workers for animate mode (default: all CPU cores).  "
        "Rendering is memory-bandwidth bound, so the optimal value depends on your hardware; "
        "try --workers 4-8 if the default is slower than expected.",
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
    github_token: str | None = typer.Option(
        None,
        "--github-token",
        envvar="GITHUB_TOKEN",
        help="GitHub personal access token for private repos",
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
) -> None:
    """Replay git history commit-by-commit as an animated treemap."""
    import shutil
    import subprocess
    import tempfile
    from datetime import datetime

    if not shutil.which("git"):
        typer.echo(
            "Error: git not found on PATH.  Install it to use dirplot git:\n"
            "  macOS:  brew install git  (or install Xcode Command Line Tools)\n"
            "  Linux:  apt install git  /  dnf install git\n"
            "  Windows: https://git-scm.com/download/win",
            err=True,
        )
        raise typer.Exit(1)

    from dirplot.git_scanner import build_node_tree, git_apply_diff, git_initial_files, git_log

    last_dt: datetime | None = None
    if last is not None:
        try:
            last_dt = parse_last_period(last)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    _tmpdir: tempfile.TemporaryDirectory[str] | None = None
    _gh_owner: str | None = None
    _gh_repo_name: str | None = None
    _gh_ref: str | None = None
    _gh_token: str | None = None
    repo: Path
    if is_github_path(repo_arg):
        gh_owner, gh_repo_name, gh_ref, _ = parse_github_path(repo_arg)
        _gh_owner, _gh_repo_name, _gh_ref = gh_owner, gh_repo_name, gh_ref
        token = github_token or _gh_cli_token()
        _gh_token = token
        if token:
            clone_url = f"https://x-access-token:{token}@github.com/{gh_owner}/{gh_repo_name}.git"
        else:
            clone_url = f"https://github.com/{gh_owner}/{gh_repo_name}.git"
        _tmpdir = tempfile.TemporaryDirectory(prefix="dirplot-git-")
        # Clone into a subdirectory named after the repo so that repo.name
        # reflects the actual repository name (not the temp dir basename).
        _clone_dir = Path(_tmpdir.name) / gh_repo_name
        # Always clone with blobs so git ls-tree --long and git cat-file resolve
        # sizes locally (fast). Without blobs, git fetches each size lazily over
        # the network, which is slower than just cloning the objects upfront.
        clone_cmd = ["git", "clone", "--quiet"]
        if last_dt is not None:
            last_iso = last_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            clone_cmd += [f"--shallow-since={last_iso}"]
            if max_commits is not None:
                clone_cmd += ["--depth", str(max_commits)]
        elif max_commits is not None:
            clone_cmd += ["--depth", str(max_commits)]
        if gh_ref:
            clone_cmd += ["--branch", gh_ref]
        clone_cmd += [clone_url, str(_clone_dir)]
        typer.echo(f"Cloning github:{gh_owner}/{gh_repo_name} ...", err=True)
        try:
            subprocess.run(clone_cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            typer.echo(f"Error cloning repository: {exc.stderr.strip()}", err=True)
            raise typer.Exit(1) from exc
        repo = _clone_dir
    else:
        if "@" in repo_arg:
            repo_path_str, _, inline_ref = repo_arg.partition("@")
            if revision_range is None:
                revision_range = inline_ref
        else:
            repo_path_str = repo_arg
        repo = Path(repo_path_str).resolve()
        if not (repo / ".git").exists():
            typer.echo(f"Error: not a git repository: {repo}", err=True)
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
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px

    typer.echo(f"Reading git log from {repo} ...", err=True)
    _shallow_hint = ""
    if _tmpdir is not None and revision_range:
        if last_dt is not None and max_commits is not None:
            _shallow_hint = (
                "\nHint: --last controls the shallow clone cutoff date "
                "and --max-commits caps the commit count. "
                "If --range references a commit beyond that window, "
                "use a wider --last period or increase --max-commits."
            )
        elif last_dt is not None:
            _shallow_hint = (
                "\nHint: --last controls the shallow clone cutoff date. "
                "If --range references a commit beyond that window, "
                "use a wider --last period."
            )
        elif max_commits is not None:
            _shallow_hint = (
                "\nHint: --max-commits limits the shallow clone depth. "
                "If --range references a commit beyond that depth, "
                "increase --max-commits or drop it."
            )
    try:
        commits = git_log(repo, revision_range, max_commits, last_dt)
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Error reading git log: {exc.stderr.strip()}{_shallow_hint}", err=True)
        raise typer.Exit(1) from exc

    if not commits:
        typer.echo(f"No commits found.{_shallow_hint}", err=True)
        raise typer.Exit(1)

    # Show total commits on HEAD so the user knows how much history is available.
    # For shallow GitHub clones, git rev-list would only reflect the clone depth,
    # so we use the GitHub API instead (one cheap request).
    total_in_repo: int | None = None
    if _gh_owner is not None:
        total_in_repo = count_commits_github(_gh_owner, _gh_repo_name, _gh_ref, _gh_token)  # type: ignore[arg-type]
    else:
        try:
            _r = subprocess.run(
                ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            total_in_repo = int(_r.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            pass

    if total_in_repo is not None and total_in_repo > len(commits):
        _filters = []
        if last_dt is not None:
            _filters.append(f"--last {last}")
        if max_commits is not None:
            _filters.append(f"--max-commits {max_commits}")
        _filter_str = " and ".join(_filters) if _filters else "--max-commits"
        typer.echo(
            f"Replaying {len(commits)} of {total_in_repo} commit(s) "
            f"(filtered by {_filter_str}) ...",
            err=True,
        )
    else:
        typer.echo(f"Replaying {len(commits)} commit(s) ...", err=True)

    # Pre-compute per-commit frame durations.
    if total_duration is not None and animate:
        if total_duration <= 0:
            typer.echo("Error: --total-duration must be positive.", err=True)
            raise typer.Exit(1)
        timestamps = [ts for _, ts, _ in commits]
        # Gap for commit i = time until the next commit (i+1).
        # Last commit reuses the previous gap (or 1 if there is only one commit).
        gaps: list[float] = [
            max(1.0, float(timestamps[j + 1] - timestamps[j])) for j in range(len(timestamps) - 1)
        ]
        gaps.append(gaps[-1] if gaps else 1.0)
        total_ms = total_duration * 1000
        commit_durations = _proportional_durations(gaps, total_ms)
        min_d, max_d = min(commit_durations), max(commit_durations)
        typer.echo(
            f"  Proportional timing: {min_d}–{max_d} ms/frame"
            f" (total ~{sum(commit_durations) / 1000:.1f}s)",
            err=True,
        )
    else:
        commit_durations = [frame_duration] * len(commits)

    excluded = frozenset(exclude)
    files: dict[str, int] = {}
    prev_sha: str | None = None

    if animate:
        # ── Phase 1: fast sequential git pass ────────────────────────────────
        # Collect (files snapshot, highlights, deletions) per commit without
        # rendering.  Rendering is the bottleneck (~5 s/frame on a typical
        # repo); deferring it lets us parallelise across CPU cores in phase 2.
        # snapshot: (orig_i, sha, ts, files_copy, cur_highlights, deletions)
        Snapshot = tuple[int, str, int, dict[str, int], dict[str, str], dict[str, str]]
        snapshots: list[Snapshot] = []

        for i, (sha, ts, subject) in enumerate(commits):
            typer.echo(f"  [{i + 1}/{len(commits)}] {sha[:8]}  {subject[:72]}", err=True)
            try:
                if prev_sha is None:
                    files = git_initial_files(repo, sha, excluded)
                    all_hl: dict[str, str] = {}
                else:
                    all_hl = git_apply_diff(repo, files, prev_sha, sha, excluded)
            except subprocess.CalledProcessError as exc:
                typer.echo(f"  Warning: skipping {sha[:8]}: {exc.stderr.strip()}", err=True)
                prev_sha = sha
                continue
            prev_sha = sha
            deletions = {p: v for p, v in all_hl.items() if v == "deleted"}
            cur_hl = {p: v for p, v in all_hl.items() if v != "deleted"}
            snapshots.append((i, sha, ts, dict(files), cur_hl, deletions))

        if not snapshots:
            typer.echo("No frames captured.", err=True)
            raise typer.Exit(1)

        _run_vcs_animation(
            repo=repo,
            snapshots=snapshots,
            commit_durations=commit_durations,
            output=output,
            width_px=width_px,
            height_px=height_px,
            font_size=font_size,
            colormap=colormap,
            depth=depth,
            log_scale=log,
            cushion=cushion,
            dark=dark,
            workers=workers,
            crf=crf,
            codec=codec,
            fade_out=fade_out,
            fade_out_duration=fade_out_duration,
            fade_out_frames=fade_out_frames,
            fade_out_color=fade_out_color,
        )

    else:
        # ── Non-animate: render and overwrite output file per commit ──────────
        total_anim_ms = sum(commit_durations)
        cumulative_ms = 0.0

        for i, (sha, ts, subject) in enumerate(commits):
            typer.echo(f"  [{i + 1}/{len(commits)}] {sha[:8]}  {subject[:72]}", err=True)
            try:
                if prev_sha is None:
                    files = git_initial_files(repo, sha, excluded)
                    all_hl = {}
                else:
                    all_hl = git_apply_diff(repo, files, prev_sha, sha, excluded)
            except subprocess.CalledProcessError as exc:
                typer.echo(f"  Warning: skipping {sha[:8]}: {exc.stderr.strip()}", err=True)
                prev_sha = sha
                continue
            prev_sha = sha
            cumulative_ms += commit_durations[i]

            node = build_node_tree(repo, files, depth)
            if log:
                apply_log_sizes(node)

            deletions = {p: v for p, v in all_hl.items() if v == "deleted"}
            rect_map: dict[str, tuple[int, int, int, int]] = {}
            png_buf = create_treemap(
                node,
                width_px,
                height_px,
                font_size,
                colormap,
                None,
                cushion,
                highlights={p: v for p, v in all_hl.items() if v != "deleted"} or None,
                rect_map_out=rect_map,
                title_suffix=(
                    f"sha:{sha[:8]}  {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}"
                ),
                progress=cumulative_ms / total_anim_ms,
                dark=dark,
            )
            output.write_bytes(png_buf.read())
            typer.echo(f"  Updated {output}", err=True)


_HG_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot hg . -o history.apng --animate"
    "  [dim]# full history, APNG[/dim]\n\n"
    "  dirplot hg . -o history.mp4 --animate"
    "  [dim]# full history, MP4 (H.264, CRF 23)[/dim]\n\n"
    "  dirplot hg .@my-branch -o history.mp4 --animate"
    "  [dim]# specific revision range[/dim]\n\n"
    "  dirplot hg . -o history.mp4 --animate --last 30d"
    "  [dim]# last 30 days of changesets[/dim]"
)


@app.command(name="hg", epilog=_HG_EPILOG)
def hg_cmd(
    repo_arg: str = typer.Argument(
        ".",
        help="Mercurial repository path (optionally suffixed with @rev, e.g. .@tip)",
    ),
    output: Path = typer.Option(..., "--output", "-o", help="Output PNG file"),
    revision_range: str | None = typer.Option(
        None,
        "--range",
        "-r",
        help="Mercurial revision range (e.g. 0:tip).  Overrides @rev in the path.",
    ),
    max_commits: int | None = typer.Option(
        None, "--max-commits", "-n", help="Maximum number of changesets to process"
    ),
    last: str | None = typer.Option(
        None,
        "--last",
        help="Show changesets within a time period (e.g. 10d, 24h, 2w, 1mo). "
        "May be combined with --max-commits.",
        metavar="PERIOD",
    ),
    exclude: list[str] = typer.Option(
        [], "--exclude", "-e", help="Top-level paths to exclude (repeatable)"
    ),
    font_size: int = typer.Option(12, "--font-size", help="Directory label font size in pixels"),
    colormap: str = typer.Option("tab20", "--colormap", "-c", help="Matplotlib colormap"),
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
        help="Build an animated APNG or MP4 from all changesets",
    ),
    log: bool = typer.Option(False, "--log/--no-log", help="Use log of file sizes for layout"),
    depth: int | None = typer.Option(None, "--depth", help="Maximum directory depth"),
    frame_duration: int = typer.Option(
        1000,
        "--frame-duration",
        help="Frame display duration in ms when not using --total-duration",
    ),
    total_duration: float | None = typer.Option(
        None,
        "--total-duration",
        help=(
            "Target total animation length in seconds.  Frames are shown proportionally"
            " to the real time gaps between changesets.  Overrides --frame-duration."
        ),
    ),
    workers: int | None = typer.Option(
        None,
        "--workers",
        "-w",
        help="Parallel render workers for animate mode (default: all CPU cores).",
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
) -> None:
    """Replay Mercurial history changeset-by-changeset as an animated treemap."""
    import shutil
    import subprocess
    from datetime import datetime

    if not shutil.which("hg"):
        typer.echo(
            "Error: hg not found on PATH.  Install Mercurial to use dirplot hg:\n"
            "  macOS:  brew install mercurial\n"
            "  Linux:  apt install mercurial  /  dnf install mercurial\n"
            "  Windows: https://www.mercurial-scm.org/downloads",
            err=True,
        )
        raise typer.Exit(1)

    from dirplot.git_scanner import build_node_tree
    from dirplot.hg_scanner import hg_apply_diff, hg_initial_files, hg_log

    last_dt: datetime | None = None
    if last is not None:
        try:
            last_dt = parse_last_period(last)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    if "@" in repo_arg:
        repo_path_str, _, inline_ref = repo_arg.partition("@")
        if revision_range is None:
            revision_range = inline_ref
    else:
        repo_path_str = repo_arg
    repo = Path(repo_path_str).resolve()

    if not (repo / ".hg").exists():
        typer.echo(f"Error: not a Mercurial repository: {repo}", err=True)
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
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px

    typer.echo(f"Reading hg log from {repo} ...", err=True)
    try:
        commits = hg_log(repo, revision_range, max_commits, last_dt)
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Error reading hg log: {exc.stderr.strip()}", err=True)
        raise typer.Exit(1) from exc

    if not commits:
        typer.echo("No changesets found.", err=True)
        raise typer.Exit(1)

    try:
        _r = subprocess.run(
            ["hg", "log", "-R", str(repo), "--template", "x\n"],
            capture_output=True,
            text=True,
            check=True,
        )
        total_in_repo: int | None = _r.stdout.count("x")
    except (subprocess.CalledProcessError, ValueError):
        total_in_repo = None

    if total_in_repo is not None and total_in_repo > len(commits):
        _filters = []
        if last_dt is not None:
            _filters.append(f"--last {last}")
        if max_commits is not None:
            _filters.append(f"--max-commits {max_commits}")
        _filter_str = " and ".join(_filters) if _filters else "--max-commits"
        typer.echo(
            f"Replaying {len(commits)} of {total_in_repo} changeset(s) "
            f"(filtered by {_filter_str}) ...",
            err=True,
        )
    else:
        typer.echo(f"Replaying {len(commits)} changeset(s) ...", err=True)

    # Pre-compute per-changeset frame durations.
    if total_duration is not None and animate:
        if total_duration <= 0:
            typer.echo("Error: --total-duration must be positive.", err=True)
            raise typer.Exit(1)
        timestamps = [ts for _, ts, _ in commits]
        gaps: list[float] = [
            max(1.0, float(timestamps[j + 1] - timestamps[j])) for j in range(len(timestamps) - 1)
        ]
        gaps.append(gaps[-1] if gaps else 1.0)
        total_ms = total_duration * 1000
        commit_durations = _proportional_durations(gaps, total_ms)
        min_d, max_d = min(commit_durations), max(commit_durations)
        typer.echo(
            f"  Proportional timing: {min_d}–{max_d} ms/frame"
            f" (total ~{sum(commit_durations) / 1000:.1f}s)",
            err=True,
        )
    else:
        commit_durations = [frame_duration] * len(commits)

    excluded = frozenset(exclude)
    files: dict[str, int] = {}
    prev_node: str | None = None

    if animate:
        # ── Phase 1: fast sequential hg pass ─────────────────────────────────
        Snapshot = tuple[int, str, int, dict[str, int], dict[str, str], dict[str, str]]
        snapshots: list[Snapshot] = []

        for i, (node, ts, subject) in enumerate(commits):
            typer.echo(f"  [{i + 1}/{len(commits)}] {node[:8]}  {subject[:72]}", err=True)
            try:
                if prev_node is None:
                    files = hg_initial_files(repo, node, excluded)
                    all_hl: dict[str, str] = {}
                else:
                    all_hl = hg_apply_diff(repo, files, prev_node, node, excluded)
            except subprocess.CalledProcessError as exc:
                typer.echo(f"  Warning: skipping {node[:8]}: {exc.stderr.strip()}", err=True)
                prev_node = node
                continue
            prev_node = node
            deletions = {p: v for p, v in all_hl.items() if v == "deleted"}
            cur_hl = {p: v for p, v in all_hl.items() if v != "deleted"}
            snapshots.append((i, node, ts, dict(files), cur_hl, deletions))

        if not snapshots:
            typer.echo("No frames captured.", err=True)
            raise typer.Exit(1)

        _run_vcs_animation(
            repo=repo,
            snapshots=snapshots,
            commit_durations=commit_durations,
            output=output,
            width_px=width_px,
            height_px=height_px,
            font_size=font_size,
            colormap=colormap,
            depth=depth,
            log_scale=log,
            cushion=cushion,
            dark=dark,
            workers=workers,
            crf=crf,
            codec=codec,
            fade_out=fade_out,
            fade_out_duration=fade_out_duration,
            fade_out_frames=fade_out_frames,
            fade_out_color=fade_out_color,
        )

    else:
        # ── Non-animate: render and overwrite output file per changeset ───────
        total_anim_ms = sum(commit_durations)
        cumulative_ms = 0.0

        for i, (node, ts, subject) in enumerate(commits):
            typer.echo(f"  [{i + 1}/{len(commits)}] {node[:8]}  {subject[:72]}", err=True)
            try:
                if prev_node is None:
                    files = hg_initial_files(repo, node, excluded)
                    all_hl = {}
                else:
                    all_hl = hg_apply_diff(repo, files, prev_node, node, excluded)
            except subprocess.CalledProcessError as exc:
                typer.echo(f"  Warning: skipping {node[:8]}: {exc.stderr.strip()}", err=True)
                prev_node = node
                continue
            prev_node = node
            cumulative_ms += commit_durations[i]

            node_tree = build_node_tree(repo, files, depth)
            if log:
                apply_log_sizes(node_tree)

            rect_map: dict[str, tuple[int, int, int, int]] = {}
            png_buf = create_treemap(
                node_tree,
                width_px,
                height_px,
                font_size,
                colormap,
                None,
                cushion,
                highlights={p: v for p, v in all_hl.items() if v != "deleted"} or None,
                rect_map_out=rect_map,
                title_suffix=(
                    f"rev:{node[:8]}  {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}"
                ),
                progress=cumulative_ms / total_anim_ms,
                dark=dark,
            )
            output.write_bytes(png_buf.read())
            typer.echo(f"  Updated {output}", err=True)


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
    "  dirplot replay events.jsonl -o replay.mp4 --bucket 10"
    "  [dim]# finer-grained 10-second buckets[/dim]"
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
    font_size: int = typer.Option(12, "--font-size", help="Directory label font size in pixels"),
    colormap: str = typer.Option("tab20", "--colormap", "-c", help="Matplotlib colormap"),
    size: str | None = typer.Option(
        None, "--size", help="Output size as WIDTHxHEIGHT", metavar="WIDTHxHEIGHT"
    ),
    cushion: bool = typer.Option(True, "--cushion/--no-cushion", help="Apply cushion shading"),
    dark: bool = typer.Option(True, "--dark/--light", help="Dark background (default) or light"),
    log: bool = typer.Option(False, "--log/--no-log", help="Use log of file sizes for layout"),
    depth: int | None = typer.Option(None, "--depth", help="Maximum directory depth"),
    workers: int | None = typer.Option(
        None,
        "--workers",
        "-w",
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
) -> None:
    """Replay a JSONL filesystem event log as an animated treemap."""
    import io
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from dirplot.replay_scanner import (
        _render_replay_frame_worker,
        apply_events,
        bucket_events,
        parse_events,
    )

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
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px

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
    typer.echo(f"Common root: {common_root}", err=True)

    excluded = frozenset(Path(e).resolve() for e in exclude)

    # Build initial files dict by statting only paths that appear in the event log
    files: dict[str, int] = {}
    for _ts, _type, path_str, dest_str in events:
        for p_str in (path_str, dest_str) if dest_str else (path_str,):
            p = Path(p_str)
            if not p_str.startswith(str(common_root)):
                continue
            if p.resolve() in excluded or not p.is_file():
                continue
            try:
                rel = str(p.relative_to(common_root)).replace(os.sep, "/")
                files[rel] = max(1, p.stat().st_size)
            except (OSError, ValueError):
                pass
    typer.echo(f"  {len(files)} unique files from event log", err=True)

    buckets = bucket_events(events, bucket)
    typer.echo(
        f"Grouped {len(events)} events into {len(buckets)} frame(s) ({bucket:.0f}s buckets) ...",
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
        frame_durations = _proportional_durations(gaps, total_ms)
        min_d, max_d = min(frame_durations), max(frame_durations)
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
        snapshots.append((i, ts, dict(files), cur_hl, deletions))

    # Phase 2: parallel render
    total = len(snapshots)
    n_workers = min(workers if workers is not None else (os.cpu_count() or 1), total)
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
            log,
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
        with ProcessPoolExecutor(max_workers=n_workers, initializer=_worker_ignore_sigint) as pool:
            futures = {
                pool.submit(_render_replay_frame_worker, args): args[4] for args in render_args
            }
            for done, future in enumerate(as_completed(futures), 1):
                orig_i, png_bytes, rect_map = future.result()
                raw[orig_i] = (png_bytes, rect_map)
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

        fade_color = _resolve_fade_color(fade_out_color, dark)
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
    typer.echo(f"Wrote {len(frame_bytes)}-frame {output.suffix.upper()[1:]} → {output}", err=True)


@app.command(name="read-meta")
def read_meta(
    files: list[Path] = typer.Argument(
        ..., help="PNG, SVG, or MP4/MOV file(s) to read dirplot metadata from"
    ),
) -> None:
    """Read dirplot metadata embedded in one or more PNG, SVG, or MP4/MOV files."""
    any_error = False

    for file in files:
        if len(files) > 1:
            typer.echo(f"==> {file} <==")

        if not file.exists():
            typer.echo(f"Error: file not found: {file}", err=True)
            any_error = True
            continue

        suffix = file.suffix.lower()

        if suffix == ".png":
            from PIL import Image

            img = Image.open(file)
            info = img.info
            meta_keys = {"Date", "Software", "URL", "Python", "OS", "Command"}
            found = {k: v for k, v in info.items() if k in meta_keys}
            if not found:
                typer.echo("No dirplot metadata found in PNG.", err=True)
                any_error = True
                continue
            for k, v in found.items():
                typer.echo(f"{k}: {v}")

        elif suffix == ".svg":
            content = file.read_text(encoding="utf-8")
            try:
                root = ET.fromstring(content)
            except ET.ParseError as exc:
                typer.echo(f"Error parsing SVG: {exc}", err=True)
                any_error = True
                continue
            svg_meta: dict[str, str] = {}
            for desc in root.iter("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
                for child in desc:
                    local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    ns_uri = child.tag.split("}")[0].lstrip("{") if "}" in child.tag else ""
                    if ns_uri == "https://github.com/deeplook/dirplot#" and child.text:
                        svg_meta[local] = child.text
            if not svg_meta:
                typer.echo("No dirplot metadata found in SVG.", err=True)
                any_error = True
                continue
            for k, v in svg_meta.items():
                typer.echo(f"{k}: {v}")

        elif suffix in {".mp4", ".mov"}:
            import json
            import shutil
            import subprocess

            if not shutil.which("ffprobe"):
                typer.echo("Error: ffprobe not found on PATH (install ffmpeg).", err=True)
                any_error = True
                continue
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file)],
                capture_output=True,
            )
            if result.returncode != 0:
                typer.echo(
                    f"Error reading MP4 metadata: {result.stderr.decode(errors='replace')}",
                    err=True,
                )
                any_error = True
                continue
            tags = json.loads(result.stdout).get("format", {}).get("tags", {})
            meta_keys = {"Date", "Software", "URL", "Python", "OS", "Command"}
            found = {k: v for k, v in tags.items() if k in meta_keys}
            if not found:
                typer.echo("No dirplot metadata found in MP4.", err=True)
                any_error = True
                continue
            for k, v in found.items():
                typer.echo(f"{k}: {v}")

        else:
            typer.echo(
                f"Unsupported file type: {suffix!r}. Expected .png, .svg, or .mp4/.mov", err=True
            )
            any_error = True

    if any_error:
        raise typer.Exit(1)


@app.command(name="demo")
def demo_cmd(
    output: Path = typer.Option(
        Path("demo"), "--output", "-o", help="Folder for generated output files"
    ),
    github_url: str = typer.Option(
        "https://github.com/deeplook/dirplot",
        "--github-url",
        help="GitHub repository URL used for remote examples",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Ask for confirmation before each command is run"
    ),
) -> None:
    """Run a set of example commands to illustrate dirplot features."""
    import re
    import subprocess

    output.mkdir(parents=True, exist_ok=True)

    # Convert https://github.com/owner/repo → github://owner/repo
    m = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", github_url)
    gh_path = f"github://{m.group(1)}" if m else github_url

    base_cmd = [sys.executable, "-m", "dirplot"]

    examples: list[tuple[str, list[str]]] = [
        (
            "termsize — show current terminal dimensions",
            ["termsize"],
        ),
        (
            "map local directory (dark mode, PNG)",
            [
                "map",
                ".",
                "--no-show",
                "--output",
                str(output / "map-local.png"),
                "--size",
                "800x600",
            ],
        ),
        (
            "map github repo (dark mode, PNG)",
            [
                "map",
                gh_path,
                "--no-show",
                "--output",
                str(output / "map-github.png"),
                "--size",
                "800x600",
            ],
        ),
        (
            "map local directory (light mode, SVG)",
            [
                "map",
                ".",
                "--no-show",
                "--output",
                str(output / "map-local.svg"),
                "--size",
                "800x600",
                "--light",
            ],
        ),
        (
            "git — last 5 commits of github repo (static PNG)",
            [
                "git",
                gh_path,
                "--output",
                str(output / "git-static.png"),
                "--size",
                "800x600",
                "--max-commits",
                "5",
            ],
        ),
        (
            "git — last 10 commits of github repo (animated MP4)",
            [
                "git",
                gh_path,
                "--output",
                str(output / "git.mp4"),
                "--size",
                "800x600",
                "--max-commits",
                "10",
                "--animate",
                "--total-duration",
                "20",
            ],
        ),
        (
            "git — last 10 commits of github repo (animated PNG with fade-out)",
            [
                "git",
                gh_path,
                "--output",
                str(output / "git-animated.png"),
                "--size",
                "800x600",
                "--max-commits",
                "10",
                "--animate",
                "--total-duration",
                "20",
                "--fade-out",
            ],
        ),
        (
            "read-meta — metadata embedded in a generated PNG",
            ["read-meta", str(output / "map-local.png")],
        ),
    ]

    skipped = [
        ("watch", "interactive; watches a directory for changes indefinitely"),
        ("replay", "interactive; requires a JSONL event log produced by `watch --event-log`"),
    ]

    from rich.console import Console
    from rich.panel import Panel

    console = Console(highlight=False)

    console.print()
    console.print(
        Panel(
            f"[bold cyan]dirplot demo[/bold cyan]\n[dim]Outputs →[/dim] {output.resolve()}/",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    n_total = len(examples)
    for i, (label, args) in enumerate(examples, 1):
        cmd_display = "dirplot " + " ".join(args)
        console.print()
        console.rule(f"[bold]{i}/{n_total}[/bold]  {label}", style="cyan")
        console.print(f"  [dim]$[/dim] [bold cyan]{cmd_display}[/bold cyan]")
        console.print()

        if interactive:
            from rich.prompt import Confirm

            if not Confirm.ask("  Run this command?", default=True, console=console):
                console.print("  [yellow]⏭  Skipped[/yellow]")
                continue

        result = subprocess.run(base_cmd + args)

        console.print()
        if result.returncode == 0:
            console.print("  [bold green]✓  Done[/bold green]")
        else:
            console.print(f"  [bold red]✗  Exited with code {result.returncode}[/bold red]")

    console.print()
    console.rule(style="dim")
    for cmd_name, reason in skipped:
        console.print(f"  [dim]⏭  [bold]{cmd_name}[/bold]: {reason}[/dim]")

    console.print()
    console.print(
        Panel(
            f"[bold green]✓  Demo complete[/bold green]\n"
            f"[dim]Outputs saved to:[/dim] {output.resolve()}/",
            border_style="green",
            padding=(0, 2),
        )
    )


@app.command(name="map", epilog=_EPILOG)
def main(
    roots: list[str] = typer.Argument(
        default=None,
        help="Root(s) to map: one or more local directories (multiple → shows only those "
        "subtrees under their common parent), archive file, ssh://…, s3://…, "
        r"github://owner/repo\[@branch], https://github.com/owner/repo\[/tree/branch], "
        r"docker://container:/path, or pod://pod-name\[@namespace]/path. "
        "Omit to read paths from --paths-from or stdin (tree/find output).",
    ),
    paths_from: Path | None = typer.Option(
        None,
        "--paths-from",
        help="File containing a path list in tree or find output format. Use - for stdin.",
        metavar="FILE",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path (optional). Use .svg extension for SVG output. Use - for stdout.",
    ),
    fmt: str | None = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format: png or svg. Defaults to svg if --output ends in .svg, else png.",
        metavar="FORMAT",
    ),
    show: bool = typer.Option(True, "--show/--no-show", help="Display the image after rendering"),
    inline: bool = typer.Option(
        False,
        "--inline",
        help="Show in terminal (auto-detects iTerm2/Kitty protocol) instead of a separate window",
    ),
    legend: int | None = typer.Option(
        None,
        "--legend",
        help="Show file-count legend; value sets max entries shown (default: 20)",
        metavar="N",
    ),
    font_size: int = typer.Option(
        12, "--font-size", help="Directory label font size in pixels (default: 12)"
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
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    subtrees: list[str] = typer.Option(
        [],
        "--subtree",
        "-s",
        help=(
            "Show only this named direct child of the root (repeatable). "
            "Allowlist complement to --exclude: use when it is easier to name what you want."
        ),
    ),
    ssh_key: str | None = typer.Option(
        None, "--ssh-key", help="SSH private key file (default: ~/.ssh/id_rsa)"
    ),
    ssh_password: str | None = typer.Option(
        None, "--ssh-password", envvar="SSH_PASSWORD", help="SSH password"
    ),
    depth: int | None = typer.Option(
        None, "--depth", help="Maximum recursion depth (local and remote)"
    ),
    aws_profile: str | None = typer.Option(
        None, "--aws-profile", envvar="AWS_PROFILE", help="AWS profile name for S3 access"
    ),
    no_sign: bool = typer.Option(
        False, "--no-sign", help="Skip AWS signing for anonymous access to public S3 buckets"
    ),
    github_token: str | None = typer.Option(
        None, "--github-token", envvar="GITHUB_TOKEN", help="GitHub personal access token"
    ),
    k8s_namespace: str | None = typer.Option(
        None, "--k8s-namespace", "-N", help="Kubernetes namespace (overrides @namespace in pod URL)"
    ),
    k8s_container: str | None = typer.Option(
        None, "--k8s-container", help="Container name for multi-container pods"
    ),
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
    dark: bool = typer.Option(True, "--dark/--light", help="Dark background (default) or light"),
    log: bool = typer.Option(
        False,
        "--log/--no-log",
        help="Use log of file sizes for layout, making small files more visible.",
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        help="Password for encrypted archives. Prompted interactively if not supplied and needed.",
    ),
    breadcrumbs: bool = typer.Option(
        True,
        "--breadcrumbs/--no-breadcrumbs",
        "-b/-B",
        help=(
            "Collapse single-subdirectory chains into breadcrumb labels"
            " (e.g. foo / bar / baz). Default: on."
        ),
    ),
) -> None:
    """Create a nested treemap bitmap for a directory tree."""
    roots = roots or []
    to_stdout = output is not None and str(output) == "-"

    def _info(msg: str) -> None:
        typer.echo(msg, err=to_stdout)

    if colormap not in plt.colormaps():
        valid = ", ".join(sorted(plt.colormaps()))
        typer.echo(f"Unknown colormap '{colormap}'. Valid options:\n{valid}", err=True)
        raise typer.Exit(1)

    # Resolve path-list mode: --paths-from FILE or implicit stdin pipe
    use_stdin = paths_from is not None or (not roots and not sys.stdin.isatty())
    if use_stdin and roots:
        typer.echo(
            "Error: cannot combine positional paths with --paths-from / piped stdin.",
            err=True,
        )
        raise typer.Exit(1)

    root = roots[0] if len(roots) == 1 else ""  # alias for single-root branches
    _display_title: str | None = None  # used as prefix for the temp image filename
    t_scan_start = time.monotonic()
    if use_stdin:
        if paths_from is None or str(paths_from) == "-":
            raw = sys.stdin.read()
        else:
            if not paths_from.exists():
                typer.echo(f"Error: --paths-from path does not exist: {paths_from}", err=True)
                raise typer.Exit(1)
            raw = paths_from.read_text()
        parsed = parse_pathlist(raw.splitlines())
        if not parsed:
            typer.echo("Error: no paths found in path-list input.", err=True)
            raise typer.Exit(1)
        for p in parsed:
            if not p.exists():
                typer.echo(f"Path does not exist: {p}", err=True)
                raise typer.Exit(1)
        excluded = frozenset(Path(e).resolve() for e in exclude)
        root_paths = [p.resolve() for p in parsed]
        if header:
            import os

            common_str = os.path.commonpath([str(p) for p in root_paths])
            _info(f"Scanning {len(root_paths)} paths under {common_str} ...")
        root_node = build_tree_multi(root_paths, excluded, depth)
    elif not roots:
        typer.echo("Error: at least one path is required.", err=True)
        raise typer.Exit(1)
    elif len(roots) > 1:
        for r in roots:
            if any(
                f(r)
                for f in (
                    is_docker_path,
                    is_pod_path,
                    is_github_path,
                    is_s3_path,
                    is_ssh_path,
                    is_archive_path,
                )
            ):
                typer.echo(
                    f"Multiple roots are only supported for local paths, got: {r}",
                    err=True,
                )
                raise typer.Exit(1)
        root_paths = []
        for r in roots:
            rp = Path(r)
            if not rp.exists():
                typer.echo(f"Path does not exist: {r}", err=True)
                raise typer.Exit(1)
            if not rp.is_dir() and not rp.is_file():
                typer.echo(f"Not a file or directory: {r}", err=True)
                raise typer.Exit(1)
            root_paths.append(rp.resolve())
        excluded = frozenset(Path(e).resolve() for e in exclude)
        if header:
            import os

            common_str = os.path.commonpath([str(p) for p in root_paths])
            _info(f"Scanning {len(roots)} paths under {common_str} ...")
        root_node = build_tree_multi(root_paths, excluded, depth)
    elif is_docker_path(root):
        docker_container, docker_path = parse_docker_path(root)
        if header:
            _info(f"Scanning docker://{docker_container}:{docker_path} ...")
        progress = [0]
        try:
            root_node = build_tree_docker(
                docker_container,
                docker_path,
                exclude=frozenset(exclude),
                depth=depth,
                _progress=progress,
            )
        except (FileNotFoundError, OSError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_pod_path(root):
        pod_name, pod_ns, pod_path = parse_pod_path(root)
        namespace = k8s_namespace or pod_ns
        if header:
            ns_label = f"@{namespace}" if namespace else ""
            _info(f"Scanning pod://{pod_name}{ns_label}:{pod_path} ...")
        progress = [0]
        try:
            root_node = build_tree_pod(
                pod_name,
                pod_path,
                namespace=namespace,
                container=k8s_container,
                exclude=frozenset(exclude),
                depth=depth,
                _progress=progress,
            )
        except (FileNotFoundError, OSError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_github_path(root):
        gh_owner, gh_repo, gh_ref, gh_subpath = parse_github_path(root)
        _display_title = f"{gh_owner}-{gh_repo}"
        try:
            root_node, resolved_ref = build_tree_github(
                gh_owner,
                gh_repo,
                gh_ref,
                token=github_token,
                exclude=frozenset(exclude),
                depth=depth,
                subpath=gh_subpath,
            )
        except (PermissionError, FileNotFoundError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        if header:
            subpath_label = f"/{gh_subpath}" if gh_subpath else ""
            _info(f"Scanning github:{gh_owner}/{gh_repo}@{resolved_ref}{subpath_label} ...")
    elif is_s3_path(root):
        bucket, prefix = parse_s3_path(root)
        if header:
            _info(f"Scanning {root} ...")
        try:
            s3 = make_s3_client(profile=aws_profile, no_sign=no_sign)
        except ImportError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        progress = [0]
        root_node = build_tree_s3(
            s3,
            bucket,
            prefix,
            exclude=frozenset(exclude),
            depth=depth,
            _progress=progress,
        )
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_ssh_path(root):
        ssh_user, ssh_host, remote_path = parse_ssh_path(root)
        if header:
            _info(f"Scanning {root} ...")
        try:
            client = connect(ssh_host, ssh_user, ssh_key=ssh_key, ssh_password=ssh_password)
        except ImportError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        sftp = client.open_sftp()
        progress = [0]
        try:
            root_node = build_tree_ssh(
                sftp,
                remote_path,
                exclude=frozenset(exclude),
                depth=depth,
                _progress=progress,
            )
        finally:
            sftp.close()
            client.close()
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_archive_path(root):
        archive_path = Path(root)
        if not archive_path.exists():
            typer.echo(f"Path does not exist: {root}", err=True)
            raise typer.Exit(1)
        if not archive_path.is_file():
            typer.echo(f"Not a file: {root}", err=True)
            raise typer.Exit(1)
        if header:
            _info(f"Reading archive {root} ...")
        try:
            root_node = build_tree_archive(
                archive_path, exclude=frozenset(exclude), depth=depth, password=password
            )
        except PasswordRequired as exc:
            if password is not None:
                typer.echo("Error: incorrect password.", err=True)
                raise typer.Exit(1) from exc
            pw = typer.prompt("Password", hide_input=True)
            try:
                root_node = build_tree_archive(
                    archive_path, exclude=frozenset(exclude), depth=depth, password=pw
                )
            except PasswordRequired as exc2:
                typer.echo("Error: incorrect password.", err=True)
                raise typer.Exit(1) from exc2
        except (ImportError, OSError, RuntimeError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    else:
        root_path = Path(root)
        if not root_path.exists():
            typer.echo(f"Path does not exist: {root}", err=True)
            raise typer.Exit(1)
        if not root_path.is_dir():
            if not root_path.is_file():
                typer.echo(f"Not a file or directory: {root}", err=True)
                raise typer.Exit(1)
            rp = root_path.resolve()
            try:
                file_size = max(1, rp.stat().st_size)
            except OSError:
                file_size = 1
            ext = rp.suffix.lower() if rp.suffix else "(no ext)"
            file_node = Node(name=rp.name, path=rp, size=file_size, is_dir=False, extension=ext)
            root_node = Node(
                name=rp.parent.name,
                path=rp.parent,
                size=file_size,
                is_dir=True,
                children=[file_node],
            )
            if header:
                _info(f"Scanning {root} ...")
        else:
            excluded = frozenset(Path(e).resolve() for e in exclude)
            if header:
                _info(f"Scanning {root} ...")
            root_node = build_tree(root_path.resolve(), excluded, depth)

    if subtrees:
        root_node = prune_to_subtrees(root_node, set(subtrees))

    tree_depth = max_depth(root_node)

    if breadcrumbs:
        root_node = apply_breadcrumbs(root_node)

    t_scan = time.monotonic() - t_scan_start
    if log:
        apply_log_sizes(root_node)
    total_files = len(collect_extensions(root_node))
    if header:
        _f = "file" if total_files == 1 else "files"
        _info(f"Found {total_files:,} {_f}, total size: {root_node.size:,} bytes  [{t_scan:.1f}s]")

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
            _info(f"Output size: {width_px}x{height_px}px")
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px
        if header:
            _info(f"Terminal size: {width_px}x{height_px}px")

    # Resolve output format: explicit --format > inferred from --output extension > png
    if fmt is not None:
        if fmt not in ("png", "svg"):
            typer.echo(f"Unknown format '{fmt}'. Valid options: png, svg", err=True)
            raise typer.Exit(1)
        use_svg = fmt == "svg"
    elif output is not None and output.suffix.lower() == ".svg":
        use_svg = True
    else:
        use_svg = False

    t_render_start = time.monotonic()
    if use_svg:
        buf = create_treemap_svg(
            root_node, width_px, height_px, font_size, colormap, legend, cushion, tree_depth, dark
        )
    else:
        buf = create_treemap(
            root_node,
            width_px,
            height_px,
            font_size,
            colormap,
            legend,
            cushion,
            tree_depth,
            dark=dark,
        )
    t_render = time.monotonic() - t_render_start

    if output is not None:
        if to_stdout:
            sys.stdout.buffer.write(buf.read())
            buf.seek(0)
        else:
            output.write_bytes(buf.read())
            if header:
                _info(f"Saved dirplot to {output}  [{t_render:.1f}s]")
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
            display_window(buf, title=_display_title)


from dirplot._overview import add_overview_command  # noqa: E402

add_overview_command(app)

# Reorder help output regardless of definition order.
_CMD_ORDER = ["demo", "overview", "termsize", "map", "git", "hg", "watch", "replay", "read-meta"]
app.registered_commands.sort(key=lambda c: _CMD_ORDER.index(c.name or ""))
