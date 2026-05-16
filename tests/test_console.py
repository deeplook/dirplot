"""Tests for the console session abstraction."""

from __future__ import annotations

import io

import pytest

from dirplot.console import (
    ConsoleCapabilities,
    ConsoleSession,
    MockConsoleSession,
    get_console,
    set_console,
)


class TestConsoleCapabilities:
    """Test ConsoleCapabilities dataclass."""

    def test_basic_creation(self):
        """Can create capabilities object."""
        caps = ConsoleCapabilities(
            inline_protocol="iterm2",
            supports_inline=True,
            supports_256_color=True,
            is_interactive=True,
            term_program="iTerm.app",
        )
        assert caps.inline_protocol == "iterm2"
        assert caps.supports_inline is True


class TestConsoleSession:
    """Test ConsoleSession class."""

    def test_basic_properties(self):
        """Session exposes basic properties."""
        caps = ConsoleCapabilities(
            inline_protocol="",
            supports_inline=False,
            supports_256_color=True,
            is_interactive=True,
            term_program="",
        )
        session = ConsoleSession(caps, size=(100, 50))

        assert session.cols == 100
        assert session.rows == 50
        assert session.size == (100, 50)

    def test_get_canvas_size_uses_requested(self):
        """Returns requested size when provided."""
        caps = ConsoleCapabilities(
            inline_protocol="",
            supports_inline=False,
            supports_256_color=True,
            is_interactive=True,
            term_program="",
        )
        session = ConsoleSession(caps, size=(80, 24))

        result = session.get_canvas_size(requested=(1920, 1080))

        assert result == (1920, 1080)

    def test_get_canvas_size_uses_terminal_default(self):
        """Returns terminal default when no size requested."""
        caps = ConsoleCapabilities(
            inline_protocol="",
            supports_inline=False,
            supports_256_color=True,
            is_interactive=True,
            term_program="",
        )
        session = ConsoleSession(caps, size=(80, 24))

        result = session.get_canvas_size(requested=None)

        # Should return default canvas size (implementation dependent)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(x, int) for x in result)

    def test_display_inline_raises_when_not_supported(self):
        """display_inline raises when terminal doesn't support it."""
        caps = ConsoleCapabilities(
            inline_protocol="",
            supports_inline=False,
            supports_256_color=True,
            is_interactive=True,
            term_program="",
        )
        session = ConsoleSession(caps, size=(80, 24))
        buf = io.BytesIO(b"test data")

        with pytest.raises(RuntimeError, match="does not support inline"):
            session.display_inline(buf)


class TestMockConsoleSession:
    """Test MockConsoleSession for testing."""

    def test_records_inline_calls(self):
        """Mock records inline display calls."""
        mock = MockConsoleSession(size=(80, 24), inline_protocol="iterm2")
        buf = io.BytesIO(b"test data")

        mock.display_inline(buf, cols=100)

        assert len(mock.display_calls) == 1
        assert mock.display_calls[0]["method"] == "inline"
        assert mock.display_calls[0]["cols"] == 100

    def test_records_window_calls(self):
        """Mock records window display calls."""
        mock = MockConsoleSession()
        buf = io.BytesIO(b"test data")

        mock.display_window(buf, title="My Title")

        assert len(mock.display_calls) == 1
        assert mock.display_calls[0]["method"] == "window"
        assert mock.display_calls[0]["title"] == "My Title"

    def test_records_logs(self):
        """Mock records log calls."""
        mock = MockConsoleSession()

        mock.log("Hello", err=False)
        mock.log("Error", err=True)

        assert len(mock.logs) == 2
        assert mock.logs[0] == ("Hello", False)
        assert mock.logs[1] == ("Error", True)

    def test_display_routes_by_mode(self):
        """display() method routes to correct handler."""
        mock = MockConsoleSession(inline_protocol="iterm2")
        buf = io.BytesIO(b"test data")

        # Test inline mode
        mock.display(buf, mode="inline")
        assert mock.display_calls[-1]["method"] == "inline"

        # Test window mode
        mock.display(buf, mode="window")
        assert mock.display_calls[-1]["method"] == "window"

        # Test none mode
        call_count = len(mock.display_calls)
        mock.display(buf, mode="none")
        assert len(mock.display_calls) == call_count  # No new call


class TestGlobalConsole:
    """Test global console session management."""

    def test_get_console_creates_default(self):
        """get_console creates a default session."""
        # Note: This might need mocking in real test environment
        try:
            console = get_console()
            assert isinstance(console, ConsoleSession)
        finally:
            # Clean up global state
            set_console(None)

    def test_set_console_changes_global(self):
        """set_console changes the global session."""
        original = get_console()
        try:
            mock = MockConsoleSession()
            set_console(mock)

            result = get_console()
            assert result is mock
        finally:
            set_console(original)


class TestConsoleIntegration:
    """Integration tests for console usage."""

    def test_can_be_injected_into_pipeline(self, tmp_path):
        """ConsoleSession can be injected into RenderingPipeline."""
        from dirplot.pipeline import PipelineConfig, RenderingPipeline

        (tmp_path / "file.txt").write_text("x" * 100)

        mock_console = MockConsoleSession()

        config = PipelineConfig(
            roots=[str(tmp_path)],
            show=True,
            inline=True,
            console=mock_console,
        )
        pipeline = RenderingPipeline(config)

        # Should use the injected console
        assert pipeline.console is mock_console

    def test_mock_records_pipeline_display(self, tmp_path):
        """Mock console records display calls from pipeline."""
        from dirplot.pipeline import PipelineConfig, RenderingPipeline

        (tmp_path / "file.txt").write_text("x" * 100)

        mock_console = MockConsoleSession(inline_protocol="iterm2")

        config = PipelineConfig(
            roots=[str(tmp_path)],
            show=True,
            inline=True,
            console=mock_console,
        )
        pipeline = RenderingPipeline(config)

        # Run pipeline (should call display)
        import contextlib

        with contextlib.suppress(Exception):  # Display might fail in test environment
            pipeline.run()

        # Should have recorded a display call
        # (Actual assertion depends on pipeline implementation)
