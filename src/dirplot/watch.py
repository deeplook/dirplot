"""Filesystem watcher that regenerates a treemap on every file change."""

import io
import sys
import time
from pathlib import Path

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    Observer = None  # type: ignore[assignment,misc]

from dirplot.render import create_treemap
from dirplot.scanner import apply_log_sizes, build_tree
from dirplot.svg_render import create_treemap_svg


class TreemapEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        root: Path,
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
    ) -> None:
        super().__init__()
        self.root = root
        self.output = output
        self.exclude = exclude
        self.width_px = width_px
        self.height_px = height_px
        self.font_size = font_size
        self.colormap = colormap
        self.cushion = cushion
        self.use_svg = output.suffix.lower() == ".svg"
        self.animate = animate
        self.log = log
        self._last_frame_time: float | None = None  # set on first frame, persisted in metadata

    def _append_apng_frame(self, new_frame_bytes: bytes) -> None:
        from PIL import Image, ImageSequence, PngImagePlugin

        now = time.monotonic()
        new_frame = Image.open(io.BytesIO(new_frame_bytes)).convert("RGBA")

        wall_now = time.time()

        if self.output.exists():
            existing = Image.open(self.output)
            # Read per-frame durations already stored in the APNG fcTL chunks.
            frames: list[Image.Image] = []
            durations: list[int] = []
            for frame in ImageSequence.Iterator(existing):
                frames.append(frame.copy().convert("RGBA"))
                durations.append(int(frame.info.get("duration", 1000)))
            # Restore last-frame timestamp from tEXt metadata if this is a fresh process.
            if self._last_frame_time is None:
                raw = existing.info.get("dirplot_last_frame_time")
                if raw is not None:
                    try:
                        # Stored as wall-clock epoch; convert to an equivalent monotonic offset.
                        wall_stored = float(raw)
                        self._last_frame_time = now - (wall_now - wall_stored)
                    except ValueError:
                        pass
        else:
            frames = []
            durations = []

        # Update the last existing frame's duration to the real elapsed time.
        if durations and self._last_frame_time is not None:
            durations[-1] = max(100, int((now - self._last_frame_time) * 1000))

        frames.append(new_frame)
        durations.append(1000)  # placeholder for the new last frame

        self._last_frame_time = now

        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("dirplot_last_frame_time", str(wall_now))

        frames[0].save(
            self.output,
            save_all=True,
            append_images=frames[1:],
            loop=0,
            format="PNG",
            duration=durations,
            pnginfo=pnginfo,
        )

    def _regenerate(self) -> None:
        try:
            node = build_tree(self.root, self.exclude)
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
                self._append_apng_frame(buf.read())
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

    def _log_event(self, verb: str, event: FileSystemEvent) -> None:
        src = event.src_path
        dest = getattr(event, "dest_path", None)
        msg = f"{verb}: {src}" if not dest else f"{verb}: {src} → {dest}"
        print(msg, file=sys.stderr)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("created", event)
            self._regenerate()

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("deleted", event)
            self._regenerate()

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("modified", event)
            self._regenerate()

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._log_event("moved", event)
            self._regenerate()
