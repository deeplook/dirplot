"""Tests for AWS S3 directory tree scanning."""

from unittest.mock import MagicMock

import pytest

from dirplot.s3 import build_tree_s3, is_s3_path, parse_s3_path


def make_s3(pages: list[dict]) -> MagicMock:
    """Return a mock boto3 S3 client whose paginator yields *pages*."""
    s3 = MagicMock()
    paginator = MagicMock()
    s3.get_paginator.return_value = paginator
    paginator.paginate.return_value = pages
    return s3


def obj(key: str, size: int) -> dict:
    return {"Key": key, "Size": size}


def prefix(p: str) -> dict:
    return {"Prefix": p}


# ---------------------------------------------------------------------------
# URI helpers
# ---------------------------------------------------------------------------


def test_is_s3_path() -> None:
    assert is_s3_path("s3://my-bucket/path")
    assert is_s3_path("s3://my-bucket")


@pytest.mark.parametrize("path", ["/local", "ssh://user@host/path", "."])
def test_is_not_s3_path(path: str) -> None:
    assert not is_s3_path(path)


def test_parse_s3_path_with_prefix() -> None:
    assert parse_s3_path("s3://my-bucket/path/to/dir") == ("my-bucket", "path/to/dir/")


def test_parse_s3_path_trailing_slash() -> None:
    assert parse_s3_path("s3://my-bucket/path/") == ("my-bucket", "path/")


def test_parse_s3_path_bucket_only() -> None:
    assert parse_s3_path("s3://my-bucket") == ("my-bucket", "")


def test_parse_s3_path_bucket_with_slash() -> None:
    assert parse_s3_path("s3://my-bucket/") == ("my-bucket", "")


# ---------------------------------------------------------------------------
# build_tree_s3
# ---------------------------------------------------------------------------


def test_build_tree_s3_flat() -> None:
    s3 = make_s3([{"Contents": [obj("project/app.py", 100), obj("project/README.md", 50)]}])

    node = build_tree_s3(s3, "bucket", "project/")
    assert node.is_dir
    assert node.name == "project"
    assert node.size == 150
    assert {c.name for c in node.children} == {"app.py", "README.md"}


def test_build_tree_s3_extensions() -> None:
    s3 = make_s3([{"Contents": [obj("project/script.py", 100), obj("project/Makefile", 50)]}])

    node = build_tree_s3(s3, "bucket", "project/")
    py = next(c for c in node.children if c.name == "script.py")
    mk = next(c for c in node.children if c.name == "Makefile")
    assert py.extension == ".py"
    assert mk.extension == "(no ext)"


def test_build_tree_s3_skips_dir_marker() -> None:
    # S3 sometimes includes a zero-byte object with the same key as the prefix
    s3 = make_s3([{"Contents": [obj("project/", 0), obj("project/file.py", 100)]}])

    node = build_tree_s3(s3, "bucket", "project/")
    assert len(node.children) == 1
    assert node.children[0].name == "file.py"


def test_build_tree_s3_skips_dotfiles() -> None:
    s3 = make_s3([{"Contents": [obj("project/.hidden", 100), obj("project/visible.txt", 200)]}])

    node = build_tree_s3(s3, "bucket", "project/")
    names = {c.name for c in node.children}
    assert "visible.txt" in names
    assert ".hidden" not in names


def test_build_tree_s3_recurses_into_subdirs() -> None:
    def paginate(Bucket: str, Prefix: str, Delimiter: str) -> list[dict]:
        if Prefix == "project/":
            return [
                {
                    "Contents": [obj("project/top.txt", 100)],
                    "CommonPrefixes": [prefix("project/src/")],
                }
            ]
        if Prefix == "project/src/":
            return [{"Contents": [obj("project/src/app.py", 200)]}]
        return [{}]

    s3 = MagicMock()
    paginator = MagicMock()
    s3.get_paginator.return_value = paginator
    paginator.paginate.side_effect = lambda **kw: paginate(**kw)

    node = build_tree_s3(s3, "bucket", "project/")
    assert node.size == 300
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir
    assert src.size == 200


def test_build_tree_s3_exclude() -> None:
    s3 = make_s3([{"Contents": [obj("project/keep.py", 100), obj("project/skip.py", 200)]}])

    node = build_tree_s3(
        s3, "bucket", "project/", exclude=frozenset({"s3://bucket/project/skip.py"})
    )
    names = {c.name for c in node.children}
    assert "keep.py" in names
    assert "skip.py" not in names


def test_build_tree_s3_depth_limit() -> None:
    def paginate(Bucket: str, Prefix: str, Delimiter: str) -> list[dict]:
        if Prefix == "project/":
            return [
                {
                    "Contents": [obj("project/top.txt", 100)],
                    "CommonPrefixes": [prefix("project/src/")],
                }
            ]
        return [{}]

    s3 = MagicMock()
    paginator = MagicMock()
    s3.get_paginator.return_value = paginator
    paginator.paginate.side_effect = lambda **kw: paginate(**kw)

    node = build_tree_s3(s3, "bucket", "project/", depth=1)
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir
    assert src.children == []
    # paginate should only have been called for the root prefix
    paginator.paginate.assert_called_once_with(Bucket="bucket", Prefix="project/", Delimiter="/")


def test_build_tree_s3_zero_size_defaults_to_1() -> None:
    s3 = make_s3([{"Contents": [obj("project/empty.txt", 0)]}])

    node = build_tree_s3(s3, "bucket", "project/")
    assert node.children[0].size == 1


def test_build_tree_s3_empty_prefix_uses_bucket_name() -> None:
    s3 = make_s3([{"Contents": [obj("file.txt", 100)]}])

    node = build_tree_s3(s3, "my-bucket", "")
    assert node.name == "my-bucket"


def test_build_tree_s3_pagination() -> None:
    """Results spread across multiple pages are combined correctly."""
    s3 = make_s3(
        [
            {"Contents": [obj("project/a.py", 100)]},
            {"Contents": [obj("project/b.py", 200)]},
        ]
    )

    node = build_tree_s3(s3, "bucket", "project/")
    assert node.size == 300
    assert {c.name for c in node.children} == {"a.py", "b.py"}
