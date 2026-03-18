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

    # ── build initial tree ────────────────────────────────────────────────
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_bytes(b"x" * 5_000)
    (src / "utils.py").write_bytes(b"x" * 3_000)

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_bytes(b"x" * 2_000)
    (docs / "api.md").write_bytes(b"x" * 1_500)

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

    # ── frame 1: initial state ────────────────────────────────────────────
    handler._regenerate()
    time.sleep(0.3)

    # ── frame 2: add tests/ ───────────────────────────────────────────────
    tests = tmp_path / "tests"
    tests.mkdir()
    for i in range(4):
        (tests / f"test_{i}.py").write_bytes(b"x" * (1_000 + i * 500))
    handler._regenerate()
    time.sleep(0.3)

    # ── frame 3: grow src/ ────────────────────────────────────────────────
    (src / "models.py").write_bytes(b"x" * 10_000)
    (src / "api.py").write_bytes(b"x" * 7_000)
    (src / "database.py").write_bytes(b"x" * 15_000)
    handler._regenerate()
    time.sleep(0.3)

    # ── frame 4: add data/ with large files ──────────────────────────────
    data = tmp_path / "data"
    data.mkdir()
    (data / "dataset.csv").write_bytes(b"x" * 60_000)
    (data / "model.pkl").write_bytes(b"x" * 40_000)
    (data / "config.json").write_bytes(b"x" * 5_000)
    handler._regenerate()
    time.sleep(0.3)

    # ── frame 5: delete some files, add a vendor/ ────────────────────────
    (docs / "README.md").unlink()
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    for name in ["requests", "flask", "sqlalchemy"]:
        lib = vendor / name
        lib.mkdir()
        (lib / "__init__.py").write_bytes(b"x" * (8_000 + len(name) * 1_000))
    handler._regenerate()

    # ── write APNG ────────────────────────────────────────────────────────
    handler.flush()

    # ── verify ────────────────────────────────────────────────────────────
    img = Image.open(_DEMO_OUTPUT)
    n_frames = getattr(img, "n_frames", 1)
    assert getattr(img, "is_animated", False), "output is not an animated PNG"
    assert n_frames == 5, f"expected 5 frames, got {n_frames}"

    for i, frame in enumerate(list(ImageSequence.Iterator(img))[:-1]):
        d = frame.info.get("duration", 0)
        assert d >= 100, f"frame {i} has suspicious duration {d} ms"

    print(f"\n  APNG: {_DEMO_OUTPUT} ({n_frames} frames)")
    print("  Open in Safari, Firefox, or Preview to view the animation.")
