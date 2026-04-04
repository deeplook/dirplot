"""Tests for hg_scanner: log parsing, diff application, initial file listing."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dirplot.hg_scanner import hg_apply_diff, hg_initial_files, hg_log

pytestmark = pytest.mark.skipif(not shutil.which("hg"), reason="hg not found")


# ---------------------------------------------------------------------------
# hg_log — edge cases via mock
# ---------------------------------------------------------------------------


def test_hg_log_blank_lines_skipped() -> None:
    """Blank lines in hg log output do not produce entries."""
    mock_result = MagicMock()
    mock_result.stdout = "\nabc123 1700000000 -18000 first\n\ndef456 1700000001 0 second\n"
    with patch("subprocess.run", return_value=mock_result):
        commits = hg_log(Path("/fake/repo"))
    assert len(commits) == 2
    assert commits[0][0] == "abc123"
    assert commits[1][0] == "def456"


def test_hg_log_invalid_timestamp_falls_back_to_zero() -> None:
    """Non-numeric timestamp in hg log output → ts=0 (no crash)."""
    mock_result = MagicMock()
    mock_result.stdout = "abc123 NOT_A_NUMBER -18000 the subject\n"
    with patch("subprocess.run", return_value=mock_result):
        commits = hg_log(Path("/fake/repo"))
    assert commits[0][1] == 0


def test_hg_log_hgdate_two_token_format() -> None:
    """hgdate 'unix offset' format — only the unix timestamp is used."""
    mock_result = MagicMock()
    mock_result.stdout = "abc123 1700000000 -18000 First commit message\n"
    with patch("subprocess.run", return_value=mock_result):
        commits = hg_log(Path("/fake/repo"))
    assert len(commits) == 1
    assert commits[0][1] == 1700000000
    assert commits[0][2] == "First commit message"


def test_hg_log_subject_preserved() -> None:
    """Subject line with spaces is returned intact."""
    mock_result = MagicMock()
    mock_result.stdout = "abc 1700000000 0 Fix a nasty bug in parser\n"
    with patch("subprocess.run", return_value=mock_result):
        commits = hg_log(Path("/fake/repo"))
    assert commits[0][2] == "Fix a nasty bug in parser"


# ---------------------------------------------------------------------------
# hg_initial_files — mock subprocess, real filesystem
# ---------------------------------------------------------------------------


def _make_archive(tmp_path: Path, structure: dict[str, int]) -> Path:
    """Create a fake hg archive tree inside tmp_path and return the tmpdir root."""
    # hg archive creates: {tmpdir}/archive/{prefix}/ with files inside.
    prefix_dir = tmp_path / "archive" / "repo-0"
    for rel_path, size in structure.items():
        full = prefix_dir / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(b"x" * size)
    return tmp_path


def test_hg_initial_files_basic(tmp_path: Path) -> None:
    """Files in the archive prefix dir are collected with correct sizes."""
    _make_archive(tmp_path, {"hello.py": 42, "subdir/world.py": 20})
    mock_proc = MagicMock()

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("tempfile.TemporaryDirectory") as mock_td,
    ):
        mock_td.return_value.__enter__.return_value = str(tmp_path)
        mock_td.return_value.__exit__.return_value = False
        files = hg_initial_files(Path("/repo"), "abc123")

    assert "hello.py" in files
    assert files["hello.py"] == 42
    assert "subdir/world.py" in files
    assert files["subdir/world.py"] == 20


def test_hg_initial_files_skips_hg_archival(tmp_path: Path) -> None:
    """.hg_archival.txt added by hg archive is excluded from results."""
    _make_archive(tmp_path, {".hg_archival.txt": 100, "main.py": 10})
    mock_proc = MagicMock()

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("tempfile.TemporaryDirectory") as mock_td,
    ):
        mock_td.return_value.__enter__.return_value = str(tmp_path)
        mock_td.return_value.__exit__.return_value = False
        files = hg_initial_files(Path("/repo"), "abc123")

    assert ".hg_archival.txt" not in files
    assert "main.py" in files


def test_hg_initial_files_excludes_top_level_dir(tmp_path: Path) -> None:
    """Top-level directory in the exclude set is omitted."""
    _make_archive(tmp_path, {"vendor/lib.py": 5, "src/app.py": 8})
    mock_proc = MagicMock()

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("tempfile.TemporaryDirectory") as mock_td,
    ):
        mock_td.return_value.__enter__.return_value = str(tmp_path)
        mock_td.return_value.__exit__.return_value = False
        files = hg_initial_files(Path("/repo"), "abc123", exclude=frozenset(["vendor"]))

    assert "vendor/lib.py" not in files
    assert "src/app.py" in files


# ---------------------------------------------------------------------------
# hg_apply_diff — status types via mock
# ---------------------------------------------------------------------------


def _status_result(stdout: str) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    return m


def _cat_result(content: bytes) -> MagicMock:
    m = MagicMock()
    m.stdout = content
    return m


def test_hg_apply_diff_added() -> None:
    status_out = "A new_file.py\n"
    files: dict[str, int] = {}
    with patch(
        "subprocess.run",
        side_effect=[_status_result(status_out), _cat_result(b"x" * 55)],
    ):
        highlights = hg_apply_diff(Path("/repo"), files, "prev", "curr")
    assert files.get("new_file.py") == 55
    assert highlights.get("/repo/new_file.py") == "created"


def test_hg_apply_diff_modified() -> None:
    status_out = "M existing.py\n"
    files = {"existing.py": 10}
    with patch(
        "subprocess.run",
        side_effect=[_status_result(status_out), _cat_result(b"y" * 99)],
    ):
        highlights = hg_apply_diff(Path("/repo"), files, "prev", "curr")
    assert files.get("existing.py") == 99
    assert highlights.get("/repo/existing.py") == "modified"


def test_hg_apply_diff_deleted() -> None:
    status_out = "R gone.py\n"
    files = {"gone.py": 50}
    with patch("subprocess.run", return_value=_status_result(status_out)):
        highlights = hg_apply_diff(Path("/repo"), files, "prev", "curr")
    assert "gone.py" not in files
    assert highlights.get("/repo/gone.py") == "deleted"


def test_hg_apply_diff_renamed() -> None:
    status_out = "A new.py\n  old.py\nR old.py\n"
    files = {"old.py": 30}
    with patch(
        "subprocess.run",
        side_effect=[_status_result(status_out), _cat_result(b"z" * 30)],
    ):
        highlights = hg_apply_diff(Path("/repo"), files, "prev", "curr")
    assert "old.py" not in files
    assert files.get("new.py") == 30
    assert highlights.get("/repo/old.py") == "deleted"
    assert highlights.get("/repo/new.py") == "created"


def test_hg_apply_diff_excluded() -> None:
    status_out = "A excl/secret.py\nM excl/other.py\nR excl/gone.py\n"
    files: dict[str, int] = {"excl/gone.py": 1}
    with patch("subprocess.run", return_value=_status_result(status_out)):
        highlights = hg_apply_diff(
            Path("/repo"), files, "prev", "curr", exclude=frozenset(["excl"])
        )
    assert not highlights
    # gone.py stays because its top-level dir is excluded
    assert "excl/gone.py" in files


def test_hg_apply_diff_blank_lines_skipped() -> None:
    status_out = "\nA valid.py\n\n"
    files: dict[str, int] = {}
    with patch(
        "subprocess.run",
        side_effect=[_status_result(status_out), _cat_result(b"a" * 7)],
    ):
        hg_apply_diff(Path("/repo"), files, "prev", "curr")
    assert "valid.py" in files


def test_hg_apply_diff_rename_r_line_not_double_deleted() -> None:
    """The R line for a rename source must not emit a second 'deleted' highlight."""
    status_out = "A new.py\n  old.py\nR old.py\n"
    files = {"old.py": 20}
    with patch(
        "subprocess.run",
        side_effect=[_status_result(status_out), _cat_result(b"x" * 20)],
    ):
        highlights = hg_apply_diff(Path("/repo"), files, "prev", "curr")
    # old.py appears exactly once in highlights as 'deleted'
    deleted_entries = [k for k, v in highlights.items() if v == "deleted"]
    assert len(deleted_entries) == 1
