#!/usr/bin/env python3
"""Watch directories and log filesystem events to a CSV file.

Usage: watch_events.py [-o events.csv] DIR [DIR ...]

Streams events until Ctrl-C. Each row: timestamp, event_type, src_path, dest_path.
"""

import csv
import signal
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

FIELDNAMES = ["timestamp", "event_type", "src_path", "dest_path"]


class CSVEventHandler(FileSystemEventHandler):
    def __init__(self, writer: csv.DictWriter, stream) -> None:
        super().__init__()
        self._writer = writer
        self._stream = stream

    def _write(self, verb: str, event: FileSystemEvent) -> None:
        src = event.src_path
        src_s = src.decode() if isinstance(src, bytes) else src
        dest = getattr(event, "dest_path", None)
        dest_s = (dest.decode() if isinstance(dest, bytes) else dest) or ""
        self._writer.writerow(
            {
                "timestamp": f"{time.time():.6f}",
                "event_type": verb,
                "src_path": src_s,
                "dest_path": dest_s,
            }
        )
        self._stream.flush()

    def on_created(self, event: FileSystemEvent) -> None:
        self._write("created", event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._write("deleted", event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._write("modified", event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._write("moved", event)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Watch directories and log events to CSV.")
    parser.add_argument("dirs", nargs="+", type=Path, help="Directories to watch")
    parser.add_argument(
        "-o", "--output", type=Path, default=None, help="Output CSV file (default: stdout)"
    )
    args = parser.parse_args()

    for d in args.dirs:
        if not d.is_dir():
            print(f"Error: {d} is not a directory", file=sys.stderr)
            sys.exit(1)

    stream = (
        open(args.output, "w", newline="", encoding="utf-8")  # noqa: SIM115
        if args.output
        else sys.stdout
    )

    writer = csv.DictWriter(stream, fieldnames=FIELDNAMES, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    stream.flush()

    handler = CSVEventHandler(writer, stream)
    observer = Observer()
    for d in args.dirs:
        observer.schedule(handler, str(d), recursive=True)

    observer.start()
    roots = ", ".join(str(d) for d in args.dirs)
    print(f"Watching {roots}  (Ctrl-C to stop)", file=sys.stderr)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        observer.stop()
        observer.join()
        if args.output:
            stream.close()
            print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
