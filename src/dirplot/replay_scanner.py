"""Replay a JSONL filesystem event log as an animated treemap."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def parse_events(path: Path) -> list[tuple[float, str, str, str]]:
    """Parse JSONL events → [(timestamp, type, path, dest_path)], sorted by time."""
    events: list[tuple[float, str, str, str]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            events.append(
                (
                    float(obj["timestamp"]),
                    obj["type"],
                    obj["path"],
                    obj.get("dest_path", ""),
                )
            )
    events.sort(key=lambda e: e[0])
    return events


def scan_to_flat(root: Path, exclude: frozenset[Path] = frozenset()) -> dict[str, int]:
    """Walk *root* and return ``{rel_path: size}`` with forward-slash separators."""
    files: dict[str, int] = {}
    root_str = str(root)
    for dirpath, dirnames, filenames in os.walk(root_str):
        dirnames[:] = [d for d in dirnames if (Path(dirpath) / d).resolve() not in exclude]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.resolve() in exclude:
                continue
            try:
                size = max(1, fpath.stat().st_size)
            except OSError:
                size = 1
            rel = str(fpath.relative_to(root)).replace(os.sep, "/")
            files[rel] = size
    return files


def bucket_events(
    events: list[tuple[float, str, str, str]],
    bucket_size: float,
) -> list[tuple[float, list[tuple[float, str, str, str]]]]:
    """Group *events* into non-overlapping time buckets of *bucket_size* seconds.

    Returns ``[(bucket_start_ts, [events...])]``.
    """
    if not events:
        return []
    buckets: list[tuple[float, list[tuple[float, str, str, str]]]] = []
    current_start = events[0][0]
    current: list[tuple[float, str, str, str]] = []
    for ev in events:
        if ev[0] >= current_start + bucket_size:
            if current:
                buckets.append((current_start, current))
            current_start = ev[0]
            current = []
        current.append(ev)
    if current:
        buckets.append((current_start, current))
    return buckets


def apply_events(
    files: dict[str, int],
    root: Path,
    events: list[tuple[float, str, str, str]],
    exclude: frozenset[Path],
) -> dict[str, str]:
    """Apply *events* to *files* in-place.

    Returns highlights ``{abs_path_str: type}`` (absolute paths, matching
    the keys used by ``rect_map`` in the renderer).
    """
    root_str = str(root)
    highlights: dict[str, str] = {}
    for _ts, event_type, path_str, dest_str in events:
        if not path_str.startswith(root_str):
            continue
        p = Path(path_str)
        if p.resolve() in exclude:
            continue
        try:
            rel = str(p.relative_to(root)).replace(os.sep, "/")
        except ValueError:
            continue

        if event_type == "deleted":
            files.pop(rel, None)
            highlights[path_str] = "deleted"
        elif event_type == "moved" and dest_str:
            dest = Path(dest_str)
            try:
                dest_rel = str(dest.relative_to(root)).replace(os.sep, "/")
            except ValueError:
                dest_rel = None
            old_size = files.pop(rel, None)
            if dest_rel is not None and dest.resolve() not in exclude:
                files[dest_rel] = old_size if old_size is not None else 1
                highlights[dest_str] = "modified"
        else:  # created, modified
            try:
                size = max(1, p.stat().st_size)
            except OSError:
                size = 1
            files[rel] = size
            highlights[path_str] = event_type

    return highlights


RectMap = dict[str, tuple[int, int, int, int]]


def _render_replay_frame_worker(args: tuple[Any, ...]) -> tuple[int, bytes, RectMap]:
    """Top-level picklable worker for parallel replay frame rendering."""
    (
        root_str,
        files,
        highlights,
        ts,
        orig_i,
        progress,
        depth,
        log_scale,
        width_px,
        height_px,
        font_size,
        colormap,
        cushion,
    ) = args

    from datetime import datetime
    from pathlib import Path

    from dirplot.git_scanner import build_node_tree
    from dirplot.render import create_treemap
    from dirplot.scanner import apply_log_sizes

    root = Path(root_str)
    node = build_node_tree(root, files, depth)
    if log_scale:
        apply_log_sizes(node)

    rect_map: RectMap = {}
    dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    buf = create_treemap(
        node,
        width_px,
        height_px,
        font_size,
        colormap,
        None,
        cushion,
        highlights=highlights or None,
        rect_map_out=rect_map,
        title_suffix=dt_str,
        progress=progress,
    )
    return (orig_i, buf.read(), rect_map)
