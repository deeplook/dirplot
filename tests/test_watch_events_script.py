"""Tests for scripts/watch_events.py."""

import csv
import importlib.util
import io
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileMovedEvent

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "watch_events.py"
spec = importlib.util.spec_from_file_location("watch_events_script", SCRIPT_PATH)
assert spec is not None
assert spec.loader is not None
watch_events = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch_events)


def test_csv_event_handler_ignores_output_file_events(tmp_path: Path) -> None:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=watch_events.FIELDNAMES)
    handler = watch_events.CSVEventHandler(writer, stream, tmp_path / "events.csv")

    handler.on_created(FileCreatedEvent(str(tmp_path / "events.csv")))
    handler.on_moved(FileMovedEvent(str(tmp_path / "source.txt"), str(tmp_path / "events.csv")))
    handler.on_created(FileCreatedEvent(str(tmp_path / "source.txt")))

    rows = stream.getvalue().splitlines()
    assert len(rows) == 1
    assert "source.txt" in rows[0]
