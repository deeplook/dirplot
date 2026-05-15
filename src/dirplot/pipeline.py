"""Rendering pipeline for dirplot commands.

This module provides a unified pipeline for scanning, transforming, rendering,
and displaying directory trees. It eliminates the repetitive orchestration
code found in individual commands.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from dirplot.scanner import Node
from dirplot.sources import scan_any

if TYPE_CHECKING:
    from dirplot.console import ConsoleSession


class Transform(Protocol):
    """A tree transformation (e.g., prune, log-scale, breadcrumbs)."""

    def apply(self, node: Node) -> Node:
        """Apply the transformation to a tree node."""
        ...


class Renderer(Protocol):
    """Renders a tree to an output format (PNG, SVG, etc.)."""

    def render(self, node: Node) -> io.BytesIO:
        """Render the tree and return as BytesIO buffer."""
        ...


class Display(Protocol):
    """Displays a rendered buffer (inline, window, file, etc.)."""

    def show(self, buf: io.BytesIO, title: str | None = None) -> None:
        """Display the rendered buffer."""
        ...


# Built-in transforms


@dataclass
class PruneTransform:
    """Prune tree to only include specified subtrees."""

    paths: set[str]

    def apply(self, node: Node) -> Node:
        from dirplot.scanner import prune_to_subtrees

        return prune_to_subtrees(node, self.paths)


@dataclass
class BreadcrumbsTransform:
    """Collapse single-subdirectory chains into breadcrumbs."""

    def apply(self, node: Node) -> Node:
        from dirplot.scanner import apply_breadcrumbs

        return apply_breadcrumbs(node)


@dataclass
class LogScaleTransform:
    """Apply log-scale compression to node sizes."""

    ratio: float

    def apply(self, node: Node) -> Node:
        from dirplot.scanner import apply_log_sizes

        apply_log_sizes(node, self.ratio)
        return node


@dataclass
class PipelineConfig:
    """Configuration for a rendering pipeline.

    This declarative config replaces the imperative orchestration
    code duplicated across commands.
    """

    # Source configuration
    roots: list[str]
    exclude: frozenset[str] = field(default_factory=frozenset)
    depth: int | None = None

    # Transforms (applied in order)
    include: set[str] = field(default_factory=set)
    breadcrumbs: bool = True
    logscale: float = 0.0

    # Rendering
    size: tuple[int, int] | None = None
    font_size: int = 12
    colormap: str = "tab20"
    legend: int | None = None
    cushion: bool = True
    dark: bool = True

    # Output
    format: Literal["png", "svg"] = "png"
    output: Path | None = None
    show: bool = True
    inline: bool = False

    # Progress/logging
    log_callback: Callable[[str], None] | None = None
    console: ConsoleSession | None = None  # Injected or auto-detected


class RenderingPipeline:
    """Unified pipeline for scan → transform → render → display.

    Example:
        config = PipelineConfig(
            roots=["."],
            exclude=frozenset({".git", "__pycache__"}),
            breadcrumbs=True,
            format="png",
            inline=True,
        )
        pipeline = RenderingPipeline(config)
        pipeline.run()
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._console: ConsoleSession | None = None

    @property
    def console(self) -> ConsoleSession:
        """Get console session (detected or injected)."""
        if self._console is None:
            if self.config.console:
                self._console = self.config.console
            else:
                from dirplot.console import ConsoleSession

                self._console = ConsoleSession.detect()
        return self._console

    def _log(self, msg: str) -> None:
        """Log a message if callback is configured."""
        if self.config.log_callback:
            self.config.log_callback(msg)

    def scan(self) -> Node:
        """Scan the source(s) and return a tree."""
        import time

        roots = self.config.roots
        if not roots:
            raise ValueError("No roots specified")

        t_start = time.monotonic()

        if len(roots) == 1:
            # Single root - use unified source system
            root = roots[0]
            self._log(f"Scanning {root} ...")
            tree = scan_any(
                root,
                exclude=self.config.exclude,
                depth=self.config.depth,
            )
        else:
            # Multiple roots - build tree under common parent
            from dirplot.scanner import build_tree_multi

            root_paths = [Path(r) for r in roots]
            import os

            common = os.path.commonpath([str(p) for p in root_paths])
            self._log(f"Scanning {len(roots)} paths under {common} ...")
            tree = build_tree_multi(
                root_paths,
                exclude=self.config.exclude,
                depth=self.config.depth,
            )

        t_scan = time.monotonic() - t_start
        self._log(f"Scan complete in {t_scan:.1f}s")

        return tree

    def transform(self, tree: Node) -> Node:
        """Apply all configured transforms to the tree."""
        # Prune to included subtrees first
        if self.config.include:
            tree = PruneTransform(self.config.include).apply(tree)

        # Apply breadcrumbs
        if self.config.breadcrumbs:
            tree = BreadcrumbsTransform().apply(tree)

        # Apply log-scale
        if self.config.logscale > 1.0:
            tree = LogScaleTransform(self.config.logscale).apply(tree)

        return tree

    def render(self, tree: Node) -> io.BytesIO:
        """Render the tree to the configured format."""
        import time

        t_start = time.monotonic()
        self._log("Rendering...")

        # Determine canvas size
        if self.config.size:
            width, height = self.config.size
        else:
            from dirplot.terminal import default_canvas_size

            width, height = default_canvas_size()

        # Render based on format
        if self.config.format == "svg":
            from dirplot.scanner import max_depth
            from dirplot.svg_render import create_treemap_svg

            buf = create_treemap_svg(
                tree,
                width,
                height,
                self.config.font_size,
                self.config.colormap,
                self.config.legend,
                self.config.cushion,
                tree_depth=max_depth(tree),
                dark=self.config.dark,
            )
        else:
            from dirplot.render_png import create_treemap
            from dirplot.scanner import max_depth

            buf = create_treemap(
                tree,
                width,
                height,
                self.config.font_size,
                self.config.colormap,
                self.config.legend,
                self.config.cushion,
                max_depth(tree),
                dark=self.config.dark,
                logscale=self.config.logscale,
            )

        t_render = time.monotonic() - t_start
        self._log(f"Rendered in {t_render:.1f}s")

        return buf

    def display(self, buf: io.BytesIO, title: str | None = None) -> None:
        """Display the rendered buffer according to config."""
        # Determine display mode
        if self.config.output:
            # Save to file
            self.config.output.write_bytes(buf.read())
            buf.seek(0)
            self._log(f"Saved to {self.config.output}")

            if not self.config.show:
                return  # File only, no display

        # Use console session for display
        mode = "inline" if self.config.inline else "window"
        self.console.display(buf, mode=mode, title=title)

    def run(self) -> io.BytesIO:
        """Execute the full pipeline: scan → transform → render → display.

        Returns:
            The rendered buffer (positioned at start).
        """
        # Execute pipeline
        tree = self.scan()
        tree = self.transform(tree)
        buf = self.render(tree)

        # Display (if configured)
        if self.config.show or self.config.output:
            self.display(buf, title=self.config.roots[0] if self.config.roots else None)

        # Reset buffer position for potential further use
        buf.seek(0)
        return buf


@contextmanager
def pipeline_context(config: PipelineConfig) -> Iterator[RenderingPipeline]:
    """Context manager for running a pipeline with automatic cleanup."""
    pipeline = RenderingPipeline(config)
    try:
        yield pipeline
    finally:
        # Any cleanup needed
        pass
