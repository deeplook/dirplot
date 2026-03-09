"""AWS S3 directory tree scanning via boto3 (optional dependency)."""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath
from typing import Any

from dirplot.scanner import Node


def _require_boto3() -> Any:
    try:
        import boto3

        return boto3
    except ImportError:
        raise ImportError(
            "S3 support requires boto3. Install it with:\n  pip install dirplot[s3]"
        ) from None


def is_s3_path(path_str: str) -> bool:
    """Return True if *path_str* is an S3 URI."""
    return path_str.startswith("s3://")


def parse_s3_path(path_str: str) -> tuple[str, str]:
    """Parse an S3 URI into *(bucket, prefix)*.

    The prefix always ends with ``/`` when non-empty so that
    ``list_objects_v2`` treats it as a directory boundary.

    Examples::

        "s3://my-bucket"          → ("my-bucket", "")
        "s3://my-bucket/"         → ("my-bucket", "")
        "s3://my-bucket/path"     → ("my-bucket", "path/")
        "s3://my-bucket/path/"    → ("my-bucket", "path/")
    """
    without_scheme = path_str[len("s3://") :]
    bucket, _, prefix = without_scheme.partition("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


def make_s3_client(profile: str | None = None, no_sign: bool = False) -> Any:
    """Return a boto3 S3 client, optionally using a named AWS profile.

    Pass *no_sign=True* for anonymous access to public buckets
    (equivalent to ``aws s3 --no-sign-request``).
    """
    boto3 = _require_boto3()
    from botocore import UNSIGNED
    from botocore.config import Config

    session = boto3.Session(profile_name=profile)
    config = Config(signature_version=UNSIGNED) if no_sign else None
    return session.client("s3", config=config)


def build_tree_s3(
    s3: Any,
    bucket: str,
    prefix: str = "",
    exclude: frozenset[str] = frozenset(),
    *,
    depth: int | None = None,
    _progress: list[int] | None = None,
) -> Node:
    """Recursively build a :class:`~dirplot.scanner.Node` tree from an S3 prefix.

    Uses ``list_objects_v2`` with ``Delimiter='/'`` so that each call
    returns one "directory level" — files in ``Contents`` and
    subdirectories in ``CommonPrefixes`` — mirroring how
    :func:`~dirplot.scanner.build_tree` works locally.

    Args:
        s3: A boto3 S3 client.
        bucket: S3 bucket name.
        prefix: Key prefix to scan (must end with ``/`` or be empty).
        exclude: Set of full ``s3://bucket/key`` URIs to skip.
        depth: Maximum recursion depth. ``None`` means unlimited.
            ``depth=1`` lists direct children without recursing into subdirs.
        _progress: Internal one-element counter for progress reporting.
    """
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/")

    raw_files: list[dict[str, Any]] = []
    raw_dirs: list[dict[str, Any]] = []
    for page in pages:
        for obj in page.get("Contents", []):
            if obj["Key"] != prefix:  # skip the directory marker itself
                raw_files.append(obj)
        raw_dirs.extend(page.get("CommonPrefixes", []))

    children: list[Node] = []

    for obj in sorted(raw_files, key=lambda o: o["Key"]):
        name = PurePosixPath(obj["Key"]).name
        if not name or name.startswith("."):
            continue
        full = f"s3://{bucket}/{obj['Key']}"
        if full in exclude:
            continue

        if _progress is not None:
            _progress[0] += 1
            if _progress[0] % 100 == 0:
                print(
                    f"\r  scanned {_progress[0]} entries…",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

        ext = PurePosixPath(name).suffix.lower() or "(no ext)"
        children.append(
            Node(
                name=name,
                path=Path(obj["Key"]),
                size=max(1, obj.get("Size", 0)),
                is_dir=False,
                extension=ext,
            )
        )

    for cp in sorted(raw_dirs, key=lambda p: p["Prefix"]):
        subprefix = cp["Prefix"]
        name = PurePosixPath(subprefix.rstrip("/")).name
        if not name or name.startswith("."):
            continue
        full = f"s3://{bucket}/{subprefix}"
        if full in exclude:
            continue

        if depth is not None and depth <= 1:
            child: Node = Node(
                name=name,
                path=Path(subprefix),
                size=1,
                is_dir=True,
                extension="",
            )
        else:
            child = build_tree_s3(
                s3,
                bucket,
                subprefix,
                exclude,
                depth=None if depth is None else depth - 1,
                _progress=_progress,
            )
        children.append(child)

    total = sum(c.size for c in children) or 1
    node_name = PurePosixPath(prefix.rstrip("/")).name or bucket
    return Node(
        name=node_name,
        path=Path(prefix or bucket),
        size=total,
        is_dir=True,
        extension="",
        children=children,
    )
