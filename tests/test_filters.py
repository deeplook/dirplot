"""Tests for path-pattern filtering and size-range parsing utilities."""

from __future__ import annotations

import pytest

from dirplot.filters import matches_exclude, parse_size, parse_size_range


def test_empty_patterns_returns_false() -> None:
    assert matches_exclude("src/foo.py", frozenset()) is False


def test_plain_name_matches_any_component() -> None:
    assert matches_exclude(".git", frozenset({".git"})) is True
    assert matches_exclude("src/.git", frozenset({".git"})) is True
    assert matches_exclude("a/b/c/.git/d", frozenset({".git"})) is True


def test_plain_name_no_false_positive() -> None:
    assert matches_exclude("src/keep.py", frozenset({".git"})) is False


def test_glob_wildcard_plain_name() -> None:
    assert matches_exclude("mypackage.egg-info", frozenset({"*.egg-info"})) is True
    assert matches_exclude("src/mypackage.egg-info", frozenset({"*.egg-info"})) is True
    assert matches_exclude("src/mypackage.egg-info/PKG-INFO", frozenset({"*.egg-info"})) is True


def test_relative_path_with_slash() -> None:
    assert matches_exclude("src/vendor", frozenset({"src/vendor"})) is True
    assert matches_exclude("src/vendor/lib.py", frozenset({"src/vendor"})) is False


def test_relative_path_fnmatch() -> None:
    assert matches_exclude("src/foo.py", frozenset({"src/*.py"})) is True
    assert matches_exclude("src/bar.txt", frozenset({"src/*.py"})) is False


def test_double_star_any_depth() -> None:
    assert matches_exclude("__pycache__", frozenset({"**/__pycache__"})) is True
    assert matches_exclude("src/__pycache__", frozenset({"**/__pycache__"})) is True
    assert matches_exclude("a/b/c/__pycache__", frozenset({"**/__pycache__"})) is True


def test_double_star_no_false_positive() -> None:
    assert matches_exclude("src/other", frozenset({"**/__pycache__"})) is False


def test_multiple_patterns_any_match() -> None:
    patterns = frozenset({".git", "*.egg-info"})
    assert matches_exclude(".git", patterns) is True
    assert matches_exclude("mypackage.egg-info", patterns) is True
    assert matches_exclude("src/foo.py", patterns) is False


# ── parse_size ───────────────────────────────────────────────────────────────


def test_parse_size_bytes() -> None:
    assert parse_size("100") == 100
    assert parse_size("100B") == 100
    assert parse_size("100b") == 100


def test_parse_size_kilobytes() -> None:
    assert parse_size("1K") == 1024
    assert parse_size("1k") == 1024
    assert parse_size("2KB") == 2 * 1024


def test_parse_size_megabytes() -> None:
    assert parse_size("10M") == 10 * 1024**2
    assert parse_size("10MB") == 10 * 1024**2
    assert parse_size("10m") == 10 * 1024**2


def test_parse_size_gigabytes() -> None:
    assert parse_size("1G") == 1024**3
    assert parse_size("1GB") == 1024**3


def test_parse_size_terabytes() -> None:
    assert parse_size("1T") == 1024**4
    assert parse_size("1TB") == 1024**4


def test_parse_size_float() -> None:
    assert parse_size("1.5M") == int(1.5 * 1024**2)


def test_parse_size_invalid_unit() -> None:
    with pytest.raises(ValueError, match="Unknown size unit"):
        parse_size("10X")


def test_parse_size_invalid_format() -> None:
    with pytest.raises(ValueError, match="Invalid size value"):
        parse_size("notasize")


# ── parse_size_range ─────────────────────────────────────────────────────────


def test_parse_size_range_bounded() -> None:
    r = parse_size_range("10M..500M")
    assert r.min_bytes == 10 * 1024**2
    assert r.max_bytes == 500 * 1024**2


def test_parse_size_range_lower_only() -> None:
    r = parse_size_range("100M..")
    assert r.min_bytes == 100 * 1024**2
    assert r.max_bytes is None


def test_parse_size_range_upper_only() -> None:
    r = parse_size_range("..50K")
    assert r.min_bytes is None
    assert r.max_bytes == 50 * 1024


def test_parse_size_range_exact() -> None:
    r = parse_size_range("1G")
    assert r.min_bytes == 1024**3
    assert r.max_bytes == 1024**3


def test_parse_size_range_inverted_raises() -> None:
    with pytest.raises(ValueError, match="lower bound"):
        parse_size_range("500M..10M")


def test_parse_size_range_whitespace_tolerated() -> None:
    r = parse_size_range("  10M .. 500M  ")
    assert r.min_bytes == 10 * 1024**2
    assert r.max_bytes == 500 * 1024**2
