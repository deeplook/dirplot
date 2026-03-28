"""Inline terminal image display (iTerm2 and Kitty protocols)."""

import base64
import io
import os
import sys
import time
from typing import BinaryIO, TextIO

_IS_WINDOWS = sys.platform == "win32"

try:
    import select as _select
    import termios
    import tty

    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False


def _read_fd_response(fd: int, timeout: float = 0.3) -> bytes:
    """Read from *fd* until quiet or *timeout* seconds."""
    result = b""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = _select.select([fd], [], [], min(remaining, 0.05))
        if ready:
            chunk = os.read(fd, 256)
            if chunk:
                result += chunk
                deadline = time.monotonic() + 0.05  # extend on activity
        else:
            if result:
                break
    return result


def _detect_inline_protocol() -> str:
    """Return ``"iterm2"``, ``"kitty"``, or ``""`` based on terminal probing."""
    if _HAS_TERMIOS and not _IS_WINDOWS:
        try:
            fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        except OSError:
            fd = -1

        if fd >= 0:
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)

                # Probe iTerm2 capabilities
                os.write(fd, b"\x1b]1337;Capabilities\x1b\\")
                resp = _read_fd_response(fd, 0.3)
                if b"Capabilities=" in resp and b"F" in resp:
                    return "iterm2"

                # Probe Kitty APC graphics protocol
                os.write(fd, b"\x1b_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA\x1b\\\x1b[c")
                resp = _read_fd_response(fd, 0.3)
                if b"\x1b_G" in resp:
                    return "kitty"
            except Exception:  # noqa: BLE001
                pass
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                os.close(fd)

    # Env-var heuristic fallback
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if term_program == "iterm.app":
        return "iterm2"
    if os.environ.get("KITTY_WINDOW_ID") or term_program in ("kitty", "ghostty"):
        return "kitty"

    return ""


def _open_tty_write_binary() -> tuple[BinaryIO, bool]:
    """Return (file_obj, owned) for the best available binary output channel.

    On Unix, tries /dev/tty first using low-level os.open() (avoids O_CREAT/O_TRUNC
    that Python's built-in open() adds, which can fail on some macOS setups).
    On Windows, tries CONOUT$ instead.
    Falls back to sys.stdout.buffer if neither is available.
    """
    if _IS_WINDOWS:
        try:
            return open("CONOUT$", "wb", buffering=0), True  # noqa: SIM115
        except OSError:
            return sys.stdout.buffer, False
    try:
        fd = os.open("/dev/tty", os.O_WRONLY | os.O_NOCTTY)
        return os.fdopen(fd, "wb", buffering=0, closefd=True), True
    except OSError:
        return sys.stdout.buffer, False


def _open_tty_write_text() -> tuple[TextIO, bool]:
    """Return (file_obj, owned) for the best available text output channel."""
    if _IS_WINDOWS:
        try:
            return open("CONOUT$", "w"), True  # noqa: SIM115
        except OSError:
            return sys.stdout, False
    try:
        fd = os.open("/dev/tty", os.O_WRONLY | os.O_NOCTTY)
        return os.fdopen(fd, "w", closefd=True), True
    except OSError:
        return sys.stdout, False


def _display_iterm2(buf: io.BytesIO) -> None:
    """Display the PNG inline using the iTerm2 escape sequence protocol."""
    data = buf.read()
    b64 = base64.b64encode(data).decode()
    payload = f"\x1b]1337;File=inline=1;size={len(data)};preserveAspectRatio=1:{b64}\a"
    f, owned = _open_tty_write_text()
    try:
        f.write(payload)
        f.flush()
    finally:
        if owned:
            f.close()


def display_kitty(buf: io.BytesIO) -> None:
    """Display the PNG inline using the Kitty APC graphics protocol."""
    data = buf.read()
    b64 = base64.b64encode(data)
    chunk_size = 4096
    chunks = [b64[i : i + chunk_size] for i in range(0, len(b64), chunk_size)]
    out, owned = _open_tty_write_binary()
    try:
        for idx, chunk in enumerate(chunks):
            first = idx == 0
            last = idx == len(chunks) - 1
            more = 0 if last else 1
            header = (f"a=T,f=100,m={more},q=2").encode() if first else (f"m={more},q=2").encode()
            out.write(b"\x1b_G" + header + b";" + chunk + b"\x1b\\")
        out.flush()
    finally:
        if owned:
            out.close()


def display_inline(buf: io.BytesIO) -> None:
    """Display the PNG inline, auto-detecting the terminal graphics protocol."""
    protocol = _detect_inline_protocol()
    if protocol == "kitty":
        display_kitty(buf)
    else:
        _display_iterm2(buf)


def display_window(buf: io.BytesIO, title: str | None = None) -> None:
    """Open the PNG in the system default image viewer.

    When *title* is given it is used as a prefix for the temporary file name
    (sanitised so it is safe on all platforms), making the file easier to
    identify in the OS image viewer's title bar.
    """
    import re
    import tempfile
    import webbrowser
    from pathlib import Path

    from PIL import Image

    if title:
        safe = re.sub(r"[^\w.\-]", "_", title)
        prefix = f"dirplot-{safe}-"
        img = Image.open(buf)
        with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".png", delete=False) as tmp:
            img.save(tmp, format="PNG")
            webbrowser.open(Path(tmp.name).resolve().as_uri())
    else:
        Image.open(buf).show()
