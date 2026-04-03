"""Integration test: watch + animate mode produces a valid multi-frame APNG.

The output is written to tests/animation/watch_demo.png and kept after the
test so it can be inspected visually in Safari, Firefox, or Preview.
"""

import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image, ImageSequence

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

_DEMO_OUTPUT = Path(__file__).parent / "animation" / "watch_demo.png"


def test_watch_animate_apng(tmp_path: Path) -> None:
    """Watch a directory through several distinct file-system states and verify
    the resulting APNG has one frame per state with sane frame durations."""

    _DEMO_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _DEMO_OUTPUT.unlink(missing_ok=True)

    handler = TreemapEventHandler(
        [tmp_path],
        _DEMO_OUTPUT,
        width_px=800,
        height_px=600,
        font_size=12,
        colormap="tab20",
        cushion=True,
        animate=True,
    )

    def _h(path: Path, verb: str) -> None:
        handler._pending_highlights[str(path)] = verb

    PAUSE = 2.0

    # ── frame 1: empty directory ─────────────────────────────────────────
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 2: create src/ with two files ──────────────────────────────
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_bytes(b"x" * 5_000)
    _h(src / "main.py", "created")
    (src / "utils.py").write_bytes(b"x" * 3_000)
    _h(src / "utils.py", "created")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 3: add docs/ ───────────────────────────────────────────────
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_bytes(b"x" * 2_000)
    _h(docs / "README.md", "created")
    (docs / "api.md").write_bytes(b"x" * 1_500)
    _h(docs / "api.md", "created")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 4: add tests/ ──────────────────────────────────────────────
    tests = tmp_path / "tests"
    tests.mkdir()
    for i in range(4):
        p = tests / f"test_{i}.py"
        p.write_bytes(b"x" * (1_000 + i * 500))
        _h(p, "created")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 5: grow src/ + modify main.py ──────────────────────────────
    for name, sz in [("models.py", 10_000), ("api.py", 7_000), ("database.py", 15_000)]:
        p = src / name
        p.write_bytes(b"x" * sz)
        _h(p, "created")
    (src / "main.py").write_bytes(b"x" * 8_000)
    _h(src / "main.py", "modified")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 6: tweak src/ sizes ──────────────────────────────────────────
    (src / "main.py").write_bytes(b"x" * 8_500)
    _h(src / "main.py", "modified")
    (src / "utils.py").write_bytes(b"x" * 3_400)
    _h(src / "utils.py", "modified")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 7: add data/ with large files ──────────────────────────────
    data = tmp_path / "data"
    data.mkdir()
    for name, sz in [("dataset.csv", 60_000), ("model.pkl", 40_000), ("config.json", 5_000)]:
        p = data / name
        p.write_bytes(b"x" * sz)
        _h(p, "created")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 8: small edits to data/ and docs/ ─────────────────────────
    (data / "config.json").write_bytes(b"x" * 5_800)
    _h(data / "config.json", "modified")
    (docs / "README.md").write_bytes(b"x" * 2_300)
    _h(docs / "README.md", "modified")
    (data / "dataset.csv").write_bytes(b"x" * 62_000)
    _h(data / "dataset.csv", "modified")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 9: delete README.md, add vendor/ ────────────────────────────
    (docs / "README.md").unlink()
    _h(docs / "README.md", "deleted")
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    for name in ["requests", "flask", "sqlalchemy"]:
        lib = vendor / name
        lib.mkdir()
        p = lib / "__init__.py"
        p.write_bytes(b"x" * (8_000 + len(name) * 1_000))
        _h(p, "created")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 10: delete all test files ──────────────────────────────────
    for i in range(4):
        p = tests / f"test_{i}.py"
        p.unlink()
        _h(p, "deleted")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 11: rename database.py → db.py, api.py → server.py ────────
    for old_name, new_name in [("database.py", "db.py"), ("api.py", "server.py")]:
        old = src / old_name
        new = src / new_name
        old.rename(new)
        _h(old, "deleted")
        _h(new, "created")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 12: small edits to several files ───────────────────────────
    (src / "models.py").write_bytes(b"x" * 10_800)
    _h(src / "models.py", "modified")
    (src / "db.py").write_bytes(b"x" * 14_200)
    _h(src / "db.py", "modified")
    (data / "config.json").write_bytes(b"x" * 6_200)
    _h(data / "config.json", "modified")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 13: delete model.pkl, modify dataset.csv ───────────────────
    (data / "model.pkl").unlink()
    _h(data / "model.pkl", "deleted")
    (data / "dataset.csv").write_bytes(b"x" * 80_000)
    _h(data / "dataset.csv", "modified")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 14: move flask to src/, delete requests ────────────────────
    old_flask = vendor / "flask" / "__init__.py"
    new_flask_dir = src / "flask_app"
    new_flask_dir.mkdir()
    new_flask = new_flask_dir / "__init__.py"
    old_flask.rename(new_flask)
    _h(old_flask, "deleted")
    _h(new_flask, "created")
    (vendor / "requests" / "__init__.py").unlink()
    _h(vendor / "requests" / "__init__.py", "deleted")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 15: modify remaining vendor + src files ────────────────────
    (vendor / "sqlalchemy" / "__init__.py").write_bytes(b"x" * 20_000)
    _h(vendor / "sqlalchemy" / "__init__.py", "modified")
    (src / "main.py").write_bytes(b"x" * 9_200)
    _h(src / "main.py", "modified")
    (src / "server.py").write_bytes(b"x" * 7_600)
    _h(src / "server.py", "modified")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frame 16: delete remaining docs, add config files ────────────────
    (docs / "api.md").unlink()
    _h(docs / "api.md", "deleted")
    (tmp_path / "Makefile").write_bytes(b"x" * 500)
    _h(tmp_path / "Makefile", "created")
    (tmp_path / ".gitignore").write_bytes(b"x" * 200)
    _h(tmp_path / ".gitignore", "created")
    handler._regenerate()
    time.sleep(PAUSE)

    # ── frames 17–20: tear everything down to empty ──────────────────────
    for f in data.iterdir():
        f.unlink()
        _h(f, "deleted")
    handler._regenerate()
    time.sleep(PAUSE)

    for lib_dir in list(vendor.iterdir()):
        for f in lib_dir.iterdir():
            f.unlink()
            _h(f, "deleted")
    handler._regenerate()
    time.sleep(PAUSE)

    for f in list(src.iterdir()):
        if f.is_file():
            f.unlink()
            _h(f, "deleted")
        elif f.is_dir():
            for ff in f.iterdir():
                ff.unlink()
                _h(ff, "deleted")
    handler._regenerate()
    time.sleep(PAUSE)

    for f in tmp_path.iterdir():
        if f.is_file():
            f.unlink()
            _h(f, "deleted")
    handler._regenerate()

    # ── write APNG ────────────────────────────────────────────────────────
    handler.flush()

    n_expected = 20

    # ── verify ────────────────────────────────────────────────────────────
    img = Image.open(_DEMO_OUTPUT)
    n_frames = getattr(img, "n_frames", 1)
    assert getattr(img, "is_animated", False), "output is not an animated PNG"
    assert n_frames == n_expected, f"expected {n_expected} frames, got {n_frames}"

    for i, frame in enumerate(list(ImageSequence.Iterator(img))[:-1]):
        d = frame.info.get("duration", 0)
        assert d >= 500, f"frame {i} has suspicious duration {d} ms"

    print(f"\n  APNG: {_DEMO_OUTPUT} ({n_frames} frames)")
    print("  Open in Safari, Firefox, or Preview to view the animation.")


