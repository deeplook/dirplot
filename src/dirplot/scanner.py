"""Directory scanning and tree construction."""

import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Node:
    """A node in the directory tree."""

    name: str
    path: Path
    size: int  # bytes; sum of all descendants for directories
    is_dir: bool
    extension: str = ""
    children: list["Node"] = field(default_factory=list)
    original_size: int = 0  # set by apply_log_sizes; 0 means size was never transformed


def build_tree(
    root: Path,
    exclude: frozenset[Path] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Recursively build a Node tree from *root*.

    Args:
        root: Directory to scan.
        exclude: Resolved absolute paths to skip entirely.
        depth: Maximum recursion depth. ``None`` means unlimited.
            ``depth=1`` lists direct children without recursing into subdirs.

    Returns:
        Root node whose ``size`` is the total size of all descendants.
    """
    children: list[Node] = []
    total = 0
    try:
        entries = list(root.iterdir())
    except PermissionError:
        return Node(name=root.name, path=root, size=0, is_dir=True)

    for entry in sorted(entries, key=lambda e: e.name):
        if entry.resolve() in exclude:
            continue
        if entry.is_symlink():
            continue
        if entry.is_dir():
            if depth is not None and depth <= 1:
                child = Node(name=entry.name, path=entry, size=1, is_dir=True)
            else:
                child = build_tree(entry, exclude, None if depth is None else depth - 1)
        elif entry.is_file():
            try:
                size = max(1, entry.stat().st_size)
            except OSError:
                size = 1
            ext = entry.suffix.lower() if entry.suffix else "(no ext)"
            child = Node(name=entry.name, path=entry, size=size, is_dir=False, extension=ext)
        else:
            continue
        children.append(child)
        total += child.size

    return Node(name=root.name, path=root, size=total, is_dir=True, children=children)


def prune_to_subtrees(node: Node, paths: set[str]) -> Node:
    """Return *node* keeping only the subtrees at *paths* (relative to *node*).

    Paths may be multi-level (e.g. ``"src/dirplot/fonts"``).  Intermediate
    nodes are kept as synthetic wrappers containing only the requested chain.
    If a path targets a node directly (e.g. ``"src"``), its full subtree is kept.
    Unknown paths are silently ignored.  The root's size is recalculated.
    """
    # Group paths by their first component → remainder (empty string = keep whole subtree)
    groups: dict[str, set[str]] = {}
    for p in paths:
        parts = Path(p).parts
        if not parts:
            continue
        first = parts[0]
        rest = str(Path(*parts[1:])) if len(parts) > 1 else ""
        groups.setdefault(first, set()).add(rest)

    kept: list[Node] = []
    for child in node.children:
        if child.name not in groups:
            continue
        sub_paths = groups[child.name]
        if "" in sub_paths or not child.is_dir:
            kept.append(child)
        else:
            kept.append(prune_to_subtrees(child, sub_paths))

    return Node(
        name=node.name,
        path=node.path,
        size=sum(c.size for c in kept),
        is_dir=True,
        children=kept,
    )


def build_tree_multi(
    roots: list[Path],
    exclude: frozenset[Path] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Scan each path in *roots* independently, then wrap them under their common parent.

    Intermediate directories between the common parent and each root are
    represented as synthetic (empty-except-for-the-chain) nodes — they are
    not scanned for other contents.
    """
    import os

    resolved = [r.resolve() for r in roots]

    if len(resolved) == 1:
        return build_tree(resolved[0], exclude, depth)

    common = Path(os.path.commonpath([str(r) for r in resolved]))

    # Scan each target independently (dirs recurse; files become leaf nodes)
    def _scan_one(r: Path) -> Node:
        if r.is_dir():
            return build_tree(r, exclude, depth)
        try:
            file_size = max(1, r.stat().st_size)
        except OSError:
            file_size = 1
        ext = r.suffix.lower() if r.suffix else "(no ext)"
        return Node(name=r.name, path=r, size=file_size, is_dir=False, extension=ext)

    scanned: list[tuple[Path, Node]] = [(r, _scan_one(r)) for r in resolved]

    def _combine(parent: Path, targets: list[tuple[Path, Node]]) -> Node:
        """Build a synthetic Node for *parent* containing exactly the given *targets*."""
        groups: dict[Path, list[tuple[Path, Node]]] = {}
        for tpath, tnode in targets:
            direct = parent / tpath.relative_to(parent).parts[0]
            groups.setdefault(direct, []).append((tpath, tnode))

        children: list[Node] = []
        for child_path, child_targets in sorted(groups.items(), key=lambda kv: kv[0].name):
            if len(child_targets) == 1 and child_targets[0][0] == child_path:
                # Direct child IS the scanned target
                children.append(child_targets[0][1])
            else:
                # Need a synthetic intermediate node
                children.append(_combine(child_path, child_targets))

        total = sum(c.size for c in children)
        return Node(name=parent.name, path=parent, size=total, is_dir=True, children=children)

    return _combine(common, scanned)


def apply_log_sizes(node: Node, logscale: float = 4.0) -> None:
    """Replace file sizes with log-scaled values in-place, then recompute directory totals.

    The original byte count is preserved in ``node.original_size`` so that renderers
    can display the real size rather than the log-transformed layout value.

    Args:
        node: The root node of the tree to transform.
        logscale: Controls the compression ratio. After transformation the ratio of
            the largest to smallest file-size layout value equals *logscale*.  Must
            be greater than 1.  Default is 4.
    """
    # First pass: collect all leaf sizes to determine the transformation parameters.
    leaf_sizes: list[int] = []

    def _collect(n: Node) -> None:
        if not n.is_dir:
            leaf_sizes.append(max(1, n.size))
        else:
            for c in n.children:
                _collect(c)

    _collect(node)

    if not leaf_sizes:
        return

    min_s = min(leaf_sizes)
    max_s = max(leaf_sizes)
    log_range = math.log(max_s) - math.log(min_s) if max_s > min_s else 1.0
    # Scale factor: normalise log values to [1, logscale], then multiply by 1000
    # to keep layout values in a similar integer magnitude to the old implementation.
    scale = 1000.0 * (logscale - 1) / log_range if log_range > 0 else 1.0

    def _apply(n: Node) -> None:
        if not n.is_dir:
            n.original_size = n.size
            log_val = math.log(max(1, n.size)) - math.log(min_s)
            n.size = max(1, round(1000 + log_val * scale))
            return
        n.original_size = n.size
        for c in n.children:
            _apply(c)
        n.size = sum(c.size for c in n.children)

    _apply(node)


def count_nodes(node: Node) -> tuple[int, int]:
    """Return *(n_files, n_dirs)* for the subtree rooted at *node*.

    *node* itself is not counted — only its descendants.
    """
    files = 0
    dirs = 0
    for child in node.children:
        if child.is_dir:
            dirs += 1
            cf, cd = count_nodes(child)
            files += cf
            dirs += cd
        else:
            files += 1
    return files, dirs


def _apply_breadcrumbs_recursive(node: Node) -> Node:
    """Recursively collapse single-subdirectory chains (internal helper)."""
    node.children = [_apply_breadcrumbs_recursive(c) for c in node.children]
    dir_children = [c for c in node.children if c.is_dir]
    file_children = [c for c in node.children if not c.is_dir]
    if node.is_dir and len(dir_children) == 1 and len(file_children) == 0:
        child = dir_children[0]
        node.name = f"{node.name} / {child.name}"
        node.children = child.children
    return node


def apply_breadcrumbs(node: Node) -> Node:
    """Collapse single-subdirectory chains into one node with a combined name.

    A directory that has exactly one directory child and no file children is
    merged with that child: the names are joined with `` / `` and the child's
    children become this node's children.  The process is bottom-up so chains
    of any length accumulate naturally.

    The root node itself is never collapsed — only its descendants are.
    """
    node.children = [_apply_breadcrumbs_recursive(c) for c in node.children]
    return node


def max_depth(node: Node) -> int:
    """Return the maximum depth of the tree rooted at *node*.

    A leaf node (no children) has depth 0.
    """
    if not node.children:
        return 0
    return 1 + max(max_depth(c) for c in node.children)


def collect_extensions(node: Node) -> list[str]:
    """Return a flat list of file extensions under *node*."""
    if not node.is_dir:
        return [node.extension]
    exts: list[str] = []
    for child in node.children:
        exts.extend(collect_extensions(child))
    return exts


def _fmt_size(n: int) -> str:
    """Format byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def _collect_files(node: Node) -> list[Node]:
    """Return a flat list of all file nodes under *node*."""
    if not node.is_dir:
        return [node]
    result: list[Node] = []
    for child in node.children:
        result.extend(_collect_files(child))
    return result


def _collect_dirs(node: Node) -> list[Node]:
    """Return a flat list of all directory nodes under *node* (excluding root)."""
    result: list[Node] = []
    for child in node.children:
        if child.is_dir:
            result.append(child)
            result.extend(_collect_dirs(child))
    return result


def tree_metrics_dict(
    root_node: Node,
    t_scan: float,
    top_n: int = 10,
    sort_by: str = "count",
) -> dict:
    """Return a dict of metrics for the scanned tree.

    *sort_by* controls extension ordering: ``"count"`` (default) or ``"size"``.
    """
    from collections import Counter, defaultdict

    n_files, n_dirs = count_nodes(root_node)
    depth = max_depth(root_node)
    all_files = _collect_files(root_node)
    all_dirs = _collect_dirs(root_node)
    empty_dirs = sum(1 for d in all_dirs if not d.children)
    total = root_node.size or 1  # guard against zero-size trees

    # Extension stats: count + total bytes
    ext_sizes: dict[str, int] = defaultdict(int)
    ext_counts_raw: Counter[str] = Counter()
    for f in all_files:
        ext_counts_raw[f.extension] += 1
        ext_sizes[f.extension] += f.size

    if sort_by == "size":
        sorted_exts = sorted(ext_sizes.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    else:
        sorted_exts = [(e, ext_sizes[e]) for e, _ in ext_counts_raw.most_common(top_n)]

    top_extensions = [
        {
            "ext": ext if ext else "(no ext)",
            "count": ext_counts_raw[ext],
            "size_bytes": ext_sizes[ext],
        }
        for ext, _ in sorted_exts
    ]

    largest_files = sorted(all_files, key=lambda n: n.size, reverse=True)[:top_n]
    largest_dirs = sorted(all_dirs, key=lambda n: n.size, reverse=True)[:top_n]

    return {
        "files": n_files,
        "dirs": n_dirs,
        "empty_dirs": empty_dirs,
        "total_size_bytes": root_node.size,
        "depth": depth,
        "scan_time_s": round(t_scan, 3),
        "top_extensions": top_extensions,
        "largest_files": [
            {
                "path": str(f.path),
                "size_bytes": f.size,
                "pct": round(100 * f.size / total, 1),
            }
            for f in largest_files
        ],
        "largest_dirs": [
            {
                "path": str(d.path),
                "size_bytes": d.size,
                "pct": round(100 * d.size / total, 1),
            }
            for d in largest_dirs
        ],
    }


def tree_metrics(
    root_node: Node,
    t_scan: float,
    top_n: int = 10,
    sort_by: str = "count",
) -> str:
    """Return a human-readable metrics string for the scanned tree.

    *sort_by* controls extension ordering: ``"count"`` (default) or ``"size"``.
    """
    m = tree_metrics_dict(root_node, t_scan, top_n=top_n, sort_by=sort_by)
    total = m["total_size_bytes"] or 1

    lines: list[str] = [
        f"  Files:      {m['files']:,}",
        f"  Dirs:       {m['dirs']:,}  ({m['empty_dirs']:,} empty)",
        f"  Total size: {_fmt_size(total)}",
        f"  Depth:      {m['depth']}",
        f"  Scan time:  {m['scan_time_s']:.2f}s",
        f"  Top extensions ({len(m['top_extensions'])}) [by {sort_by}]:",
    ]
    for e in m["top_extensions"]:
        label = e["ext"]
        lines.append(f"    {label:<20} {e['count']:>6,}    {_fmt_size(e['size_bytes'])}")

    lines.append("  Largest files:")
    for f in m["largest_files"]:
        size_str = _fmt_size(f["size_bytes"])
        lines.append(f"    {size_str:<10}  {f['pct']:>5.1f}%  {f['path']}")

    lines.append("  Largest dirs:")
    for d in m["largest_dirs"]:
        size_str = _fmt_size(d["size_bytes"])
        lines.append(f"    {size_str:<10}  {d['pct']:>5.1f}%  {d['path']}")

    return "\n".join(lines)
