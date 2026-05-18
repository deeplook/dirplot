"""Shared animation utilities: frame timing, fade colours, worker init."""

import signal

import typer


def worker_ignore_sigint() -> None:
    """Initializer for ProcessPoolExecutor workers: ignore SIGINT so Ctrl-C is
    handled only by the main process and workers exit cleanly on shutdown."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def proportional_durations(gaps: list[float], total_ms: float, floor_ms: int = 200) -> list[int]:
    """Convert time *gaps* into integer frame durations that sum to *total_ms*.

    Each frame gets a duration proportional to its gap.  Frames whose
    proportional share would fall below *floor_ms* are raised to that floor;
    the remaining frames are scaled down so the total still equals *total_ms*.
    A final rounding correction is applied to the longest frame so the integer
    sum matches exactly.
    """
    total_gap = sum(gaps)
    if total_gap > 0:
        proportional = [g / total_gap * total_ms for g in gaps]
    else:
        proportional = [total_ms / len(gaps) for _ in gaps] if gaps else []

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


def resolve_fade_color(
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
