"""Docker container directory scanning via the docker CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

from dirplot.scanner import Node


def _docker_cmd() -> str:
    """Return the docker executable name, raising if not found."""
    import shutil

    if shutil.which("docker") is None:
        raise FileNotFoundError(
            "docker CLI not found in PATH. Install Docker from https://docs.docker.com/get-docker/"
        )
    return "docker"


def is_docker_path(s: str) -> bool:
    """Return True if *s* looks like a Docker container path."""
    return s.startswith("docker://")


def parse_docker_path(s: str) -> tuple[str, str]:
    """Parse a Docker path string into *(container, remote_path)*.

    Accepted formats::

        docker://container/path
        docker://container:/path
    """
    rest = s[len("docker://") :]

    # Support both docker://container:/path and docker://container/path
    if ":" in rest:
        container, remote_path = rest.split(":", 1)
    else:
        parts = rest.split("/", 1)
        container = parts[0]
        remote_path = "/" + parts[1] if len(parts) > 1 else "/"

    if not remote_path.startswith("/"):
        remote_path = "/" + remote_path

    return container, remote_path


def _check_container(docker: str, container_name: str) -> None:
    """Raise FileNotFoundError if the container does not exist or is not running."""
    result = subprocess.run(
        [docker, "inspect", "--type", "container", container_name],
        capture_output=True,
    )
    if result.returncode != 0:
        raise FileNotFoundError(f"Docker container not found or not running: {container_name!r}")


def _run_find(
    docker: str, container_name: str, remote_path: str, depth: int | None
) -> subprocess.CompletedProcess[str]:
    """Run find inside the container, trying GNU find then BusyBox fallback.

    GNU find (Debian/Ubuntu/RHEL images) supports ``-printf`` for efficient
    single-pass output. BusyBox find (Alpine images) does not; we fall back to
    a POSIX sh + stat loop that works on any image with a shell.
    """
    max_depth_args = ["-maxdepth", str(depth)] if depth is not None else []

    # GNU find: single pass, output is "rel_path\tsize\ttype"
    result = subprocess.run(
        [
            docker,
            "exec",
            container_name,
            "find",
            remote_path,
            "-xdev",
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

    # BusyBox fallback: sh + stat loop. remote_path is passed as $1 to avoid
    # quoting issues inside the script string.
    # Use ${p%/}/ so that p="/" → prefix="/", p="/app" → prefix="/app/",
    # avoiding the double-slash bug when stripping the root path.
    max_depth_sh = f"-maxdepth {depth}" if depth is not None else ""
    script = (
        'p="$1"; pfx="${p%/}/"\n'
        f'find "$p" -xdev {max_depth_sh} -not -type l | while IFS= read -r f; do\n'
        '  r="${f#${pfx}}"\n'
        '  case "$r" in "") continue;; "$f") continue;; /*) continue;; esac\n'
        '  s=$(stat -c%s "$f" 2>/dev/null) || s=1\n'
        '  [ -d "$f" ] && t=d || t=f\n'
        '  printf "%s\\t%s\\t%s\\n" "$r" "$s" "$t"\n'
        "done"
    )
    return subprocess.run(
        [docker, "exec", container_name, "sh", "-c", script, "_", remote_path],
        capture_output=True,
        text=True,
    )


def build_tree_docker(
    container_name: str,
    remote_path: str,
    exclude: frozenset[str] = frozenset(),
    *,
    depth: int | None = None,
    _progress: list[int] | None = None,
) -> Node:
    """Build a :class:`~dirplot.scanner.Node` tree from a Docker container path.

    Uses ``docker exec`` to run ``find`` inside the container, so the container
    must be running and have a POSIX ``find`` binary available (standard on all
    common Linux base images).

    Args:
        container_name: Container name or ID.
        remote_path: Absolute path inside the container.
        exclude: Set of absolute paths inside the container to skip.
        depth: Maximum recursion depth. ``None`` means unlimited.
        _progress: Internal one-element counter for progress reporting.
    """
    docker = _docker_cmd()
    _check_container(docker, container_name)

    result = _run_find(docker, container_name, remote_path, depth)
    if result.returncode != 0:
        err = result.stderr.strip()
        raise OSError(f"find failed in container {container_name!r} at {remote_path!r}: {err}")

    # Parse find output into (rel_path, size, is_dir) entries
    entries: list[tuple[str, int, bool]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        rel_path, size_str, ftype = parts
        if not rel_path:
            continue  # the root entry itself (empty relative path)
        name = PurePosixPath(rel_path).name
        if name.startswith("."):
            continue  # skip hidden files
        abs_path = remote_path.rstrip("/") + "/" + rel_path
        if abs_path in exclude or any(abs_path.startswith(ex.rstrip("/") + "/") for ex in exclude):
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
    dir_nodes[""] = root_node  # empty string = root

    # Sort so parent dirs appear before their children
    entries_sorted = sorted(entries, key=lambda e: e[0])

    for rel_path, size, is_dir in entries_sorted:
        pure = PurePosixPath(rel_path)
        name = pure.name
        parent_rel = str(pure.parent) if str(pure.parent) != "." else ""
        abs_path = root_path.rstrip("/") + "/" + rel_path

        # Ensure intermediate directories exist in the tree
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
