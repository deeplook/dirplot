"""Docker container directory tree source implementation."""

from __future__ import annotations

from dirplot.docker import build_tree_docker, is_docker_path, parse_docker_path
from dirplot.scanner import Node
from dirplot.sources import register_source


class DockerSource:
    """Tree source for Docker container filesystems via docker exec."""

    @property
    def name(self) -> str:
        return "docker"

    def can_handle(self, path: str) -> bool:
        return is_docker_path(path)

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        container, remote_path = parse_docker_path(path)
        return build_tree_docker(container, remote_path, exclude, depth=depth)

    def get_display_name(self, path: str) -> str:
        container, remote_path = parse_docker_path(path)
        return f"docker://{container}{remote_path}"


docker_source = DockerSource()
register_source(docker_source)
