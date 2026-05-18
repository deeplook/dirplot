"""Tests for the filesystem watcher (TreemapEventHandler)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dirplot.watch import TreemapEventHandler

try:
    from watchdog.events import (
        FileCreatedEvent,
        FileDeletedEvent,
        FileModifiedEvent,
        FileMovedEvent,
    )

    _watchdog_available = True
except ImportError:
    _watchdog_available = False


# ---------------------------------------------------------------------------
# Snapshot output (--snapshot)
# ---------------------------------------------------------------------------


def test_watch_snapshot_written(tmp_path: Path) -> None:
    """_regenerate writes a PNG to output when snapshot path is given."""
    out = tmp_path / "treemap.png"
    (tmp_path / "a.py").write_bytes(b"x" * 2_000)

    handler = TreemapEventHandler(
        [tmp_path],
        output=out,
        width_px=200,
        height_px=150,
        font_size=12,
        colormap="tab20",
        cushion=False,
    )
    handler._regenerate()

    assert out.exists()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_watch_no_snapshot_no_write(tmp_path: Path) -> None:
    """_regenerate does not crash when output is None (no snapshot)."""
    (tmp_path / "a.py").write_bytes(b"x" * 1_000)

    handler = TreemapEventHandler(
        [tmp_path],
        output=None,
        width_px=200,
        height_px=150,
        font_size=12,
        colormap="tab20",
        cushion=False,
    )
    # Must not raise
    handler._regenerate()


# ---------------------------------------------------------------------------
# SVG output path
# ---------------------------------------------------------------------------


def test_watch_svg_output(tmp_path: Path) -> None:
    """_regenerate writes an SVG file when output has .svg extension."""
    out = tmp_path / "treemap.svg"
    (tmp_path / "a.py").write_bytes(b"x" * 1_000)

    handler = TreemapEventHandler(
        [tmp_path], out, width_px=200, height_px=150, font_size=12, colormap="tab20", cushion=False
    )
    handler._regenerate()

    assert out.exists()
    content = out.read_text()
    assert "<svg" in content


def test_watch_svg_output_includes_change_highlight(tmp_path: Path) -> None:
    """_regenerate passes pending file highlights to SVG rendering."""
    out = tmp_path / "treemap.svg"
    changed = tmp_path / "a.py"
    changed.write_bytes(b"x" * 1_000)

    handler = TreemapEventHandler(
        [tmp_path], out, width_px=200, height_px=150, font_size=12, colormap="tab20", cushion=False
    )
    handler._pending_highlights[changed.as_posix()] = "created"
    handler._regenerate()

    assert 'stroke="#00dc00"' in out.read_text()


# ---------------------------------------------------------------------------
# log-scale path
# ---------------------------------------------------------------------------


def test_watch_log_scale(tmp_path: Path) -> None:
    """_regenerate with logscale > 1 does not crash and produces a PNG."""
    out = tmp_path / "treemap.png"
    (tmp_path / "big.py").write_bytes(b"x" * 100_000)
    (tmp_path / "tiny.py").write_bytes(b"x" * 1)

    handler = TreemapEventHandler(
        [tmp_path],
        out,
        width_px=200,
        height_px=150,
        font_size=12,
        colormap="tab20",
        cushion=False,
        logscale=4.0,
    )
    handler._regenerate()

    assert out.exists()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Exception during rendering is caught
# ---------------------------------------------------------------------------


def test_watch_regenerate_exception_is_caught(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """An exception inside _regenerate is printed to stderr and does not propagate."""
    from unittest.mock import patch

    out = tmp_path / "treemap.png"
    handler = TreemapEventHandler(
        [tmp_path], out, width_px=200, height_px=150, font_size=12, colormap="tab20", cushion=False
    )

    with patch("dirplot.watch.build_tree_multi", side_effect=RuntimeError("boom")):
        handler._regenerate()  # must not raise

    captured = capsys.readouterr()
    assert "boom" in captured.err


# ---------------------------------------------------------------------------
# _record_event with bytes paths
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_record_event_bytes_path(tmp_path: Path) -> None:
    """_record_event decodes bytes src_path correctly."""
    out = tmp_path / "t.png"
    handler = TreemapEventHandler(
        [tmp_path], out, width_px=100, height_px=100, font_size=12, colormap="tab20", cushion=False
    )
    event = MagicMock()
    event.src_path = b"/some/bytes/path.py"
    event.dest_path = None
    handler._record_event("created", event)
    assert handler._events[-1]["path"] == "/some/bytes/path.py"


# ---------------------------------------------------------------------------
# debounce=0 path
# ---------------------------------------------------------------------------


def test_schedule_regenerate_no_debounce(tmp_path: Path) -> None:
    """With debounce=0, _schedule_regenerate calls _regenerate immediately."""
    out = tmp_path / "treemap.png"
    (tmp_path / "f.py").write_bytes(b"x" * 500)

    handler = TreemapEventHandler(
        [tmp_path],
        out,
        width_px=100,
        height_px=100,
        font_size=12,
        colormap="tab20",
        cushion=False,
        debounce=0,
    )
    handler._schedule_regenerate()
    assert out.exists()


# ---------------------------------------------------------------------------
# flush joins a running render thread
# ---------------------------------------------------------------------------


def test_flush_joins_render_thread(tmp_path: Path) -> None:
    """flush() calls render_thread.join() when a render thread is active."""
    out = tmp_path / "t.png"
    handler = TreemapEventHandler(
        [tmp_path], out, width_px=100, height_px=100, font_size=12, colormap="tab20", cushion=False
    )
    mock_thread = MagicMock()
    handler._render_thread = mock_thread
    handler.flush()
    mock_thread.join.assert_called_once()


# ---------------------------------------------------------------------------
# Event handlers: on_created, on_deleted, on_modified, on_moved
# ---------------------------------------------------------------------------


def _handler(tmp_path: Path, out: Path, **kw: object) -> TreemapEventHandler:
    """Helper: create a handler with a large debounce so the timer never fires in tests."""
    return TreemapEventHandler(
        [tmp_path],
        out,
        width_px=100,
        height_px=100,
        font_size=12,
        colormap="tab20",
        cushion=False,
        debounce=100.0,
        **kw,
    )


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_on_created_file(tmp_path: Path) -> None:
    out = tmp_path / "t.png"
    handler = _handler(tmp_path, out)
    (tmp_path / "new.py").write_bytes(b"x" * 10)
    event = FileCreatedEvent(str(tmp_path / "new.py"))
    handler.on_created(event)
    handler._timer.cancel()
    assert handler._pending_highlights.get((tmp_path / "new.py").as_posix()) == "created"


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_on_created_directory_ignored(tmp_path: Path) -> None:
    """Directory creation events are ignored."""
    out = tmp_path / "t.png"
    handler = _handler(tmp_path, out)
    event = MagicMock()
    event.is_directory = True
    event.src_path = str(tmp_path / "newdir")
    handler.on_created(event)
    assert not handler._pending_highlights


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_on_deleted_file(tmp_path: Path) -> None:
    out = tmp_path / "t.png"
    handler = _handler(tmp_path, out)
    event = FileDeletedEvent(str(tmp_path / "gone.py"))
    handler.on_deleted(event)
    handler._timer.cancel()
    assert handler._pending_highlights.get((tmp_path / "gone.py").as_posix()) == "deleted"


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_on_modified_file(tmp_path: Path) -> None:
    out = tmp_path / "t.png"
    f = tmp_path / "mod.py"
    f.write_bytes(b"x" * 20)
    handler = _handler(tmp_path, out)
    event = FileModifiedEvent(str(f))
    handler.on_modified(event)
    handler._timer.cancel()
    assert handler._pending_highlights.get(f.as_posix()) == "modified"


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_on_moved_file(tmp_path: Path) -> None:
    out = tmp_path / "t.png"
    src = tmp_path / "old.py"
    dst = tmp_path / "new.py"
    handler = _handler(tmp_path, out)
    event = FileMovedEvent(str(src), str(dst))
    handler.on_moved(event)
    handler._timer.cancel()
    assert handler._pending_highlights.get(src.as_posix()) == "deleted"
    assert handler._pending_highlights.get(dst.as_posix()) == "created"


# ---------------------------------------------------------------------------
# event_log written by flush()
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_flush_writes_event_log(tmp_path: Path) -> None:
    """flush() writes recorded events as JSONL to event_log path."""
    import json

    out = tmp_path / "t.png"
    log = tmp_path / "events.jsonl"
    handler = _handler(tmp_path, out, event_log=log)

    event = FileCreatedEvent(str(tmp_path / "x.py"))
    handler.on_created(event)
    handler._timer.cancel()
    handler.flush()

    assert log.exists()
    lines = log.read_text().strip().splitlines()
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    assert rec["type"] == "created"
