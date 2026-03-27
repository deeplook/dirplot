"""Filesystem watcher that regenerates a treemap on every file change."""

import io
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    Observer = None  # type: ignore[assignment]

from dirplot.render import _draw_highlights, create_treemap
from dirplot.scanner import apply_log_sizes, build_tree_multi
from dirplot.svg_render import create_treemap_svg


class TreemapEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        roots: list[Path],
        output: Path,
        *,
        exclude: frozenset[Path] = frozenset(),
        width_px: int,
        height_px: int,
        font_size: int,
        colormap: str,
        cushion: bool,
        animate: bool = False,
        log: bool = False,
        debounce: float = 0.0,
        event_log: Path | None = None,
        depth: int | None = None,
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
        self.use_svg = output.suffix.lower() == ".svg"
        self.animate = animate
        self.log = log
        self.debounce = debounce
        self.event_log = event_log
        self._events: list[dict[str, Any]] = []
        self._timer: threading.Timer | None = None
        self._render_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # Animate mode: raw PNG bytes and inter-frame durations accumulated in
        # memory; written to disk as a single APNG in flush().
        self._frame_bytes: list[bytes] = []
        self._durations: list[int] = []
        self._last_frame_time: float | None = None
        # Pending file-change highlights: path → event_type, consumed each frame.
        self._pending_highlights: dict[str, str] = {}
        # Rect map from the most recent frame, used for deletion highlights.
        self._prev_rect_map: dict[str, tuple[int, int, int, int]] = {}

    def _store_frame(self, png_bytes: bytes) -> None:
        """Append a rendered PNG to the in-memory frame list and update timings."""
        now = time.monotonic()
        # APNG fcTL delay is uint16/uint16; Pillow uses delay_den=1000, so
        # delay_num = duration_ms must fit in uint16 (max 65 535 ms ≈ 65 s).
        if self._durations and self._last_frame_time is not None:
            self._durations[-1] = min(65535, max(100, int((now - self._last_frame_time) * 1000)))
        self._frame_bytes.append(png_bytes)
        self._durations.append(1000)  # placeholder until next frame arrives
        self._last_frame_time = now

    def _write_apng(self) -> None:
        """Write all accumulated frames as a single APNG (called once in flush())."""
        from dirplot.render import write_apng

        write_apng(self.output, self._frame_bytes, self._durations)
        print(f"Wrote {len(self._frame_bytes)}-frame APNG → {self.output}", file=sys.stderr)

    def _patch_prev_frame_deletions(self, deletions: dict[str, str]) -> None:
        """Draw red borders on the previous frame for files about to be deleted."""
        from PIL import Image, ImageDraw

        prev_img = Image.open(io.BytesIO(self._frame_bytes[-1])).convert("RGB")
        draw = ImageDraw.Draw(prev_img)
        _draw_highlights(draw, self._prev_rect_map, deletions)
        buf = io.BytesIO()
        prev_img.save(buf, format="PNG")
        self._frame_bytes[-1] = buf.getvalue()

    def _regenerate(self) -> None:
        # Consume pending highlights for this frame.
        with self._lock:
            all_highlights = dict(self._pending_highlights) if self._pending_highlights else {}
            self._pending_highlights.clear()

        # Separate deletions (shown on previous frame) from other highlights.
        deletions = {p: v for p, v in all_highlights.items() if v == "deleted"}
        current_highlights = {p: v for p, v in all_highlights.items() if v != "deleted"} or None

        # Patch the previous frame with red borders for deleted files.
        if deletions and self._prev_rect_map and self._frame_bytes:
            self._patch_prev_frame_deletions(deletions)

        try:
            node = build_tree_multi(self.roots, self.exclude, self.depth)
            if self.log:
                apply_log_sizes(node)
            rect_map: dict[str, tuple[int, int, int, int]] = {}
            if self.use_svg:
                buf = create_treemap_svg(
                    node,
                    self.width_px,
                    self.height_px,
                    self.font_size,
                    self.colormap,
                    None,
                    self.cushion,
                )
                self.output.write_bytes(buf.read())
            elif self.animate:
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
                )
                self._store_frame(buf.read())
                print(f"Captured frame {len(self._frame_bytes)}", file=sys.stderr)
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
                )
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
                    "timestamp": time.time(),
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
        """Fire any pending debounced regeneration and write the event log."""
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
        if self.animate and self._frame_bytes:
            self._write_apng()
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
        src_s = src.decode() if isinstance(src, bytes) else src
        with self._lock:
            if verb == "moved":
                self._pending_highlights[src_s] = "deleted"
                dest = getattr(event, "dest_path", None)
                dest_s = dest.decode() if isinstance(dest, bytes) else dest
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
