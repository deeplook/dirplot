"""Tests for terminal size detection."""

import struct
import sys
from unittest.mock import MagicMock, patch

import pytest

from dirplot.terminal import get_terminal_pixel_size

_skip_no_fcntl = pytest.mark.skipif(
    sys.platform == "win32", reason="fcntl not available on Windows"
)


def _make_winsz(rows: int, cols: int, width_px: int, height_px: int) -> bytes:
    return struct.pack("HHHH", rows, cols, width_px, height_px)


@_skip_no_fcntl
def test_get_terminal_pixel_size_from_ioctl() -> None:
    with patch("fcntl.ioctl", return_value=_make_winsz(50, 200, 1600, 800)):
        w, h, row = get_terminal_pixel_size()
    assert w == 1600
    assert h == 800
    assert row == 16  # 800 // 50


@_skip_no_fcntl
def test_get_terminal_pixel_size_ioctl_zero_falls_back() -> None:
    """ioctl returning zero dimensions triggers the os.get_terminal_size fallback."""
    with (
        patch("fcntl.ioctl", return_value=_make_winsz(0, 0, 0, 0)),
        patch("os.get_terminal_size", return_value=MagicMock(columns=80, lines=24)),
    ):
        w, h, row = get_terminal_pixel_size()
    assert w == 80 * 8
    assert h == 24 * 16
    assert row == 16


@_skip_no_fcntl
def test_get_terminal_pixel_size_ioctl_raises_falls_back() -> None:
    """ioctl exception triggers the os.get_terminal_size fallback."""
    with (
        patch("fcntl.ioctl", side_effect=OSError),
        patch("os.get_terminal_size", return_value=MagicMock(columns=100, lines=30)),
    ):
        w, h, row = get_terminal_pixel_size()
    assert w == 100 * 8
    assert h == 30 * 16
    assert row == 16


@_skip_no_fcntl
def test_get_terminal_pixel_size_both_fail() -> None:
    """Both ioctl and get_terminal_size failing returns the hardcoded fallback."""
    with (
        patch("fcntl.ioctl", side_effect=OSError),
        patch("os.get_terminal_size", side_effect=OSError),
    ):
        w, h, row = get_terminal_pixel_size()
    assert w == 1280
    assert h == 720
    assert row == 16
