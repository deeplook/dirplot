"""Tests for Google Drive scanning via the gog CLI."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from dirplot.gdrive import (
    _entries_to_tree,
    build_tree_gdrive,
    is_gdrive_path,
    parse_gdrive_path,
)

# ---------------------------------------------------------------------------
# URI helpers
# ---------------------------------------------------------------------------


def test_is_gdrive_path_root() -> None:
    assert is_gdrive_path("gdrive://")


def test_is_gdrive_path_folder_id() -> None:
    assert is_gdrive_path("gdrive://1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms")


@pytest.mark.parametrize("path", ["/local/path", "s3://bucket", "docker://c:/app", "github://o/r"])
def test_is_gdrive_path_non_gdrive(path: str) -> None:
    assert not is_gdrive_path(path)


def test_parse_gdrive_path_root() -> None:
    assert parse_gdrive_path("gdrive://") is None


def test_parse_gdrive_path_root_trailing_slash() -> None:
    assert parse_gdrive_path("gdrive:///") is None


def test_parse_gdrive_path_folder_id() -> None:
    fid = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
    assert parse_gdrive_path(f"gdrive://{fid}") == fid


# ---------------------------------------------------------------------------
# _entries_to_tree
# ---------------------------------------------------------------------------


def test_entries_to_tree_flat() -> None:
    entries = [
        ("report.pdf", 2000, False),
        ("notes.txt", 500, False),
    ]
    node = _entries_to_tree("My Drive", entries)
    assert node.is_dir
    assert node.name == "My Drive"
    assert node.size == 2500
    assert {c.name for c in node.children} == {"report.pdf", "notes.txt"}


def test_entries_to_tree_extensions() -> None:
    entries = [
        ("data.csv", 1000, False),
        ("Makefile", 100, False),
    ]
    node = _entries_to_tree("My Drive", entries)
    csv_node = next(c for c in node.children if c.name == "data.csv")
    mk_node = next(c for c in node.children if c.name == "Makefile")
    assert csv_node.extension == ".csv"
    assert mk_node.extension == "(no ext)"


def test_entries_to_tree_nested() -> None:
    entries = [
        ("Projects", 0, True),
        ("Projects/app.py", 300, False),
        ("README.md", 50, False),
    ]
    node = _entries_to_tree("My Drive", entries)
    assert node.size == 350
    projects = next(c for c in node.children if c.name == "Projects")
    assert projects.is_dir
    assert projects.size == 300
    assert projects.children[0].name == "app.py"


def test_entries_to_tree_missing_intermediate_dirs() -> None:
    """Items may appear without their parent folder being listed explicitly."""
    entries = [("a/b/file.txt", 100, False)]
    node = _entries_to_tree("My Drive", entries)
    a = next(c for c in node.children if c.name == "a")
    assert a.is_dir
    b = next(c for c in a.children if c.name == "b")
    assert b.is_dir
    assert b.children[0].name == "file.txt"


# ---------------------------------------------------------------------------
# build_tree_gdrive (mocked subprocess)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_gog_which(request: pytest.FixtureRequest):
    """Pretend gog is installed for all build_tree_gdrive tests except the not-found test."""
    if request.node.name == "test_build_tree_gdrive_gog_not_found":
        yield
        return
    with patch("shutil.which", return_value="/usr/local/bin/gog"):
        yield


def _gog_response(items: list[dict], truncated: bool = False) -> MagicMock:
    """Build a mock subprocess.CompletedProcess with gog JSON output."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps({"items": items, "truncated": truncated})
    result.stderr = ""
    return result


_FOLDER_MIME = "application/vnd.google-apps.folder"
_DOC_MIME = "application/vnd.google-apps.document"


def test_build_tree_gdrive_flat() -> None:
    items = [
        {"path": "report.pdf", "mimeType": "application/pdf", "size": 2000, "depth": 1},
        {"path": "notes.txt", "mimeType": "text/plain", "size": 500, "depth": 1},
    ]
    with patch("subprocess.run", return_value=_gog_response(items)):
        node = build_tree_gdrive()
    assert node.is_dir
    assert node.name == "My Drive"
    assert node.size == 2500
    assert {c.name for c in node.children} == {"report.pdf", "notes.txt"}


def test_build_tree_gdrive_parses_string_size() -> None:
    items = [
        {"path": "report.pdf", "mimeType": "application/pdf", "size": "2000", "depth": 1},
    ]
    with patch("subprocess.run", return_value=_gog_response(items)):
        node = build_tree_gdrive()
    report = next(c for c in node.children if c.name == "report.pdf")
    assert report.size == 2000
    assert node.size == 2000


