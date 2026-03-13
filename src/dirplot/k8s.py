"""Kubernetes pod directory scanning via kubectl."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

from dirplot.scanner import Node


def _kubectl_cmd() -> str:
    """Return the kubectl executable name, raising if not found."""
    import shutil

    if shutil.which("kubectl") is None:
        raise FileNotFoundError(
            "kubectl not found in PATH. Install kubectl from https://kubernetes.io/docs/tasks/tools/"
        )
    return "kubectl"


def is_pod_path(s: str) -> bool:
    """Return True if *s* looks like a Kubernetes pod path."""
    return s.startswith("pod://")


def parse_pod_path(s: str) -> tuple[str, str | None, str]:
    """Parse a pod path string into *(pod_name, namespace, remote_path)*.

    Accepted formats::

        pod://pod-name/path               # default namespace
        pod://pod-name:/path              # default namespace, colon separator
        pod://pod-name@namespace/path     # explicit namespace
        pod://pod-name@namespace:/path    # explicit namespace, colon separator
    """
    rest = s[len("pod://") :]

    # Split off namespace: "pod@namespace..." → pod_name, "namespace..."
    namespace: str | None = None
    if "@" in rest:
        pod_name, rest = rest.split("@", 1)
        # rest is now "namespace/path" or "namespace:/path"
        if ":" in rest.split("/")[0]:
            namespace, remote_path = rest.split(":", 1)
        else:
            parts = rest.split("/", 1)
            namespace = parts[0]
            remote_path = "/" + parts[1] if len(parts) > 1 else "/"
    else:
        # rest is "pod-name/path" or "pod-name:/path"
        if ":" in rest.split("/")[0]:
            pod_name, remote_path = rest.split(":", 1)
        else:
            parts = rest.split("/", 1)
            pod_name = parts[0]
            remote_path = "/" + parts[1] if len(parts) > 1 else "/"

    if not remote_path.startswith("/"):
        remote_path = "/" + remote_path

    return pod_name, namespace, remote_path


def _check_pod(kubectl: str, pod_name: str, namespace: str | None) -> None:
    """Raise FileNotFoundError if the pod does not exist or is not running."""
    cmd = [kubectl, "get", "pod", pod_name]
    if namespace:
        cmd += ["-n", namespace]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        ns_hint = f" in namespace {namespace!r}" if namespace else ""
        raise FileNotFoundError(f"Kubernetes pod not found or not running: {pod_name!r}{ns_hint}")


def _run_find(
    kubectl: str,
    pod_name: str,
    namespace: str | None,
    container: str | None,
    remote_path: str,
    depth: int | None,
) -> subprocess.CompletedProcess[str]:
    """Run find inside the pod, trying GNU find then BusyBox fallback.

    GNU find (Debian/Ubuntu/RHEL images) supports ``-printf`` for efficient
    single-pass output. BusyBox find (Alpine images) does not; we fall back to
    a POSIX sh + stat loop that works on any image with a shell.
    """
    max_depth_args = ["-maxdepth", str(depth)] if depth is not None else []

    base_cmd = [kubectl, "exec", pod_name]
    if namespace:
        base_cmd += ["-n", namespace]
    if container:
        base_cmd += ["-c", container]
    base_cmd += ["--"]

    # GNU find: single pass, output is "rel_path\tsize\ttype"
    result = subprocess.run(
        base_cmd
        + [
            "find",
            remote_path,
            *max_depth_args,
            "-not",
            "-type",
            "l",
            "-printf",
            r"%P\t%s\t%y\n",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 or "unrecognized" not in result.stderr:
        return result

    # BusyBox fallback: sh + stat loop
    max_depth_sh = f"-maxdepth {depth}" if depth is not None else ""
    script = (
        'p="$1"; pfx="${p%/}/"\n'
        f'find "$p" {max_depth_sh} -not -type l | while IFS= read -r f; do\n'
        '  r="${f#${pfx}}"\n'
        '  case "$r" in "") continue;; "$f") continue;; /*) continue;; esac\n'
        '  s=$(stat -c%s "$f" 2>/dev/null) || s=1\n'
        '  [ -d "$f" ] && t=d || t=f\n'
        '  printf "%s\\t%s\\t%s\\n" "$r" "$s" "$t"\n'
        "done"
    )
    return subprocess.run(
        base_cmd + ["sh", "-c", script, "_", remote_path],
        capture_output=True,
        text=True,
    )


def build_tree_pod(
    pod_name: str,
    remote_path: str,
    namespace: str | None = None,
    container: str | None = None,
    exclude: frozenset[str] = frozenset(),
    *,
    depth: int | None = None,
    _progress: list[int] | None = None,
) -> Node:
    """Build a :class:`~dirplot.scanner.Node` tree from a Kubernetes pod path.

    Uses ``kubectl exec`` to run ``find`` inside the pod, so the pod must be
    running and have a POSIX ``find`` binary available.

    Args:
        pod_name: Pod name.
        remote_path: Absolute path inside the pod.
        namespace: Kubernetes namespace. ``None`` uses the current context default.
        container: Container name for multi-container pods. ``None`` uses the default.
        exclude: Set of absolute paths inside the pod to skip.
        depth: Maximum recursion depth. ``None`` means unlimited.
        _progress: Internal one-element counter for progress reporting.
    """
    kubectl = _kubectl_cmd()
    _check_pod(kubectl, pod_name, namespace)

    result = _run_find(kubectl, pod_name, namespace, container, remote_path, depth)
    if result.returncode != 0:
        err = result.stderr.strip()
        if (
            result.returncode == 126
            or "executable file not found" in err
            or "not found in $PATH" in err
        ):
            raise OSError(
                f"No shell or 'find' utility in pod {pod_name!r} — the container is likely "
                "distroless (scratch/distroless image with no OS tools). "
                "dirplot requires a POSIX 'find' binary inside the container."
            )
        raise OSError(f"find failed in pod {pod_name!r} at {remote_path!r}: {err}")

    entries: list[tuple[str, int, bool]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        rel_path, size_str, ftype = parts
        if not rel_path:
            continue
        name = PurePosixPath(rel_path).name
        if name.startswith("."):
            continue
        abs_path = remote_path.rstrip("/") + "/" + rel_path
        if abs_path in exclude:
            continue
        try:
            size = int(size_str)
        except ValueError:
            size = 1
        entries.append((rel_path, max(size, 1), ftype == "d"))

        if _progress is not None:
            _progress[0] += 1
            if _progress[0] % 100 == 0:
                print(
                    f"\r  scanned {_progress[0]} entries…",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

    return _entries_to_tree(remote_path, entries)


def _entries_to_tree(root_path: str, entries: list[tuple[str, int, bool]]) -> Node:
    """Convert a flat list of *(rel_path, size, is_dir)* entries into a Node tree."""
    dir_nodes: dict[str, Node] = {}
    root_name = PurePosixPath(root_path).name or root_path
    root_node = Node(name=root_name, path=Path(root_path), size=0, is_dir=True, children=[])
    dir_nodes[""] = root_node

    entries_sorted = sorted(entries, key=lambda e: e[0])

    for rel_path, size, is_dir in entries_sorted:
        pure = PurePosixPath(rel_path)
        name = pure.name
        parent_rel = str(pure.parent) if str(pure.parent) != "." else ""
        abs_path = root_path.rstrip("/") + "/" + rel_path

        _ensure_dir(dir_nodes, root_path, parent_rel)
        parent_node = dir_nodes.get(parent_rel, root_node)

        if is_dir:
            node = Node(
                name=name,
                path=Path(abs_path),
                size=0,
                is_dir=True,
                children=[],
            )
            dir_nodes[rel_path] = node
        else:
            ext = pure.suffix.lower() or "(no ext)"
            node = Node(
                name=name,
                path=Path(abs_path),
                size=size,
                is_dir=False,
                extension=ext,
            )

        parent_node.children.append(node)

    _compute_sizes(root_node)
    return root_node


def _ensure_dir(dir_nodes: dict[str, Node], root_path: str, rel_path: str) -> None:
    """Create missing intermediate directory nodes."""
    if rel_path in dir_nodes or rel_path == "":
        return
    pure = PurePosixPath(rel_path)
    parent_rel = str(pure.parent) if str(pure.parent) != "." else ""
    _ensure_dir(dir_nodes, root_path, parent_rel)

    abs_path = root_path.rstrip("/") + "/" + rel_path
    node = Node(
        name=pure.name,
        path=Path(abs_path),
        size=0,
        is_dir=True,
        children=[],
    )
    dir_nodes[rel_path] = node
    dir_nodes[parent_rel].children.append(node)


def _compute_sizes(node: Node) -> int:
    """Recursively set directory sizes to the sum of their children's sizes."""
    if not node.is_dir:
        return node.size
    total = sum(_compute_sizes(c) for c in node.children)
    node.size = max(total, 1)
    return node.size
