"""Terminal size detection."""

import os
import struct
import sys


def get_terminal_pixel_size() -> tuple[int, int, int]:
    """Return *(width_px, height_px, row_height_px)* of the current terminal.

    Falls back to a character-cell estimate when the ioctl is unavailable
    (e.g. when stdout is not a tty).
    """
    try:
        import fcntl
        import termios

        buf = b"\x00" * 8
        result = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, buf)
        rows, _cols, width_px, height_px = struct.unpack("HHHH", result)
        if width_px > 0 and height_px > 0 and rows > 0:
            return width_px, height_px, height_px // rows
    except Exception:  # noqa: BLE001
        pass
    try:
        size = os.get_terminal_size()
        return size.columns * 8, size.lines * 16, 16
    except Exception:  # noqa: BLE001
        return 1280, 720, 16
