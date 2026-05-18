"""The ``git`` and ``hg`` commands: replay VCS history as an animated treemap."""

import io
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.defaults import DEFAULT_COLORMAP, DEFAULT_FONT_SIZE
from dirplot.display import display_inline
from dirplot.helpers.animation import (
    proportional_durations,
    resolve_fade_color,
    worker_ignore_sigint,
)
from dirplot.helpers.highlights import resolve_highlight_specs
from dirplot.helpers.time import parse_last_period
from dirplot.scanner import apply_log_sizes
from dirplot.terminal import default_canvas_size, get_terminal_size

_GIT_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot git . --inline"
    "  [dim]# snapshot of HEAD, inline in terminal[/dim]\n\n"
    "  dirplot git . -o snapshot.png"
    "  [dim]# snapshot of HEAD, saved to file[/dim]\n\n"
    "  dirplot git .@my-branch -o snapshot.png"
    "  [dim]# snapshot of tip of a branch[/dim]\n\n"
    "  dirplot git . -o history.png --range v1.0..HEAD"
    "  [dim]# animate a revision range (APNG)[/dim]\n\n"
    "  dirplot git . -o history.mp4 --range v1.0..HEAD"
    "  [dim]# animate a revision range (MP4)[/dim]\n\n"
    "  dirplot git . -o history.mp4 --period 30d"
    "  [dim]# animate last 30 days of commits[/dim]\n\n"
    "  dirplot git . -o history.mp4 --period 30d --last 20"
    "  [dim]# last 20 commits within that period[/dim]\n\n"
    "  dirplot git github://owner/repo -o history.mp4 --period 90d --first 50"
    "  [dim]# GitHub repo, first 50 commits in period[/dim]"
)

_HG_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot hg . --inline"
    "  [dim]# snapshot of tip, inline in terminal[/dim]\n\n"
    "  dirplot hg . -o snapshot.png"
    "  [dim]# snapshot of tip, saved to file[/dim]\n\n"
    "  dirplot hg .@my-branch -o snapshot.png"
    "  [dim]# snapshot of tip of a branch[/dim]\n\n"
    "  dirplot hg . -o history.png --range 0:tip"
    "  [dim]# animate full history (APNG)[/dim]\n\n"
    "  dirplot hg . -o history.mp4 --period 30d"
    "  [dim]# animate last 30 days of changesets[/dim]\n\n"
    "  dirplot hg . -o history.mp4 --period 30d --last 20 --total-duration 30"
    "  [dim]# last 20 changesets, proportional timing[/dim]"
)


def run_vcs_animation(
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
    logscale: float,
    cushion: bool,
    dark: bool,
    workers: int | None,
    crf: int,
    codec: str,
    fade_out: bool,
    fade_out_duration: float,
    fade_out_frames: int | None,
    fade_out_color: str,
    quiet: bool = False,
) -> None:
    """Render *snapshots* to an animated APNG or MP4 at *output*.

    Phases 2–4 of the VCS animation pipeline: parallel frame rendering,
    deletion-highlight patching, and output writing.  Shared by ``git_cmd``
    and ``hg_cmd``; the VCS-specific Phase 1 (collecting snapshots) is
    handled by each command.
    """
    from dirplot.git_scanner import _render_frame_worker
    from dirplot.render_png import _draw_highlights

    # ── Phase 2: parallel render ──────────────────────────────────────────
    if workers is not None and workers <= 0:
        typer.echo("Error: --workers must be a positive integer.", err=True)
        raise typer.Exit(1)

    total = len(snapshots)
    n_workers = min(workers if workers is not None else (os.cpu_count() or 1), total)
    if not quiet:
        typer.echo(f"Rendering {total} frame(s) using {n_workers} worker(s) ...", err=True)

    # Per-frame progress: fraction of total animation time elapsed after each frame plays.
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
            logscale,
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
        with ProcessPoolExecutor(max_workers=n_workers, initializer=worker_ignore_sigint) as pool:
            futures = {pool.submit(_render_frame_worker, args): args[5] for args in render_args}
            for done, future in enumerate(as_completed(futures), 1):
                orig_i, png_bytes, rect_map = future.result()
                raw[orig_i] = (png_bytes, rect_map)
                if not quiet:
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

        fade_color = resolve_fade_color(fade_out_color, dark)
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
    if not quiet:
        typer.echo(f"Wrote {len(frame_bytes)}-frame {fmt} → {output}", err=True)


