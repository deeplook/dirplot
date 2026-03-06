"""Shared pytest fixtures."""

from pathlib import Path

import pytest


@pytest.fixture()
def sample_tree(tmp_path: Path) -> Path:
    """A small directory tree for testing.

    Structure::

        root/
        ├── docs/
        │   └── guide.md
        ├── src/
        │   ├── app.py   (100 bytes)
        │   └── util.py  (200 bytes)
        └── README.md    (50 bytes)
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()

    (tmp_path / "docs" / "guide.md").write_bytes(b"x" * 80)
    (tmp_path / "src" / "app.py").write_bytes(b"x" * 100)
    (tmp_path / "src" / "util.py").write_bytes(b"x" * 200)
    (tmp_path / "README.md").write_bytes(b"x" * 50)

    return tmp_path
