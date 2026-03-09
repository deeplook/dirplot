"""Terminal size detection."""

import os
import struct
import sys


def get_terminal_size() -> tuple[int, int, int, int]:
    """Return *(cols, rows, width_px, height_px)* of the current terminal.

    Falls back to a character-cell estimate when the ioctl is unavailable
    (e.g. when stdout is not a tty).
    """
    try:
        import fcntl
        import termios

        buf = b"\x00" * 8
        result = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, buf)
        rows, cols, width_px, height_px = struct.unpack("HHHH", result)
        if cols > 0 and rows > 0:
            if width_px == 0 or height_px == 0:
                width_px = cols * 8
                height_px = rows * 16
            return cols, rows, width_px, height_px
    except Exception:  # noqa: BLE001
        pass
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines, size.columns * 8, size.lines * 16
    except Exception:  # noqa: BLE001
        return 160, 45, 1280, 720


def get_terminal_pixel_size() -> tuple[int, int, int]:
    """Return *(width_px, height_px, row_height_px)* of the current terminal.

    Falls back to a character-cell estimate when the ioctl is unavailable
    (e.g. when stdout is not a tty).
    """
    cols, rows, width_px, height_px = get_terminal_size()
    return width_px, height_px, height_px // rows if rows > 0 else 16