@app.command(name="git", epilog=_GIT_EPILOG)
def git_cmd(
    repo_arg: str = typer.Argument(
        ".",
        help=(
            "Git repository path (optionally suffixed with @ref, e.g. .@my-branch),"
            " github://owner/repo[@branch], or https://github.com/owner/repo[@ref]"
        ),
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output file (.png or .mp4/.mov for animations)"
    ),
    revision_range: str | None = typer.Option(
        None,
        "--range",
        help=(
            "Git revision range to animate (e.g. v1.0..HEAD). "
            "Triggers animation mode. "
            "When using a GitHub URL with --first, "
            "ensure the clone depth covers the range's base commit."
        ),
    ),
    period: str | None = typer.Option(
        None,
        "--period",
        help="Time window to animate (e.g. 30d, 24h, 2w, 1mo). Triggers animation mode.",
        metavar="PERIOD",
    ),
    first: int | None = typer.Option(
        None, "--first", help="Take only the first N commits of the range (animation mode only)"
    ),
    last: int | None = typer.Option(
        None, "--last", help="Take only the last N commits of the range (animation mode only)"
    ),
    exclude: list[str] = typer.Option(
        [], "--exclude", "-e", help="Top-level paths to exclude (repeatable)"
    ),
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
    inline: bool = typer.Option(
        False,
        "--inline",
        help="Display snapshot inline in the terminal (iTerm2/Kitty/Ghostty). Single-frame mode only.",  # noqa: E501
    ),
    logscale: float = typer.Option(
        0.0,
        "--log-scale",
        help="Log-scale compression ratio (max/min ratio). 0 disables; must be > 1 to enable.",
        show_default=True,
    ),
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
        help="Parallel render workers (default: all CPU cores).  "
        "Rendering is memory-bandwidth bound, so the optimal value depends on your hardware; "
        "try --workers 4-8 if the default is slower than expected.",
    ),
    crf: int = typer.Option(
        23,
        "--crf",
        help="MP4 quality: Constant Rate Factor (0=lossless, 51=worst; default 23).",
        show_default=True,
    ),
    codec: str = typer.Option(
        "libx264",
        "--codec",
        help="MP4 video codec: libx264 (H.264, default) or libx265 (H.265, smaller files).",
    ),
    github_token_file: Path | None = typer.Option(
        None,
        "--github-token-file",
        help="File containing a GitHub personal access token (avoids exposing the token in shell history).",  # noqa: E501
        metavar="FILE",
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
            "'transparent' (PNG/APNG only), a CSS colour name, or a hex code"
        ),
        metavar="COLOR",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
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
) -> None:
    """Render a git repo as a treemap snapshot or animate a commit range.

    Without --range or --period: renders a single snapshot of the last commit
    (HEAD, or the tip of the branch/tag given via @ref).  Use --inline to display
    it directly in the terminal, or --output to save it as a PNG.

    With --range or --period: produces an animation (PNG/APNG or MP4) of the
    matching commits.  --first N and --last N slice the commit list.
    """
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
    from dirplot.github import (
        _gh_cli_token,
        count_commits_github,
        is_github_path,
        parse_github_path,
    )

    is_animation = revision_range is not None or period is not None

    if inline and is_animation:
        typer.echo(
            "Error: --inline is only available in single-frame mode (no --range or --period).",
            err=True,
        )
        raise typer.Exit(1)
    if not inline and output is None:
        typer.echo("Error: --output is required unless --inline is given.", err=True)
        raise typer.Exit(1)
    if (first is not None or last is not None) and not is_animation:
        typer.echo("Error: --first and --last require --range or --period.", err=True)
        raise typer.Exit(1)
    if first is not None and last is not None:
        typer.echo("Error: --first and --last are mutually exclusive.", err=True)
        raise typer.Exit(1)

    if size is not None:
        try:
            _w, _h = (int(p) for p in size.lower().split("x", 1))
        except ValueError:
            _w, _h = 0, 0
        if _w == 0 or _h == 0:
            typer.echo(
                f"Invalid --size '{size}': width and height must both be positive.", err=True
            )
            raise typer.Exit(1)

    if output is not None:
        if is_animation and output.suffix.lower() not in {".png", ".mp4", ".mov"}:
            typer.echo(
                "Error: animation --output must be a .png (APNG), .mp4, or .mov file.", err=True
            )
            raise typer.Exit(1)
        if not is_animation and output.suffix.lower() != ".png":
            typer.echo("Error: snapshot --output must be a .png file.", err=True)
            raise typer.Exit(1)

    period_dt: datetime | None = None
    if period is not None:
        try:
            period_dt = parse_last_period(period)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    github_token: str | None = os.environ.get("GITHUB_TOKEN")
    _tmpdir: tempfile.TemporaryDirectory[str] | None = None
    _gh_owner: str | None = None
    _gh_repo_name: str | None = None
    _gh_ref: str | None = None
    _gh_token: str | None = None
    _at_ref: str | None = None
    repo: Path
    if github_token_file is not None:
        if not github_token_file.exists():
            typer.echo(f"Error: --github-token-file not found: {github_token_file}", err=True)
            raise typer.Exit(1)
        github_token = github_token_file.read_text().strip()

    if is_github_path(repo_arg):
        gh_owner, gh_repo_name, gh_ref, _ = parse_github_path(repo_arg)
        _gh_owner, _gh_repo_name, _gh_ref = gh_owner, gh_repo_name, gh_ref
        _at_ref = gh_ref
        token = github_token or _gh_cli_token()
        _gh_token = token
        clone_url = f"https://github.com/{gh_owner}/{gh_repo_name}.git"
        _tmpdir = tempfile.TemporaryDirectory(prefix="dirplot-git-")
        # Clone into a subdirectory named after the repo so that repo.name
        # reflects the actual repository name (not the temp dir basename).
        _clone_dir = Path(_tmpdir.name) / gh_repo_name
        clone_env = None
        if token:
            askpass = Path(_tmpdir.name) / "git-askpass.py"
            askpass.write_text(
                "import os, sys\n"
                "prompt = sys.argv[1] if len(sys.argv) > 1 else ''\n"
                "if 'username' in prompt.lower():\n"
                "    print('x-access-token')\n"
                "else:\n"
                "    print(os.environ['DIRPLOT_GITHUB_TOKEN'])\n",
                encoding="utf-8",
            )
            askpass.chmod(0o700)
            clone_env = {
                **os.environ,
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
                "DIRPLOT_GITHUB_TOKEN": token,
            }
        # Always clone with blobs so git ls-tree --long and git cat-file resolve
        # sizes locally (fast). Without blobs, git fetches each size lazily over
        # the network, which is slower than just cloning the objects upfront.
        clone_cmd = ["git", "-c", "credential.helper=", "clone", "--quiet"]
        if period_dt is not None and revision_range is None:
            # --period without --range: use as shallow-since cutoff.
            # With --range the clone must fetch enough history to resolve both
            # range endpoints, so we skip shallow cloning entirely.
            period_iso = period_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            clone_cmd += [f"--shallow-since={period_iso}"]
        elif first is not None and revision_range is None:
            clone_cmd += ["--depth", str(first)]
        if gh_ref:
            clone_cmd += ["--branch", gh_ref]
        clone_cmd += [clone_url, str(_clone_dir)]
        if not quiet:
            typer.echo(f"Cloning github:{gh_owner}/{gh_repo_name} ...", err=True)
        try:
            subprocess.run(clone_cmd, check=True, capture_output=True, text=True, env=clone_env)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip()
            if token:
                stderr = stderr.replace(token, "<redacted>")
            typer.echo(f"Error cloning repository: {stderr}", err=True)
            raise typer.Exit(1) from exc
        repo = _clone_dir
    else:
        if "@" in repo_arg:
            repo_path_str, _, _at_ref = repo_arg.partition("@")
        else:
            repo_path_str = repo_arg
        repo = Path(repo_path_str).resolve()
        if not (repo / ".git").exists():
            typer.echo(f"Error: not a git repository: {repo}", err=True)
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

    inline_cols: int | None = None
    if inline and size is None:
        inline_cols, *_ = get_terminal_size()

    if not quiet:
        typer.echo(f"Reading git log from {repo} ...", err=True)

    _shallow_hint = ""
    if _tmpdir is not None and revision_range and period_dt is not None:
        _shallow_hint = (
            "\nHint: --period controls the shallow clone cutoff date. "
            "If --range references a commit beyond that window, "
            "use a wider --period."
        )

    # In single-frame mode, fetch only the last commit at the ref (or HEAD).
    _log_range = revision_range if is_animation else _at_ref
    # When --range + --period: fetch all range commits first, then filter by
    # period relative to the range end.  Without --range, pass period_dt to
    # git_log so it uses --after (anchored to now).
    _period_for_log = period_dt if revision_range is None else None
    try:
        commits = git_log(repo, _log_range, None, _period_for_log)
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Error reading git log: {exc.stderr.strip()}{_shallow_hint}", err=True)
        raise typer.Exit(1) from exc

    if not commits:
        typer.echo(f"No commits found.{_shallow_hint}", err=True)
        raise typer.Exit(1)

    # When --range + --period: filter to commits within period of the range end.
    if is_animation and revision_range is not None and period_dt is not None:
        from datetime import datetime, timezone

        period_seconds = (datetime.now(tz=timezone.utc) - period_dt).total_seconds()
        cutoff_ts = commits[-1][1] - period_seconds
        commits = [c for c in commits if c[1] >= cutoff_ts]
        if not commits:
            typer.echo("No commits found within --period of the range end.", err=True)
            raise typer.Exit(1)

    # Apply --first / --last slicing after fetching (git log --reverse -n N gives
    # newest commits, not oldest, so we must slice in Python instead).
    if is_animation:
        if first is not None:
            commits = commits[:first]
        elif last is not None:
            commits = commits[-last:]
    else:
        commits = commits[-1:]

    # Show total commits on HEAD so the user knows how much history is available.
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

    if not quiet:
        if is_animation:
            if total_in_repo is not None and total_in_repo > len(commits):
                _filters = []
                if period_dt is not None:
                    _filters.append(f"--period {period}")
                if first is not None:
                    _filters.append(f"--first {first}")
                if last is not None:
                    _filters.append(f"--last {last}")
                _filter_str = " and ".join(_filters) if _filters else "filters"
                typer.echo(
                    f"Animating {len(commits)} of {total_in_repo} commit(s) "
                    f"(filtered by {_filter_str}) ...",
                    err=True,
                )
            else:
                typer.echo(f"Animating {len(commits)} commit(s) ...", err=True)
        else:
            sha, ts, subject = commits[-1]
            typer.echo(
                f"Rendering snapshot: {sha[:8]}  {subject[:72]}",
                err=True,
            )

    excluded = frozenset(exclude)
    files: dict[str, int] = {}
    prev_sha: str | None = None

    if is_animation:
        # Pre-compute per-commit frame durations.
        if total_duration is not None:
            if total_duration <= 0:
                typer.echo("Error: --total-duration must be positive.", err=True)
                raise typer.Exit(1)
            timestamps = [ts for _, ts, _ in commits]
            gaps: list[float] = [
                max(1.0, float(timestamps[j + 1] - timestamps[j]))
                for j in range(len(timestamps) - 1)
            ]
            gaps.append(gaps[-1] if gaps else 1.0)
            total_ms = total_duration * 1000
            commit_durations = proportional_durations(gaps, total_ms)
            min_d, max_d = min(commit_durations), max(commit_durations)
            if not quiet:
                typer.echo(
                    f"  Proportional timing: {min_d}–{max_d} ms/frame"
                    f" (total ~{sum(commit_durations) / 1000:.1f}s)",
                    err=True,
                )
        else:
            commit_durations = [frame_duration] * len(commits)

        # ── Phase 1: fast sequential git pass ────────────────────────────────
        Snapshot = tuple[int, str, int, dict[str, int], dict[str, str], dict[str, str]]
        snapshots: list[Snapshot] = []

        for i, (sha, ts, subject) in enumerate(commits):
            if not quiet:
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

        if highlight:
            for _idx, _sha, _ts, files_copy, cur_hl, _deletions in snapshots:
                abs_paths = [(repo / rel).as_posix() for rel in files_copy]
                cur_hl.update(resolve_highlight_specs(highlight, abs_paths))

        assert output is not None
        run_vcs_animation(
            repo=repo,
            snapshots=snapshots,
            commit_durations=commit_durations,
            output=output,
            width_px=width_px,
            height_px=height_px,
            font_size=font_size,
            colormap=colormap,
            depth=depth,
            logscale=logscale,
            cushion=cushion,
            dark=dark,
            workers=workers,
            crf=crf,
            codec=codec,
            fade_out=fade_out,
            fade_out_duration=fade_out_duration,
            fade_out_frames=fade_out_frames,
            fade_out_color=fade_out_color,
            quiet=quiet,
        )

    else:
        # ── Single frame: render the last commit ──────────────────────────────
        sha, ts, subject = commits[-1]
        try:
            files = git_initial_files(repo, sha, excluded)
        except subprocess.CalledProcessError as exc:
            typer.echo(f"Error reading commit {sha[:8]}: {exc.stderr.strip()}", err=True)
            raise typer.Exit(1) from exc

        node = build_node_tree(repo, files, depth)
        if logscale > 1:
            apply_log_sizes(node, logscale)

        from dirplot.render_png import create_treemap

        hl: dict[str, str] | None = None
        if highlight:
            abs_paths = [(repo / rel).as_posix() for rel in files]
            hl = resolve_highlight_specs(highlight, abs_paths)

        png_buf = create_treemap(
            node,
            width_px,
            height_px,
            font_size,
            colormap,
            None,
            cushion,
            title_suffix=f"sha:{sha[:8]}  {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}",
            dark=dark,
            logscale=logscale,
            highlights=hl,
        )
        if inline:
            display_inline(png_buf, cols=inline_cols)
        else:
            assert output is not None
            output.write_bytes(png_buf.read())
            if not quiet:
                typer.echo(f"Wrote {output}", err=True)