def test_build_tree_gdrive_nested() -> None:
    items = [
        {"path": "Projects", "mimeType": _FOLDER_MIME, "size": 0, "depth": 1},
        {"path": "Projects/app.py", "mimeType": "text/x-python", "size": 1200, "depth": 2},
        {"path": "README.md", "mimeType": "text/plain", "size": 300, "depth": 1},
    ]
    with patch("subprocess.run", return_value=_gog_response(items)):
        node = build_tree_gdrive()
    assert node.size == 1500
    projects = next(c for c in node.children if c.name == "Projects")
    assert projects.is_dir
    assert projects.size == 1200


def test_build_tree_gdrive_native_formats_get_size_1() -> None:
    """Google-native formats (Docs, Sheets, …) have size=0 — shown as 1 byte."""
    items = [
        {"path": "doc.gdoc", "mimeType": _DOC_MIME, "size": 0, "depth": 1},
        {"path": "real.pdf", "mimeType": "application/pdf", "size": 500, "depth": 1},
    ]
    with patch("subprocess.run", return_value=_gog_response(items)):
        node = build_tree_gdrive()
    doc = next(c for c in node.children if c.name == "doc.gdoc")
    assert doc.size == 1


def test_build_tree_gdrive_skips_dotfiles() -> None:
    items = [
        {"path": ".hidden", "mimeType": "text/plain", "size": 100, "depth": 1},
        {"path": "visible.txt", "mimeType": "text/plain", "size": 200, "depth": 1},
    ]
    with patch("subprocess.run", return_value=_gog_response(items)):
        node = build_tree_gdrive()
    names = {c.name for c in node.children}
    assert "visible.txt" in names
    assert ".hidden" not in names


def test_build_tree_gdrive_exclude() -> None:
    items = [
        {"path": "keep.py", "mimeType": "text/x-python", "size": 100, "depth": 1},
        {"path": "skip.py", "mimeType": "text/x-python", "size": 200, "depth": 1},
    ]
    with patch("subprocess.run", return_value=_gog_response(items)):
        node = build_tree_gdrive(exclude=frozenset({"skip.py"}))
    names = {c.name for c in node.children}
    assert "keep.py" in names
    assert "skip.py" not in names


def test_build_tree_gdrive_folder_id() -> None:
    """Folder ID is passed as --parent to gog."""
    fid = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
    calls: list[list[str]] = []

    def _capture(cmd, **kwargs):
        calls.append(list(cmd))
        return _gog_response([])

    with patch("subprocess.run", side_effect=_capture):
        build_tree_gdrive(fid)

    assert "--parent" in calls[0]
    assert fid in calls[0]


def test_build_tree_gdrive_root_no_parent_flag() -> None:
    """Root scan (folder_id=None) must not pass --parent to gog."""
    calls: list[list[str]] = []

    def _capture(cmd, **kwargs):
        calls.append(list(cmd))
        return _gog_response([])

    with patch("subprocess.run", side_effect=_capture):
        build_tree_gdrive()

    assert "--parent" not in calls[0]


def test_build_tree_gdrive_depth_passed() -> None:
    calls: list[list[str]] = []

    def _capture(cmd, **kwargs):
        calls.append(list(cmd))
        return _gog_response([])

    with patch("subprocess.run", side_effect=_capture):
        build_tree_gdrive(depth=3)

    assert "--depth" in calls[0]
    idx = calls[0].index("--depth")
    assert calls[0][idx + 1] == "3"


def test_build_tree_gdrive_unlimited_depth_uses_zero() -> None:
    """dirplot depth=None maps to gog --depth 0 (unlimited)."""
    calls: list[list[str]] = []

    def _capture(cmd, **kwargs):
        calls.append(list(cmd))
        return _gog_response([])

    with patch("subprocess.run", side_effect=_capture):
        build_tree_gdrive(depth=None)

    idx = calls[0].index("--depth")
    assert calls[0][idx + 1] == "0"


def test_build_tree_gdrive_gog_not_found() -> None:
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(FileNotFoundError, match="gog"),
    ):
        build_tree_gdrive()


def test_build_tree_gdrive_gog_failure() -> None:
    bad = MagicMock()
    bad.returncode = 1
    bad.stdout = ""
    bad.stderr = "auth required"
    with (
        patch("subprocess.run", return_value=bad),
        pytest.raises(OSError, match="gog drive tree failed"),
    ):
        build_tree_gdrive()


def test_build_tree_gdrive_invalid_json() -> None:
    bad = MagicMock()
    bad.returncode = 0
    bad.stdout = "not json"
    bad.stderr = ""
    with (
        patch("subprocess.run", return_value=bad),
        pytest.raises(OSError, match="invalid JSON"),
    ):
        build_tree_gdrive()


def test_build_tree_gdrive_progress_reported() -> None:
    items = [
        {"path": f"file{i}.txt", "mimeType": "text/plain", "size": 100, "depth": 1}
        for i in range(101)
    ]
    progress: list[int] = [0]
    with patch("subprocess.run", return_value=_gog_response(items)):
        build_tree_gdrive(_progress=progress)
    assert progress[0] == 101
