"""Console session abstraction for dirplot.

This module provides a unified interface for terminal interactions,
including size detection, capability detection, and display methods.
It replaces scattered global state with an injectable session object.
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from typing import Protocol


class DisplayOutput(Protocol):
    """Protocol for display output handlers."""

    def show(self, buf: io.BytesIO, title: str | None = None, **kwargs: object) -> None:
        """Display the buffer."""
        ...


@dataclass
class ConsoleCapabilities:
    """Detected terminal capabilities."""

    inline_protocol: str  # "iterm2", "kitty", or ""
    supports_inline: bool
    supports_256_color: bool
    is_interactive: bool
    term_program: str


class ConsoleSession:
    """Encapsulates terminal session state and operations.

    This replaces the scattered global state in display.py and terminal.py
    with an injectable, testable object.

    Example:
        # Production
        console = ConsoleSession.detect()
        console.display_inline(buf)

        # Testing
        mock_console = ConsoleSession(
            capabilities=ConsoleCapabilities(
                inline_protocol="",
                supports_inline=False,
                ...
            ),
            size=(80, 24),
        )
        # Inject mock into commands for testing
    """

    def __init__(
        self,
        capabilities: ConsoleCapabilities,
        size: tuple[int, int],
        is_windows: bool = False,
    ):
        self.capabilities = capabilities
        self.size = size
        self.is_windows = is_windows
        self._inline_cols: int | None = None

    @classmethod
    def detect(cls) -> ConsoleSession:
        """Detect terminal capabilities and create a session.

        This is the factory method for production use.
        """
        from dirplot.display import _detect_inline_protocol
        from dirplot.terminal import get_terminal_size

        is_windows = sys.platform == "win32"

        # Detect inline protocol
        inline_protocol = _detect_inline_protocol()

        # Detect terminal size
        try:
            cols, rows, _, _ = get_terminal_size()
        except Exception:
            cols, rows = 80, 24  # Sensible defaults

        capabilities = ConsoleCapabilities(
            inline_protocol=inline_protocol,
            supports_inline=inline_protocol in ("iterm2", "kitty"),
            supports_256_color=cls._detect_256_color(),
            is_interactive=sys.stdin.isatty(),
            term_program=os.environ.get("TERM_PROGRAM", ""),
        )

        return cls(
            capabilities=capabilities,
            size=(cols, rows),
            is_windows=is_windows,
        )

    @classmethod
    def _detect_256_color(cls) -> bool:
        """Detect if terminal supports 256 colors."""
        term = os.environ.get("TERM", "")
        colorterm = os.environ.get("COLORTERM", "")
        return "256" in term or colorterm in ("truecolor", "24bit")

    @property
    def cols(self) -> int:
        """Terminal columns."""
        return self.size[0]

    @property
    def rows(self) -> int:
        """Terminal rows."""
        return self.size[1]

    def get_canvas_size(self, requested: tuple[int, int] | None = None) -> tuple[int, int]:
        """Get the canvas size for rendering.

        Args:
            requested: User-requested size, or None for terminal size.

        Returns:
            (width_px, height_px) for rendering.
        """
        if requested:
            return requested

        from dirplot.terminal import default_canvas_size

        return default_canvas_size()

    def display_inline(self, buf: io.BytesIO, cols: int | None = None) -> None:
        """Display buffer inline using detected protocol."""
        from dirplot.display import display_inline

        if not self.capabilities.supports_inline:
            raise RuntimeError("Terminal does not support inline graphics")

        display_inline(buf, cols=cols or self.cols)

    def display_window(self, buf: io.BytesIO, title: str | None = None) -> None:
        """Display buffer in system viewer."""
        from dirplot.display import display_window

        display_window(buf, title=title)

    def display(
        self,
        buf: io.BytesIO,
        mode: str,  # "inline", "window", "file", "none"
        title: str | None = None,
        output_path: str | None = None,
    ) -> None:
        """Display buffer according to mode.

        This is the unified display method that replaces the scattered
        display logic in commands.
        """
        if mode == "file" and output_path:
            from pathlib import Path

            Path(output_path).write_bytes(buf.read())
            buf.seek(0)
        elif mode == "inline":
            if self.capabilities.supports_inline:
                self.display_inline(buf, cols=self.cols)
            else:
                # Fall back to window if inline not supported
                self.display_window(buf, title=title)
        elif mode == "window":
            self.display_window(buf, title=title)
        elif mode == "none":
            pass  # Don't display

    def log(self, msg: str, err: bool = False) -> None:
        """Log a message to the console.

        This provides a unified logging interface that respects
        terminal capabilities.
        """
        stream = sys.stderr if err else sys.stdout
        print(msg, file=stream)


class MockConsoleSession(ConsoleSession):
    """Mock console session for testing.

    Records all display calls for verification in tests.
    """

    def __init__(
        self,
        size: tuple[int, int] = (80, 24),
        inline_protocol: str = "",
    ):
        capabilities = ConsoleCapabilities(
            inline_protocol=inline_protocol,
            supports_inline=bool(inline_protocol),
            supports_256_color=True,
            is_interactive=True,
            term_program="MockTerminal",
        )
        super().__init__(capabilities, size)
        self.display_calls: list[dict[str, object]] = []
        self.logs: list[tuple[str, bool]] = []

    def display_inline(self, buf: io.BytesIO, cols: int | None = None) -> None:
        """Record inline display call."""
        self.display_calls.append(
            {
                "method": "inline",
                "cols": cols,
                "size": len(buf.getvalue()),
            }
        )

    def display_window(self, buf: io.BytesIO, title: str | None = None) -> None:
        """Record window display call."""
        self.display_calls.append(
            {
                "method": "window",
                "title": title,
                "size": len(buf.getvalue()),
            }
        )

    def log(self, msg: str, err: bool = False) -> None:
        """Record log call."""
        self.logs.append((msg, err))


# Global session (for backward compatibility during transition)
_SESSION: ConsoleSession | None = None


def get_console() -> ConsoleSession:
    """Get the global console session.

    Creates and caches a detected session on first call.
    """
    global _SESSION
    if _SESSION is None:
        _SESSION = ConsoleSession.detect()
    return _SESSION


def set_console(session: ConsoleSession) -> None:
    """Set the global console session.

    Useful for testing or when injecting a custom session.
    """
    global _SESSION
    _SESSION = session
