"""Filesystem watcher that regenerates a treemap on every file change."""

import io
import json
import sys
import threading
import time
from pathlib import Path

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    Observer = None  # type: ignore[assignment]

from dirplot.render import create_treemap
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
        self._events: list[dict] = []
        self._timer: threading.Timer | None = None
        self._render_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # Animate mode: raw PNG bytes and inter-frame durations accumulated in
        # memory; written to disk as a single APNG in flush().
        self._frame_bytes: list[bytes] = []
        self._durations: list[int] = []
        self._last_frame_time: float | None = None

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
        from PIL import Image

        frames = [Image.open(io.BytesIO(b)).convert("RGBA") for b in self._frame_bytes]
        if len(frames) == 1:
            frames[0].save(self.output, format="PNG")
        else:
            frames[0].save(
                self.output,
                save_all=True,
                append_images=frames[1:],
                loop=0,
                format="PNG",
                duration=self._durations,
            )
        print(f"Wrote {len(frames)}-frame APNG → {self.output}", file=sys.stderr)

    def _regenerate(self) -> None:
        try:
            node = build_tree_multi(self.roots, self.exclude, self.depth)
            if self.log:
                apply_log_sizes(node)
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
                )
                self.output.write_bytes(buf.read())
                print(f"Updated {self.output}", file=sys.stderr)
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

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("created", event)
            self._record_event("created", event)
            self._schedule_regenerate()

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("deleted", event)
            self._record_event("deleted", event)
            self._schedule_regenerate()

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("modified", event)
            self._record_event("modified", event)
            self._schedule_regenerate()

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("moved", event)
            self._record_event("moved", event)
            self._schedule_regenerate()
