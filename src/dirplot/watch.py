"""Filesystem watcher that regenerates a treemap on every file change."""

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    Observer = None  # type: ignore[assignment]

from dirplot.filters import SizeRange
from dirplot.render_png import create_treemap
from dirplot.scanner import apply_log_sizes, build_tree_multi, filter_by_size
from dirplot.svg_render import create_treemap_svg


class TreemapEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        roots: list[Path],
        output: Path | None = None,
        *,
        exclude: frozenset[str] = frozenset(),
        width_px: int,
        height_px: int,
        font_size: int,
        colormap: str,
        cushion: bool,
        logscale: float = 0.0,
        debounce: float = 0.0,
        event_log: Path | None = None,
        depth: int | None = None,
        dark: bool = True,
        size_ranges: list[SizeRange] | None = None,
        keep_empty_dirs: bool = False,
    ) -> None:
        super().__init__()
        self.roots = roots
        self.output = output
        self.exclude = exclude
        self.depth = depth
        self.width_px = width_px
        self.height_px = height_px
        self.font_size = font_size
        self.colormap = colormap
        self.cushion = cushion
        self.dark = dark
        self.use_svg = output is not None and output.suffix.lower() == ".svg"
        self.logscale = logscale
        self.debounce = debounce
        self.event_log = event_log
        self.size_ranges = size_ranges
        self.keep_empty_dirs = keep_empty_dirs
        self._events: list[dict[str, Any]] = []
        self._timer: threading.Timer | None = None
        self._render_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # Pending file-change highlights: path → event_type, consumed each frame.
        self._pending_highlights: dict[str, str] = {}
        # Rect map from the most recent frame.
        self._prev_rect_map: dict[str, tuple[int, int, int, int]] = {}

    def _regenerate(self) -> None:
        # Consume pending highlights for this frame.
        with self._lock:
            all_highlights = dict(self._pending_highlights) if self._pending_highlights else {}
            self._pending_highlights.clear()

        current_highlights = {p: v for p, v in all_highlights.items() if v != "deleted"} or None

        try:
            node = build_tree_multi(self.roots, self.exclude, self.depth)
            if self.size_ranges:
                filtered = filter_by_size(node, self.size_ranges, self.keep_empty_dirs)
                if filtered is None:
                    print("No files match the --size filter.", file=sys.stderr)
                    return
                node = filtered
            if self.logscale > 1:
                apply_log_sizes(node, self.logscale)
            rect_map: dict[str, tuple[int, int, int, int]] = {}
            if self.use_svg and self.output is not None:
                buf = create_treemap_svg(
                    node,
                    self.width_px,
                    self.height_px,
                    self.font_size,
                    self.colormap,
                    None,
                    self.cushion,
                    dark=self.dark,
                    highlights=current_highlights,
                )
                self.output.write_bytes(buf.read())
            else:
                buf = create_treemap(
                    node,
                    self.width_px,
                    self.height_px,
                    self.font_size,
                    self.colormap,
                    None,
                    self.cushion,
                    highlights=current_highlights,
                    rect_map_out=rect_map,
                    dark=self.dark,
                    logscale=self.logscale,
                )
                if self.output is not None:
                    self.output.write_bytes(buf.read())
                    print(f"Updated {self.output}", file=sys.stderr)
            self._prev_rect_map = rect_map
        except Exception as exc:  # noqa: BLE001
            print(f"Error regenerating treemap: {exc}", file=sys.stderr)

    def _record_event(self, verb: str, event: FileSystemEvent) -> None:
        src = event.src_path
        dest = getattr(event, "dest_path", None)
        src_s = src.decode() if isinstance(src, bytes) else src
        dest_s = dest.decode() if isinstance(dest, bytes) else dest
        with self._lock:
            self._events.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": verb,
                    "path": src_s,
                    "dest_path": dest_s,
                }
            )

    def _schedule_regenerate(self) -> None:
        if self.debounce <= 0:
            self._regenerate()
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce, self._on_timer_fire)
            self._timer.start()

    def _on_timer_fire(self) -> None:
        with self._lock:
            self._timer = None
            self._render_thread = threading.current_thread()
        self._regenerate()
        with self._lock:
            self._render_thread = None

    def flush(self) -> None:
        """Fire any pending debounced regeneration."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
                pending = True
            else:
                pending = False
            render_thread = self._render_thread
        if pending:
            self._regenerate()
        elif render_thread is not None:
            render_thread.join()
        if self.event_log is not None and self._events:
            with self._lock:
                snapshot = list(self._events)
            lines = [json.dumps(e, ensure_ascii=False) for e in snapshot]
            self.event_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _log_event(self, verb: str, event: FileSystemEvent) -> None:
        src = event.src_path
        dest = getattr(event, "dest_path", None)
        src_s = src.decode() if isinstance(src, bytes) else src
        dest_s = dest.decode() if isinstance(dest, bytes) else dest
        msg = f"{verb}: {src_s}" if not dest_s else f"{verb}: {src_s} → {dest_s}"
        print(msg, file=sys.stderr)

    def _track_highlight(self, verb: str, event: FileSystemEvent) -> None:
        src = event.src_path
        src_s = Path(src.decode() if isinstance(src, bytes) else src).as_posix()
        with self._lock:
            if verb == "moved":
                self._pending_highlights[src_s] = "deleted"
                dest = getattr(event, "dest_path", None)
                dest_raw = dest.decode() if isinstance(dest, bytes) else dest
                dest_s = Path(dest_raw).as_posix() if dest_raw else None
                if dest_s:
                    self._pending_highlights[dest_s] = "created"
            elif verb == "modified" and src_s in self._pending_highlights:
                pass  # don't overwrite "created" with "modified"
            else:
                self._pending_highlights[src_s] = verb

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("created", event)
            self._record_event("created", event)
            self._track_highlight("created", event)
            self._schedule_regenerate()

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("deleted", event)
            self._record_event("deleted", event)
            self._track_highlight("deleted", event)
            self._schedule_regenerate()

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("modified", event)
            self._record_event("modified", event)
            self._track_highlight("modified", event)
            self._schedule_regenerate()

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("moved", event)
            self._record_event("moved", event)
            self._track_highlight("moved", event)
            self._schedule_regenerate()
