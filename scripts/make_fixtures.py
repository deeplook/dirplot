#!/usr/bin/env python3
"""Generate archive fixtures for the test suite.

Creates tests/fixtures/ with sample.<ext> in every format supported by
dirplot.archives, built from the same tree as the ``sample_tree`` pytest
fixture:

    README.md       (50 B)
    docs/
        guide.md    (80 B)
    src/
        app.py      (100 B)
        util.py     (200 B)
    .hidden         (10 B)   ← present in archive; skipped by scanner

Run once locally to refresh the on-disk fixtures:

    python scripts/make_fixtures.py

The pytest ``sample_archives`` session fixture in tests/conftest.py
generates the same files in a temp directory automatically, so running
this script is not required for CI.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

# Mirrors the sample_tree fixture in tests/conftest.py plus a dotfile.
SAMPLE_FILES: list[tuple[str, bytes]] = [
    ("README.md", b"x" * 50),
    ("docs/guide.md", b"x" * 80),
    ("src/app.py", b"x" * 100),
    ("src/util.py", b"x" * 200),
    (".hidden", b"x" * 10),
]


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in SAMPLE_FILES:
            zf.writestr(name, data)
    return buf.getvalue()


def _tar_bytes(mode: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(mode=mode, fileobj=buf) as tf:
        for name, data in SAMPLE_FILES:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _write_7z(dest: Path) -> None:
    import py7zr

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, data in SAMPLE_FILES:
            f = tmp_path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        with py7zr.SevenZipFile(dest, "w") as sz:
            for name, _ in SAMPLE_FILES:
                sz.write(tmp_path / name, name)


def _write_rar(dest: Path) -> bool:
    rar = shutil.which("rar")
    if not rar:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, data in SAMPLE_FILES:
            f = tmp_path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        subprocess.run(
            [rar, "a", "-r", str(dest), "."], cwd=tmp_path, check=True, capture_output=True
        )
    return True


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    zip_bytes = _zip_bytes()

    tasks: list[tuple[str, bytes | None]] = [
        # ZIP and synonyms (same bytes, different extensions)
        ("sample.zip", zip_bytes),
        ("sample.jar", zip_bytes),
        ("sample.war", zip_bytes),
        ("sample.ear", zip_bytes),
        ("sample.whl", zip_bytes),
        ("sample.apk", zip_bytes),
        ("sample.epub", zip_bytes),
        ("sample.xpi", zip_bytes),
        # tar variants
        ("sample.tar", _tar_bytes("w:")),
        ("sample.tar.gz", _tar_bytes("w:gz")),
        ("sample.tgz", _tar_bytes("w:gz")),
        ("sample.tar.bz2", _tar_bytes("w:bz2")),
        ("sample.tbz2", _tar_bytes("w:bz2")),
        ("sample.tar.xz", _tar_bytes("w:xz")),
        ("sample.txz", _tar_bytes("w:xz")),
    ]

    for filename, data in tasks:
        dest = FIXTURES_DIR / filename
        assert data is not None
        dest.write_bytes(data)
        print(f"  {filename:30s}  {dest.stat().st_size:>8,} B")

    # 7z
    dest_7z = FIXTURES_DIR / "sample.7z"
    _write_7z(dest_7z)
    print(f"  {'sample.7z':30s}  {dest_7z.stat().st_size:>8,} B")

    # RAR
    dest_rar = FIXTURES_DIR / "sample.rar"
    if _write_rar(dest_rar):
        print(f"  {'sample.rar':30s}  {dest_rar.stat().st_size:>8,} B")
    else:
        print(f"  {'sample.rar':30s}  skipped (rar CLI not found)", file=sys.stderr)

    print(f"\nFixtures written to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
