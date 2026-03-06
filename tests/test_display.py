"""Tests for inline terminal display with /dev/tty unavailable."""

import io
import sys
from unittest.mock import patch

import pytest

from dirplot.display import (
    _detect_inline_protocol,
    _display_iterm2,
    _open_tty_write_binary,
    _open_tty_write_text,
    display_inline,
    display_kitty,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # minimal fake PNG


def _buf() -> io.BytesIO:
    return io.BytesIO(PNG_BYTES)


# ---------------------------------------------------------------------------
# _open_tty_write_binary / _open_tty_write_text
# ---------------------------------------------------------------------------


def test_open_tty_write_binary_falls_back_to_stdout_buffer() -> None:
    with patch("os.open", side_effect=OSError("no tty")):
        f, owned = _open_tty_write_binary()
    assert f is sys.stdout.buffer
    assert owned is False


def test_open_tty_write_text_falls_back_to_stdout() -> None:
    with patch("os.open", side_effect=OSError("no tty")):
        f, owned = _open_tty_write_text()
    assert f is sys.stdout
    assert owned is False


# ---------------------------------------------------------------------------
# display_kitty — no /dev/tty
# ---------------------------------------------------------------------------


def test_display_kitty_no_tty_writes_to_stdout(capsys: pytest.CaptureFixture) -> None:
    with patch("os.open", side_effect=OSError("no tty")):
        display_kitty(_buf())

    raw = capsys.readouterr().out.encode(sys.stdout.encoding or "utf-8", errors="replace")
    # Kitty APC frame starts with ESC _ G
    assert b"\x1b_G" in raw


# ---------------------------------------------------------------------------
# _display_iterm2 — no /dev/tty
# ---------------------------------------------------------------------------


def test_display_iterm2_no_tty_writes_to_stdout(capsys: pytest.CaptureFixture) -> None:
    with patch("os.open", side_effect=OSError("no tty")):
        _display_iterm2(_buf())

    out = capsys.readouterr().out
    assert "\x1b]1337;File=" in out
    assert out.endswith("\a")


# ---------------------------------------------------------------------------
# _detect_inline_protocol — no /dev/tty, env-var fallback
# ---------------------------------------------------------------------------


def test_detect_protocol_no_tty_kitty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    with patch("os.open", side_effect=OSError("no tty")):
        assert _detect_inline_protocol() == "kitty"


def test_detect_protocol_no_tty_iterm2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    with patch("os.open", side_effect=OSError("no tty")):
        assert _detect_inline_protocol() == "iterm2"


def test_detect_protocol_no_tty_ghostty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    with patch("os.open", side_effect=OSError("no tty")):
        assert _detect_inline_protocol() == "kitty"


def test_detect_protocol_no_tty_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    with patch("os.open", side_effect=OSError("no tty")):
        assert _detect_inline_protocol() == ""


# ---------------------------------------------------------------------------
# display_inline — no /dev/tty, routes by env
# ---------------------------------------------------------------------------


def test_display_inline_no_tty_routes_kitty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    with patch("os.open", side_effect=OSError("no tty")):
        display_inline(_buf())

    raw = capsys.readouterr().out.encode(sys.stdout.encoding or "utf-8", errors="replace")
    assert b"\x1b_G" in raw


def test_display_inline_no_tty_routes_iterm2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    with patch("os.open", side_effect=OSError("no tty")):
        display_inline(_buf())

    out = capsys.readouterr().out
    assert "\x1b]1337;File=" in out


def test_display_inline_no_tty_no_env_falls_back_to_iterm2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """With no env hints, display_inline falls through to _display_iterm2."""
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    with patch("os.open", side_effect=OSError("no tty")):
        display_inline(_buf())

    out = capsys.readouterr().out
    assert "\x1b]1337;File=" in out
