"""Kubernetes pod directory tree source implementation."""

from __future__ import annotations

from dirplot.k8s import build_tree_pod, is_pod_path, parse_pod_path
from dirplot.scanner import Node
from dirplot.sources import register_source


class K8sSource:
    """Tree source for Kubernetes pod filesystems via kubectl exec."""

    @property
    def name(self) -> str:
        return "k8s"

    def can_handle(self, path: str) -> bool:
        return is_pod_path(path)

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        pod_name, namespace, remote_path = parse_pod_path(path)
        return build_tree_pod(
            pod_name, remote_path, namespace=namespace, exclude=exclude, depth=depth
        )

    def get_display_name(self, path: str) -> str:
        pod_name, namespace, remote_path = parse_pod_path(path)
        ns = f"@{namespace}" if namespace else ""
        return f"pod://{pod_name}{ns}{remote_path}"


k8s_source = K8sSource()
register_source(k8s_source)