# ── MP4 output ────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not found")
def test_watch_animate_mp4(tmp_path: Path) -> None:
    """Watch handler writes a valid .mp4 file when output has .mp4 extension."""
    out = tmp_path / "demo.mp4"

    handler = TreemapEventHandler(
        [tmp_path],
        out,
        width_px=200,
        height_px=150,
        font_size=12,
        colormap="tab20",
        cushion=True,
        animate=True,
        crf=28,
    )

    (tmp_path / "a.py").write_bytes(b"x" * 4_000)
    handler._regenerate()

    (tmp_path / "b.py").write_bytes(b"x" * 2_000)
    handler._regenerate()

    handler.flush()

    assert out.exists()
    assert out.stat().st_size > 0


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


# ---------------------------------------------------------------------------
# log=True path
# ---------------------------------------------------------------------------


def test_watch_log_scale(tmp_path: Path) -> None:
    """_regenerate with log=True does not crash and produces a PNG."""
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
        log=True,
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


def _handler(tmp_path: Path, out: Path, **kw) -> TreemapEventHandler:
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
    assert handler._pending_highlights.get(str(tmp_path / "new.py")) == "created"


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
    assert handler._pending_highlights.get(str(tmp_path / "gone.py")) == "deleted"


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_on_modified_file(tmp_path: Path) -> None:
    out = tmp_path / "t.png"
    f = tmp_path / "mod.py"
    f.write_bytes(b"x" * 20)
    handler = _handler(tmp_path, out)
    event = FileModifiedEvent(str(f))
    handler.on_modified(event)
    handler._timer.cancel()
    assert handler._pending_highlights.get(str(f)) == "modified"


@pytest.mark.skipif(not _watchdog_available, reason="watchdog not installed")
def test_on_moved_file(tmp_path: Path) -> None:
    out = tmp_path / "t.png"
    src = tmp_path / "old.py"
    dst = tmp_path / "new.py"
    handler = _handler(tmp_path, out)
    event = FileMovedEvent(str(src), str(dst))
    handler.on_moved(event)
    handler._timer.cancel()
    assert handler._pending_highlights.get(str(src)) == "deleted"
    assert handler._pending_highlights.get(str(dst)) == "created"
