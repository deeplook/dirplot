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


def _write_bsdtar(dest: Path, fmt: str) -> bool:
    """Write an archive using bsdtar (libarchive CLI). Returns False if bsdtar is absent."""
    bsdtar = shutil.which("bsdtar")
    if not bsdtar:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, data in SAMPLE_FILES:
            f = tmp_path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        if fmt == "iso9660":
            subprocess.run(
                [bsdtar, "-cf", str(dest), "--format", fmt, "-C", str(tmp_path), "."],
                check=True,
                capture_output=True,
            )
        elif fmt == "zstd":
            # tar + zstd: --zstd is a compression filter, not a --format value
            names = [name for name, _ in SAMPLE_FILES]
            subprocess.run(
                [bsdtar, "-cf", str(dest), "--zstd"] + names,
                cwd=str(tmp_path),
                check=True,
                capture_output=True,
            )
        else:
            names = [name for name, _ in SAMPLE_FILES]
            subprocess.run(
                [bsdtar, "-cf", str(dest), "--format", fmt] + names,
                cwd=str(tmp_path),
                check=True,
                capture_output=True,
            )
    return True


def _write_rpm(dest: Path) -> bool:
    """Write a minimal RPM to *dest* using rpmbuild. Returns False if unavailable.

    rpmbuild is available on Linux (rpm-build package) but not on macOS by default.
    libarchive can read RPM but not write it, so we use the rpmbuild CLI here.
    """
    rpmbuild = shutil.which("rpmbuild")
    if not rpmbuild:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Build tree under BUILDROOT as required by rpmbuild
        buildroot = tmp_path / "BUILDROOT" / "sample-1.0-1.noarch"
        for name, data in SAMPLE_FILES:
            f = buildroot / name.lstrip("/")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        spec = tmp_path / "sample.spec"
        spec.write_text(
            "%define _topdir {tmp}\n"
            "%define _rpmdir {tmp}/RPMS\n"
            "%define _builddir {tmp}/BUILD\n"
            "%define _srcrpmdir {tmp}/SRPMS\n"
            "%define _build_name_fmt %%{{NAME}}-%%{{VERSION}}-%%{{RELEASE}}.%%{{ARCH}}.rpm\n"
            "Name: sample\n"
            "Version: 1.0\n"
            "Release: 1\n"
            "Summary: dirplot test fixture\n"
            "License: MIT\n"
            "BuildArch: noarch\n"
            "%description\ndirplot test fixture\n"
            "%files\n"
            + "".join(f"/{name}\n" for name, _ in SAMPLE_FILES if not name.startswith("."))
            + "%changelog\n",
        ).format(tmp=tmp_path)
        subprocess.run(
            [rpmbuild, "-bb", "--buildroot", str(buildroot), str(spec)],
            check=True,
            capture_output=True,
        )
        rpms = list((tmp_path / "RPMS").rglob("*.rpm"))
        if not rpms:
            return False
        dest.write_bytes(rpms[0].read_bytes())
    return True


def _write_ar(dest: Path) -> None:
    """Write a Unix ar archive using the `ar` CLI (always available via binutils/Xcode CLT)."""
    ar = shutil.which("ar")
    assert ar, "`ar` not found — install Xcode Command Line Tools or binutils"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        members = []
        for name, data in SAMPLE_FILES:
            # ar archives are flat; use basename only (slashes not supported)
            flat_name = name.replace("/", "_")
            f = tmp_path / flat_name
            f.write_bytes(data)
            members.append(flat_name)
        subprocess.run(
            [ar, "rcs", str(dest)] + members,
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )


def _write_cab(dest: Path) -> bool:
    """Write a Cabinet archive using gcab (Linux) or makecab (Windows). Returns False if absent."""
    gcab = shutil.which("gcab") or shutil.which("makecab")
    if not gcab:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, data in SAMPLE_FILES:
            f = tmp_path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        flat_files = []
        for name, _ in SAMPLE_FILES:
            flat_files.append(str(tmp_path / name))
        subprocess.run(
            [gcab, "-c", str(dest)] + flat_files,
            check=True,
            capture_output=True,
        )
    return True


def _write_lha(dest: Path) -> bool:
    """Write an LHA archive using the `lha` CLI. Returns False if absent.

    Note: lhasa (common on Linux) is extract-only. The `lha` package
    (brew install lha on macOS, lhamt on some Linux distros) can create archives.
    """
    lha = shutil.which("lha")
    if not lha:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, data in SAMPLE_FILES:
            f = tmp_path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        subprocess.run(
            [lha, "a", str(dest)] + [name for name, _ in SAMPLE_FILES],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
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
        ("sample.nupkg", zip_bytes),
        ("sample.vsix", zip_bytes),
        ("sample.ipa", zip_bytes),
        ("sample.aab", zip_bytes),
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

    # libarchive-based formats (require bsdtar)
    for filename, fmt in [
        ("sample.cpio", "cpio"),
        ("sample.xar", "xar"),
        ("sample.iso", "iso9660"),
        ("sample.tar.zst", "zstd"),
        ("sample.tzst", "zstd"),
    ]:
        dest_la = FIXTURES_DIR / filename
        if _write_bsdtar(dest_la, fmt):
            print(f"  {filename:30s}  {dest_la.stat().st_size:>8,} B")
        else:
            print(f"  {filename:30s}  skipped (bsdtar CLI not found)", file=sys.stderr)

    # RPM (requires rpmbuild, typically available on Linux)
    dest_rpm = FIXTURES_DIR / "sample.rpm"
    if _write_rpm(dest_rpm):
        print(f"  {'sample.rpm':30s}  {dest_rpm.stat().st_size:>8,} B")
    else:
        print(f"  {'sample.rpm':30s}  skipped (rpmbuild not found)", file=sys.stderr)

    # .a — Unix static library (ar archive); `ar` is always available (binutils / Xcode CLT)
    dest_a = FIXTURES_DIR / "sample.a"
    _write_ar(dest_a)
    print(f"  {'sample.a':30s}  {dest_a.stat().st_size:>8,} B")

    # .cab — Microsoft Cabinet (gcab on Linux, typically absent on macOS)
    dest_cab = FIXTURES_DIR / "sample.cab"
    if _write_cab(dest_cab):
        print(f"  {'sample.cab':30s}  {dest_cab.stat().st_size:>8,} B")
    else:
        print(f"  {'sample.cab':30s}  skipped (gcab not found)", file=sys.stderr)

    # .lha / .lzh — LHA (lha CLI; brew install lha on macOS, lhasa on Linux is extract-only)
    for filename in ("sample.lha", "sample.lzh"):
        dest_lha = FIXTURES_DIR / filename
        if _write_lha(dest_lha):
            print(f"  {filename:30s}  {dest_lha.stat().st_size:>8,} B")
        else:
            print(f"  {filename:30s}  skipped (lha not found)", file=sys.stderr)

    print(f"\nFixtures written to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
