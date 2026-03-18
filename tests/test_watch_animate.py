"""Integration test: watch + animate mode produces a valid multi-frame APNG.

The output is written to tests/animation/watch_demo.png and kept after the
test so it can be inspected visually in Safari, Firefox, or Preview.
"""

import time
from pathlib import Path

from PIL import Image, ImageSequence

from dirplot.watch import TreemapEventHandler

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
