#!/usr/bin/env python3
"""List frame durations in an APNG file."""

import struct
import sys
from pathlib import Path


def read_apng_frames(path: Path) -> list[dict]:
    """Parse APNG chunks and return per-frame info."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file")

    frames = []
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]

        if chunk_type == b"acTL":
            num_frames = struct.unpack(">I", data[pos + 8 : pos + 12])[0]
            num_plays = struct.unpack(">I", data[pos + 12 : pos + 16])[0]
            print(f"Animation: {num_frames} frames, loops={num_plays} (0=infinite)")
            print()

        elif chunk_type == b"fcTL":
            payload = data[pos + 8 : pos + 8 + length]
            seq = struct.unpack(">I", payload[0:4])[0]
            w = struct.unpack(">I", payload[4:8])[0]
            h = struct.unpack(">I", payload[8:12])[0]
            x_off = struct.unpack(">I", payload[12:16])[0]
            y_off = struct.unpack(">I", payload[16:20])[0]
            delay_num = struct.unpack(">H", payload[20:22])[0]
            delay_den = struct.unpack(">H", payload[22:24])[0]
            if delay_den == 0:
                delay_den = 100
            duration_ms = delay_num / delay_den * 1000
            frames.append(
                {
                    "seq": seq,
                    "size": f"{w}x{h}",
                    "offset": f"+{x_off}+{y_off}",
                    "duration_ms": duration_ms,
                }
            )

        pos += 12 + length  # 4 len + 4 type + data + 4 crc

    return frames


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.png>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    frames = read_apng_frames(path)

    if not frames:
        print("Not an APNG (no animation chunks found).")
        return

    total = 0.0
    for i, f in enumerate(frames):
        print(f"  Frame {i + 1}: {f['duration_ms']:8.1f}ms  {f['size']}  {f['offset']}")
        total += f["duration_ms"]

    print()
    print(f"  Total: {total:.1f}ms ({total / 1000:.2f}s)")


if __name__ == "__main__":
    main()
