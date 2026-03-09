"""Shared pytest fixtures."""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Tree used by sample_tree and sample_archives — keep in sync.
# ---------------------------------------------------------------------------
_SAMPLE_FILES: list[tuple[str, bytes]] = [
    ("README.md", b"x" * 50),
    ("docs/guide.md", b"x" * 80),
    ("src/app.py", b"x" * 100),
    ("src/util.py", b"x" * 200),
    (".hidden", b"x" * 10),
]


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in _SAMPLE_FILES:
            zf.writestr(name, data)
    return buf.getvalue()


def _tar_bytes(mode: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(mode=mode, fileobj=buf) as tf:
        for name, data in _SAMPLE_FILES:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture(scope="session")
def sample_archives(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Session-scoped fixture: one archive per supported format → {ext: Path}.

    Mirrors the logic in scripts/make_fixtures.py so tests always work in CI
    without running the script first.
    """
    base = tmp_path_factory.mktemp("fixtures")
    archives: dict[str, Path] = {}

    zip_data = _zip_bytes()

    # ZIP and synonyms
    for ext in (".zip", ".jar", ".war", ".ear", ".whl", ".apk", ".epub", ".xpi"):
        p = base / f"sample{ext}"
        p.write_bytes(zip_data)
        archives[ext] = p

    # tar variants
    for ext, mode in [
        (".tar", "w:"),
        (".tar.gz", "w:gz"),
        (".tgz", "w:gz"),
        (".tar.bz2", "w:bz2"),
        (".tbz2", "w:bz2"),
        (".tar.xz", "w:xz"),
        (".txz", "w:xz"),
    ]:
        p = base / f"sample{ext}"
        p.write_bytes(_tar_bytes(mode))
        archives[ext] = p

    # 7z
    import py7zr

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, data in _SAMPLE_FILES:
            f = tmp_path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        p = base / "sample.7z"
        with py7zr.SevenZipFile(p, "w") as sz:
            for name, _ in _SAMPLE_FILES:
                sz.write(tmp_path / name, name)
        archives[".7z"] = p

    # RAR (only if the rar CLI is available)
    rar_cli = shutil.which("rar")
    if rar_cli:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name, data in _SAMPLE_FILES:
                f = tmp_path / name
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(data)
            p = base / "sample.rar"
            subprocess.run(
                [rar_cli, "a", "-r", str(p), "."], cwd=tmp_path, check=True, capture_output=True
            )
            archives[".rar"] = p

    return archives


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
