"""Tests for filter_by_size tree-pruning function."""

from __future__ import annotations

from pathlib import Path

from dirplot.filters import SizeRange
from dirplot.scanner import Node, filter_by_size, matches_any_range


def _leaf(name: str, size: int) -> Node:
    return Node(name=name, path=Path(name), size=size, is_dir=False, extension=".txt")


def _dir(name: str, children: list[Node]) -> Node:
    return Node(
        name=name,
        path=Path(name),
        size=sum(c.size for c in children),
        is_dir=True,
        extension="",
        children=children,
    )


# ── matches_any_range ─────────────────────────────────────────────────────────


def test_matches_within_range() -> None:
    r = SizeRange(min_bytes=100, max_bytes=500)
    assert matches_any_range(200, [r]) is True


def test_matches_at_lower_bound() -> None:
    r = SizeRange(min_bytes=100, max_bytes=500)
    assert matches_any_range(100, [r]) is True


def test_matches_at_upper_bound() -> None:
    r = SizeRange(min_bytes=100, max_bytes=500)
    assert matches_any_range(500, [r]) is True


def test_does_not_match_below_range() -> None:
    r = SizeRange(min_bytes=100, max_bytes=500)
    assert matches_any_range(50, [r]) is False


def test_does_not_match_above_range() -> None:
    r = SizeRange(min_bytes=100, max_bytes=500)
    assert matches_any_range(600, [r]) is False


def test_matches_open_lower() -> None:
    r = SizeRange(min_bytes=None, max_bytes=500)
    assert matches_any_range(1, [r]) is True
    assert matches_any_range(501, [r]) is False


def test_matches_open_upper() -> None:
    r = SizeRange(min_bytes=100, max_bytes=None)
    assert matches_any_range(999999, [r]) is True
    assert matches_any_range(99, [r]) is False


def test_matches_or_logic() -> None:
    r1 = SizeRange(min_bytes=None, max_bytes=100)
    r2 = SizeRange(min_bytes=1000, max_bytes=None)
    assert matches_any_range(50, [r1, r2]) is True
    assert matches_any_range(2000, [r1, r2]) is True
    assert matches_any_range(500, [r1, r2]) is False


# ── filter_by_size ────────────────────────────────────────────────────────────


def test_leaf_kept_when_in_range() -> None:
    leaf = _leaf("a.txt", 200)
    result = filter_by_size(leaf, [SizeRange(None, None)])
    assert result is not None
    assert result.name == "a.txt"


def test_leaf_pruned_when_out_of_range() -> None:
    leaf = _leaf("a.txt", 200)
    result = filter_by_size(leaf, [SizeRange(min_bytes=500, max_bytes=None)])
    assert result is None


def test_dir_pruned_when_all_children_removed() -> None:
    tree = _dir("root", [_leaf("a.txt", 50), _leaf("b.txt", 60)])
    result = filter_by_size(tree, [SizeRange(min_bytes=1000, max_bytes=None)])
    assert result is None


def test_dir_kept_when_some_children_match() -> None:
    tree = _dir("root", [_leaf("small.txt", 50), _leaf("big.txt", 5000)])
    result = filter_by_size(tree, [SizeRange(min_bytes=1000, max_bytes=None)])
    assert result is not None
    assert len(result.children) == 1
    assert result.children[0].name == "big.txt"


def test_parent_size_recalculated() -> None:
    tree = _dir("root", [_leaf("small.txt", 50), _leaf("big.txt", 5000)])
    result = filter_by_size(tree, [SizeRange(min_bytes=1000, max_bytes=None)])
    assert result is not None
    assert result.size == 5000


def test_keep_empty_dirs_option() -> None:
    tree = _dir("root", [_leaf("a.txt", 50)])
    result = filter_by_size(tree, [SizeRange(min_bytes=1000, max_bytes=None)], keep_empty_dirs=True)
    assert result is not None
    assert result.children == []
    assert result.size == 0


def test_nested_tree_filtering() -> None:
    inner = _dir("inner", [_leaf("small.txt", 10), _leaf("large.txt", 2000)])
    outer = _dir("outer", [inner, _leaf("medium.txt", 500)])
    result = filter_by_size(outer, [SizeRange(min_bytes=1000, max_bytes=None)])
    assert result is not None
    assert len(result.children) == 1
    assert result.children[0].name == "inner"
    assert result.children[0].children[0].name == "large.txt"


def test_or_logic_multiple_ranges() -> None:
    tree = _dir("root", [_leaf("tiny.txt", 5), _leaf("large.txt", 5000)])
    r1 = SizeRange(min_bytes=None, max_bytes=10)
    r2 = SizeRange(min_bytes=4000, max_bytes=None)
    result = filter_by_size(tree, [r1, r2])
    assert result is not None
    assert len(result.children) == 2


def test_uses_original_size_when_set() -> None:
    leaf = _leaf("a.txt", 1)  # log-scaled size
    leaf = Node(**{**vars(leaf), "original_size": 5000})  # type: ignore[arg-type]
    result = filter_by_size(leaf, [SizeRange(min_bytes=4000, max_bytes=None)])
    assert result is not None
