"""Google Drive scanning via the gog CLI (https://gogcli.sh/)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from dirplot.filters import matches_exclude
from dirplot.scanner import NO_EXT, Node

_GDRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"

# Google-native formats have no byte size (stored as 0). Show them as 1 byte
# so they remain visible in the treemap rather than disappearing.
_GDRIVE_NATIVE_MIME_PREFIX = "application/vnd.google-apps."


def _gog_cmd() -> str:
    """Return the gog executable path, raising FileNotFoundError if absent."""
    if shutil.which("gog") is None:
        raise FileNotFoundError(
            "gog CLI not found in PATH. "
            "Install from https://gogcli.sh/ and authenticate with `gog auth`."
        )
    return "gog"


def is_gdrive_path(s: str) -> bool:
    """Return True if *s* looks like a Google Drive path."""
    return s.startswith("gdrive://")


def parse_gdrive_path(s: str) -> str | None:
    """Parse a Google Drive URL into an optional folder ID.

    Returns the folder ID if one was specified, or ``None`` for the Drive root.

    Accepted formats::

        gdrive://                           → Drive root (My Drive + shared drives)
        gdrive://1BxiMVs0XRA5nFMdKvBdBZjg   → specific folder ID
    """
    rest = s[len("gdrive://") :].strip("/")
    return rest if rest else None


def build_tree_gdrive(
    folder_id: str | None = None,
    *,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
    _progress: list[int] | None = None,
) -> Node:
    """Build a :class:`~dirplot.scanner.Node` tree from Google Drive.

    Shells out to ``gog drive tree --json`` and parses the flat item list into
    a Node hierarchy.  Authentication is handled entirely by gog — run
    ``gog auth`` once before use.

    Args:
        folder_id: Drive folder ID to start from.  ``None`` scans from the
            Drive root (My Drive + all shared drives).
        exclude: Set of path patterns to skip.
        depth: Maximum recursion depth.  ``None`` means unlimited.
        _progress: Internal one-element counter for progress reporting.
    """
    gog = _gog_cmd()

    cmd = [gog, "drive", "tree", "--json"]
    if folder_id:
        cmd += ["--parent", folder_id]
    # gog uses --depth 0 for unlimited; dirplot uses None
    cmd += ["--depth", str(depth) if depth is not None else "0"]
    cmd += ["--max", "0"]  # unlimited items

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise OSError(f"gog drive tree failed: {err}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OSError(f"gog drive tree returned invalid JSON: {exc}") from exc

    items: list[dict[str, object]] = data.get("items", [])
    if data.get("truncated"):
        print(
            "  Warning: Google Drive results truncated. "
            "Use --depth to limit recursion or --max in gog directly.",
            file=sys.stderr,
        )

    entries: list[tuple[str, int, bool]] = []
    for item in items:
        path_str = str(item.get("path") or "")
        if not path_str:
            continue
        name = PurePosixPath(path_str).name
        if name.startswith("."):
            continue
        if matches_exclude(path_str, exclude):
            continue

        mime = str(item.get("mimeType") or "")
        is_dir = mime == _GDRIVE_FOLDER_MIME

        raw_size = item.get("size")
        try:
            size = int(raw_size) if isinstance(raw_size, int | float | str) else 0
        except ValueError:
            size = 0
        if not is_dir and size == 0:
            # Google-native formats (Docs, Sheets, Slides, …) report no byte
            # size.  Use 1 so they remain visible in the treemap.
            size = 1

        entries.append((path_str, size, is_dir))

        if _progress is not None:
            _progress[0] += 1
            if _progress[0] % 100 == 0:
                print(
                    f"\r  scanned {_progress[0]} entries…",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

    root_label = folder_id or "My Drive"
    return _entries_to_tree(root_label, entries)


def _entries_to_tree(root_name: str, entries: list[tuple[str, int, bool]]) -> Node:
    """Convert a flat list of *(rel_path, size, is_dir)* entries into a Node tree."""
    dir_nodes: dict[str, Node] = {}
    root_node = Node(name=root_name, path=Path(root_name), size=0, is_dir=True, children=[])
    dir_nodes[""] = root_node

    for rel_path, size, is_dir in sorted(entries, key=lambda e: e[0]):
        pure = PurePosixPath(rel_path)
        name = pure.name
        parent_rel = str(pure.parent) if str(pure.parent) != "." else ""

        _ensure_dir(dir_nodes, parent_rel)
        parent_node = dir_nodes.get(parent_rel, root_node)

        if is_dir:
            node = Node(name=name, path=Path(rel_path), size=0, is_dir=True, children=[])
            dir_nodes[rel_path] = node
        else:
            node = Node(
                name=name,
                path=Path(rel_path),
                size=size,
                is_dir=False,
                extension=pure.suffix.lower() or NO_EXT,
            )

        parent_node.children.append(node)

    _compute_sizes(root_node)
    return root_node


def _ensure_dir(dir_nodes: dict[str, Node], rel_path: str) -> None:
    """Create missing intermediate directory nodes."""
    if rel_path in dir_nodes or rel_path == "":
        return
    pure = PurePosixPath(rel_path)
    parent_rel = str(pure.parent) if str(pure.parent) != "." else ""
    _ensure_dir(dir_nodes, parent_rel)
    node = Node(name=pure.name, path=Path(rel_path), size=0, is_dir=True, children=[])
    dir_nodes[rel_path] = node
    dir_nodes[parent_rel].children.append(node)


def _compute_sizes(node: Node) -> int:
    """Recursively set directory sizes to the sum of their children's sizes."""
    if not node.is_dir:
        return node.size
    total = sum(_compute_sizes(c) for c in node.children)
    node.size = max(total, 1)
    return node.size
