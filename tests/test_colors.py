"""Tests for colour assignment stability."""

import pytest

from dirplot.colors import _hex_to_rgba, assign_colors


def test_color_stability() -> None:
    """Same extension always maps to the same colour."""
    exts = [".py", ".md", ".txt"]
    colors_a = assign_colors(exts)
    colors_b = assign_colors(exts)
    assert colors_a == colors_b


def test_color_stability_across_sets() -> None:
    """Extension colour is independent of which other extensions are present."""
    color_in_small = assign_colors([".py", ".md"])[".py"]
    color_in_large = assign_colors([".py", ".md", ".txt", ".json", ".yaml"])[".py"]
    assert color_in_small == color_in_large


def test_color_is_rgba() -> None:
    colors = assign_colors([".py"])
    rgba = colors[".py"]
    assert len(rgba) == 4
    assert all(0.0 <= v <= 1.0 for v in rgba)


def test_linguist_color_used_for_known_ext() -> None:
    """Known extensions get their Linguist color, not a colormap color."""
    colors = assign_colors([".py"])
    # Python Linguist color is #3572A5
    assert colors[".py"] == pytest.approx(_hex_to_rgba("#3572A5"), abs=1e-3)


def test_linguist_color_case_insensitive() -> None:
    """.PY and .py resolve to the same Linguist color."""
    assert assign_colors([".PY"])[".PY"] == assign_colors([".py"])[".py"]


def test_unknown_ext_uses_colormap() -> None:
    """Unknown extensions still get a colormap color (stable, RGBA)."""
    colors = assign_colors([".xyzzy123"])
    rgba = colors[".xyzzy123"]
    assert len(rgba) == 4
    assert all(0.0 <= v <= 1.0 for v in rgba)


def test_unknown_colormap_raises() -> None:
    with pytest.raises(Exception):  # noqa: B017
        assign_colors([".py"], colormap="not_a_real_colormap")
