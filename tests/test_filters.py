"""Tests for the matches_exclude path-pattern filtering utility."""

from __future__ import annotations

from dirplot.filters import matches_exclude


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