@app.command(name="hg", epilog=_HG_EPILOG)
def hg_cmd(
    repo_arg: str = typer.Argument(
        ".",
        help="Mercurial repository path (optionally suffixed with @rev, e.g. .@tip)",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output file (.png or .mp4/.mov for animations)"
    ),
    revision_range: str | None = typer.Option(
        None,
        "--range",
        help="Mercurial revision range to animate (e.g. 0:tip). Triggers animation mode.",
    ),
    period: str | None = typer.Option(
        None,
        "--period",
        help="Time window to animate (e.g. 30d, 24h, 2w, 1mo). Triggers animation mode.",
        metavar="PERIOD",
    ),
    first: int | None = typer.Option(
        None, "--first", help="Take only the first N changesets of the range (animation mode only)"
    ),
    last: int | None = typer.Option(
        None, "--last", help="Take only the last N changesets of the range (animation mode only)"
    ),
    exclude: list[str] = typer.Option(
        [], "--exclude", "-e", help="Top-level paths to exclude (repeatable)"
    ),
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
    inline: bool = typer.Option(
        False,
        "--inline",
        help="Display snapshot inline in the terminal (iTerm2/Kitty/Ghostty). Single-frame mode only.",  # noqa: E501
    ),
    logscale: float = typer.Option(
        0.0,
        "--log-scale",
        help="Log-scale compression ratio (max/min ratio). 0 disables; must be > 1 to enable.",
        show_default=True,
    ),
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
        help="Parallel render workers (default: all CPU cores).",
    ),
    crf: int = typer.Option(
        23,
        "--crf",
        help="MP4 quality: Constant Rate Factor (0=lossless, 51=worst; default 23).",
        show_default=True,
    ),
    codec: str = typer.Option(
        "libx264",
        "--codec",
        help="MP4 video codec: libx264 (H.264, default) or libx265 (H.265, smaller files).",
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
            "'transparent' (PNG/APNG only), a CSS colour name, or a hex code"
        ),
        metavar="COLOR",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
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
) -> None:
    """Render a Mercurial repo as a treemap snapshot or animate a changeset range.

    Without --range or --period: renders a single snapshot of the tip (or the
    tip of the branch/rev given via @ref).  Use --inline to display it directly
    in the terminal, or --output to save it as a PNG.

    With --range or --period: produces an animation (PNG/APNG or MP4) of the
    matching changesets.  --first N and --last N slice the changeset list.
    """
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

    is_animation = revision_range is not None or period is not None

    if inline and is_animation:
        typer.echo(
            "Error: --inline is only available in single-frame mode (no --range or --period).",
            err=True,
        )
        raise typer.Exit(1)
    if not inline and output is None:
        typer.echo("Error: --output is required unless --inline is given.", err=True)
        raise typer.Exit(1)
    if (first is not None or last is not None) and not is_animation:
        typer.echo("Error: --first and --last require --range or --period.", err=True)
        raise typer.Exit(1)
    if first is not None and last is not None:
        typer.echo("Error: --first and --last are mutually exclusive.", err=True)
        raise typer.Exit(1)

    if size is not None:
        try:
            _w, _h = (int(p) for p in size.lower().split("x", 1))
        except ValueError:
            _w, _h = 0, 0
        if _w == 0 or _h == 0:
            typer.echo(
                f"Invalid --size '{size}': width and height must both be positive.", err=True
            )
            raise typer.Exit(1)

    if output is not None:
        if is_animation and output.suffix.lower() not in {".png", ".mp4", ".mov"}:
            typer.echo(
                "Error: animation --output must be a .png (APNG), .mp4, or .mov file.", err=True
            )
            raise typer.Exit(1)
        if not is_animation and output.suffix.lower() != ".png":
            typer.echo("Error: snapshot --output must be a .png file.", err=True)
            raise typer.Exit(1)

    period_dt: datetime | None = None
    if period is not None:
        try:
            period_dt = parse_last_period(period)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    _at_ref: str | None = None
    if "@" in repo_arg:
        repo_path_str, _, _at_ref = repo_arg.partition("@")
    else:
        repo_path_str = repo_arg
    repo = Path(repo_path_str).resolve()

    if not (repo / ".hg").exists():
        typer.echo(f"Error: not a Mercurial repository: {repo}", err=True)
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

    inline_cols: int | None = None
    if inline and size is None:
        inline_cols, *_ = get_terminal_size()

    if not quiet:
        typer.echo(f"Reading hg log from {repo} ...", err=True)

    _log_range = revision_range if is_animation else _at_ref
    _period_for_log = period_dt if revision_range is None else None
    try:
        commits = hg_log(repo, _log_range, None, _period_for_log)
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Error reading hg log: {exc.stderr.strip()}", err=True)
        raise typer.Exit(1) from exc

    if not commits:
        typer.echo("No changesets found.", err=True)
        raise typer.Exit(1)

    # When --range + --period: filter to changesets within period of the range end.
    if is_animation and revision_range is not None and period_dt is not None:
        from datetime import datetime, timezone

        period_seconds = (datetime.now(tz=timezone.utc) - period_dt).total_seconds()
        cutoff_ts = commits[-1][1] - period_seconds
        commits = [c for c in commits if c[1] >= cutoff_ts]
        if not commits:
            typer.echo("No changesets found within --period of the range end.", err=True)
            raise typer.Exit(1)

    # Apply --first / --last slicing after fetching (hg log --limit N gives
    # newest changesets, not oldest, so we must slice in Python instead).
    if is_animation:
        if first is not None:
            commits = commits[:first]
        elif last is not None:
            commits = commits[-last:]
    else:
        commits = commits[-1:]

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

    if not quiet:
        if is_animation:
            if total_in_repo is not None and total_in_repo > len(commits):
                _filters = []
                if period_dt is not None:
                    _filters.append(f"--period {period}")
                if first is not None:
                    _filters.append(f"--first {first}")
                if last is not None:
                    _filters.append(f"--last {last}")
                _filter_str = " and ".join(_filters) if _filters else "filters"
                typer.echo(
                    f"Animating {len(commits)} of {total_in_repo} changeset(s) "
                    f"(filtered by {_filter_str}) ...",
                    err=True,
                )
            else:
                typer.echo(f"Animating {len(commits)} changeset(s) ...", err=True)
        else:
            node_id, ts, subject = commits[-1]
            typer.echo(
                f"Rendering snapshot: {node_id[:8]}  {subject[:72]}",
                err=True,
            )

    excluded = frozenset(exclude)
    files: dict[str, int] = {}
    prev_node: str | None = None

    if is_animation:
        # Pre-compute per-changeset frame durations.
        if total_duration is not None:
            if total_duration <= 0:
                typer.echo("Error: --total-duration must be positive.", err=True)
                raise typer.Exit(1)
            timestamps = [ts for _, ts, _ in commits]
            gaps: list[float] = [
                max(1.0, float(timestamps[j + 1] - timestamps[j]))
                for j in range(len(timestamps) - 1)
            ]
            gaps.append(gaps[-1] if gaps else 1.0)
            total_ms = total_duration * 1000
            commit_durations = proportional_durations(gaps, total_ms)
            min_d, max_d = min(commit_durations), max(commit_durations)
            if not quiet:
                typer.echo(
                    f"  Proportional timing: {min_d}–{max_d} ms/frame"
                    f" (total ~{sum(commit_durations) / 1000:.1f}s)",
                    err=True,
                )
        else:
            commit_durations = [frame_duration] * len(commits)

        # ── Phase 1: fast sequential hg pass ─────────────────────────────────
        Snapshot = tuple[int, str, int, dict[str, int], dict[str, str], dict[str, str]]
        snapshots: list[Snapshot] = []

        for i, (node_id, ts, subject) in enumerate(commits):
            if not quiet:
                typer.echo(f"  [{i + 1}/{len(commits)}] {node_id[:8]}  {subject[:72]}", err=True)
            try:
                if prev_node is None:
                    files = hg_initial_files(repo, node_id, excluded)
                    all_hl: dict[str, str] = {}
                else:
                    all_hl = hg_apply_diff(repo, files, prev_node, node_id, excluded)
            except subprocess.CalledProcessError as exc:
                typer.echo(f"  Warning: skipping {node_id[:8]}: {exc.stderr.strip()}", err=True)
                prev_node = node_id
                continue
            prev_node = node_id
            deletions = {p: v for p, v in all_hl.items() if v == "deleted"}
            cur_hl = {p: v for p, v in all_hl.items() if v != "deleted"}
            snapshots.append((i, node_id, ts, dict(files), cur_hl, deletions))

        if not snapshots:
            typer.echo("No frames captured.", err=True)
            raise typer.Exit(1)

        if highlight:
            for _idx, _nid, _ts, files_copy, cur_hl, _deletions in snapshots:
                abs_paths = [(repo / rel).as_posix() for rel in files_copy]
                cur_hl.update(resolve_highlight_specs(highlight, abs_paths))

        assert output is not None
        run_vcs_animation(
            repo=repo,
            snapshots=snapshots,
            commit_durations=commit_durations,
            output=output,
            width_px=width_px,
            height_px=height_px,
            font_size=font_size,
            colormap=colormap,
            depth=depth,
            logscale=logscale,
            cushion=cushion,
            dark=dark,
            workers=workers,
            crf=crf,
            codec=codec,
            fade_out=fade_out,
            fade_out_duration=fade_out_duration,
            fade_out_frames=fade_out_frames,
            fade_out_color=fade_out_color,
            quiet=quiet,
        )

    else:
        # ── Single frame: render the last changeset ───────────────────────────
        node_id, ts, subject = commits[-1]
        try:
            files = hg_initial_files(repo, node_id, excluded)
        except subprocess.CalledProcessError as exc:
            typer.echo(f"Error reading changeset {node_id[:8]}: {exc.stderr.strip()}", err=True)
            raise typer.Exit(1) from exc

        node_tree = build_node_tree(repo, files, depth)
        if logscale > 1:
            apply_log_sizes(node_tree, logscale)

        from dirplot.render_png import create_treemap

        hl_hg: dict[str, str] | None = None
        if highlight:
            abs_paths = [(repo / rel).as_posix() for rel in files]
            hl_hg = resolve_highlight_specs(highlight, abs_paths)

        png_buf = create_treemap(
            node_tree,
            width_px,
            height_px,
            font_size,
            colormap,
            None,
            cushion,
            title_suffix=f"rev:{node_id[:8]}  {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}",  # noqa: E501
            dark=dark,
            logscale=logscale,
            highlights=hl_hg,
        )
        if inline:
            display_inline(png_buf, cols=inline_cols)
        else:
            assert output is not None
            output.write_bytes(png_buf.read())
            if not quiet:
                typer.echo(f"Wrote {output}", err=True)
