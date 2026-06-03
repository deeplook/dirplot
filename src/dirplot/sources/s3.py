"""AWS S3 directory tree source implementation."""

from __future__ import annotations

from dirplot.s3 import build_tree_s3, is_s3_path, make_s3_client, parse_s3_path
from dirplot.scanner import Node
from dirplot.sources import register_source


class S3Source:
    """Tree source for AWS S3 buckets via boto3."""

    @property
    def name(self) -> str:
        return "s3"

    def can_handle(self, path: str) -> bool:
        return is_s3_path(path)

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        bucket, prefix = parse_s3_path(path)
        s3 = make_s3_client()
        return build_tree_s3(s3, bucket, prefix, exclude, depth=depth)

    def get_display_name(self, path: str) -> str:
        bucket, prefix = parse_s3_path(path)
        return f"s3://{bucket}/{prefix}".rstrip("/")


s3_source = S3Source()
register_source(s3_source)
