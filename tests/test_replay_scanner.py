"""Tests for replay_scanner: event parsing, bucketing, applying, and frame rendering."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from dirplot.replay_scanner import (
    _render_replay_frame_worker,
    apply_events,
    bucket_events,
    parse_events,
    scan_to_flat,
)

# ---------------------------------------------------------------------------
# parse_events
# ---------------------------------------------------------------------------


def test_parse_events_basic(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"timestamp": 1.0, "type": "created", "path": "/a/b.py"})
        + "\n"
        + json.dumps({"timestamp": 2.0, "type": "modified", "path": "/a/c.py"})
        + "\n"
    )
    events = parse_events(log)
    assert len(events) == 2
    assert events[0] == (1.0, "created", "/a/b.py", "")
    assert events[1] == (2.0, "modified", "/a/c.py", "")


def test_parse_events_sorted(tmp_path: Path) -> None:
    """Events are returned sorted by timestamp regardless of file order."""
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"timestamp": 3.0, "type": "modified", "path": "/z"})
        + "\n"
        + json.dumps({"timestamp": 1.0, "type": "created", "path": "/a"})
        + "\n"
        + json.dumps({"timestamp": 2.0, "type": "deleted", "path": "/b"})
        + "\n"
    )
    events = parse_events(log)
    assert [e[0] for e in events] == [1.0, 2.0, 3.0]


def test_parse_events_blank_lines_skipped(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log.write_text(
        "\n"
        + json.dumps({"timestamp": 1.0, "type": "created", "path": "/a"})
        + "\n"
        + "   \n"
        + json.dumps({"timestamp": 2.0, "type": "deleted", "path": "/b"})
        + "\n"
    )
    events = parse_events(log)
    assert len(events) == 2


def test_parse_events_dest_path(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"timestamp": 1.0, "type": "moved", "path": "/a", "dest_path": "/b"}) + "\n"
    )
    events = parse_events(log)
    assert events[0] == (1.0, "moved", "/a", "/b")


def test_parse_events_empty_file(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log.write_text("")
    assert parse_events(log) == []


# ---------------------------------------------------------------------------
# scan_to_flat
# ---------------------------------------------------------------------------


def test_scan_to_flat_basic(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x" * 100)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_bytes(b"x" * 200)
    files = scan_to_flat(tmp_path)
    assert files["a.py"] == 100
    assert files["sub/b.py"] == 200


def test_scan_to_flat_forward_slashes(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_bytes(b"x" * 50)
    files = scan_to_flat(tmp_path)
    assert all("/" in k or "/" not in k for k in files)
    assert "sub/c.txt" in files


def test_scan_to_flat_excludes_dir(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_bytes(b"x" * 10)
    excl = tmp_path / "excluded"
    excl.mkdir()
    (excl / "secret.py").write_bytes(b"x" * 10)
    files = scan_to_flat(tmp_path, exclude=frozenset([excl.resolve()]))
    assert "keep.py" in files
    assert not any("excluded" in k for k in files)


def test_scan_to_flat_oserror_fallback(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_bytes(b"x" * 42)
    with patch("os.walk") as mock_walk:
        mock_walk.return_value = [(str(tmp_path), [], ["f.py"])]
        with patch.object(Path, "stat", side_effect=OSError("no access")):
            files = scan_to_flat(tmp_path)
    assert files.get("f.py") == 1


# ---------------------------------------------------------------------------
# bucket_events
# ---------------------------------------------------------------------------


def test_bucket_events_empty() -> None:
    assert bucket_events([], 60.0) == []


def test_bucket_events_single_bucket() -> None:
    events = [(1.0, "created", "/a", ""), (2.0, "modified", "/b", "")]
    buckets = bucket_events(events, 60.0)
    assert len(buckets) == 1
    assert buckets[0][0] == 1.0
    assert len(buckets[0][1]) == 2


def test_bucket_events_multiple_buckets() -> None:
    events = [
        (0.0, "created", "/a", ""),
        (30.0, "modified", "/b", ""),
        (70.0, "created", "/c", ""),
        (75.0, "deleted", "/d", ""),
    ]
    buckets = bucket_events(events, 60.0)
    assert len(buckets) == 2
    assert len(buckets[0][1]) == 2
    assert len(buckets[1][1]) == 2


def test_bucket_events_boundary() -> None:
    """An event exactly at bucket_start + bucket_size starts a new bucket."""
    events = [(0.0, "created", "/a", ""), (60.0, "modified", "/b", "")]
    buckets = bucket_events(events, 60.0)
    assert len(buckets) == 2


# ---------------------------------------------------------------------------
# apply_events
# ---------------------------------------------------------------------------


def test_apply_events_created(tmp_path: Path) -> None:
    f = tmp_path / "new.py"
    f.write_bytes(b"x" * 50)
    files: dict[str, int] = {}
    highlights = apply_events(files, tmp_path, [(1.0, "created", str(f), "")], frozenset())
    assert files["new.py"] == 50
    assert highlights[str(f)] == "created"


def test_apply_events_modified(tmp_path: Path) -> None:
    f = tmp_path / "existing.py"
    f.write_bytes(b"x" * 80)
    files = {"existing.py": 40}
    apply_events(files, tmp_path, [(1.0, "modified", str(f), "")], frozenset())
    assert files["existing.py"] == 80


def test_apply_events_deleted(tmp_path: Path) -> None:
    files = {"bye.py": 100}
    path_str = str(tmp_path / "bye.py")
    highlights = apply_events(files, tmp_path, [(1.0, "deleted", path_str, "")], frozenset())
    assert "bye.py" not in files
    assert highlights[path_str] == "deleted"


def test_apply_events_moved(tmp_path: Path) -> None:
    src = tmp_path / "old.py"
    dst = tmp_path / "new.py"
    dst.write_bytes(b"x" * 30)
    files = {"old.py": 30}
    apply_events(files, tmp_path, [(1.0, "moved", str(src), str(dst))], frozenset())
    assert "old.py" not in files
    assert files.get("new.py") == 30


def test_apply_events_outside_root_skipped(tmp_path: Path) -> None:
    other = tmp_path.parent / "other.py"
    files: dict[str, int] = {}
    apply_events(files, tmp_path, [(1.0, "created", str(other), "")], frozenset())
    assert not files


def test_apply_events_excluded_skipped(tmp_path: Path) -> None:
    f = tmp_path / "secret.py"
    f.write_bytes(b"x" * 10)
    files: dict[str, int] = {}
    apply_events(files, tmp_path, [(1.0, "created", str(f), "")], frozenset([f.resolve()]))
    assert not files


def test_apply_events_oserror_fallback(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    f.write_bytes(b"x" * 10)
    files: dict[str, int] = {}
    with patch.object(Path, "stat", side_effect=OSError("no access")):
        apply_events(files, tmp_path, [(1.0, "created", str(f), "")], frozenset())
    assert files.get("f.py") == 1


def test_apply_events_moved_dest_outside_root(tmp_path: Path) -> None:
    """Move where dest is outside root — old entry removed, nothing added."""
    src = tmp_path / "f.py"
    dest_outside = tmp_path.parent / "elsewhere.py"
    files = {"f.py": 50}
    apply_events(files, tmp_path, [(1.0, "moved", str(src), str(dest_outside))], frozenset())
    assert "f.py" not in files
    assert not any("elsewhere" in k for k in files)


# ---------------------------------------------------------------------------
# _render_replay_frame_worker
# ---------------------------------------------------------------------------


def test_render_replay_frame_worker(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x" * 100)
    (tmp_path / "b.md").write_bytes(b"x" * 50)
    files = {"a.py": 100, "b.md": 50}
    args = (
        str(tmp_path),  # root_str
        files,
        {},  # highlights
        time.time(),  # ts
        0,  # orig_i
        0.5,  # progress
        None,  # depth
        False,  # log_scale
        200,  # width_px
        150,  # height_px
        12,  # font_size
        "tab20",  # colormap
        False,  # cushion
        True,  # dark
    )
    orig_i, png_bytes, rect_map = _render_replay_frame_worker(args)
    assert orig_i == 0
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert isinstance(rect_map, dict)


def test_render_replay_frame_worker_log_scale(tmp_path: Path) -> None:
    (tmp_path / "big.py").write_bytes(b"x" * 10_000)
    (tmp_path / "small.py").write_bytes(b"x" * 10)
    files = {"big.py": 10_000, "small.py": 10}
    args = (
        str(tmp_path),
        files,
        {},
        time.time(),
        1,
        1.0,
        None,
        True,  # log_scale
        200,
        150,
        12,
        "tab20",
        False,  # cushion
        True,  # dark
    )
    orig_i, png_bytes, _ = _render_replay_frame_worker(args)
    assert orig_i == 1
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
