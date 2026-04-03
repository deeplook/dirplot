"""Build a Node tree from a git commit and compute per-commit change highlights."""

import contextlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from dirplot.scanner import Node


def git_log(
    repo: Path,
    revision_range: str | None = None,
    max_count: int | None = None,
    last: datetime | None = None,
) -> list[tuple[str, int, str]]:
    """Return commits as (sha, unix_timestamp, subject), oldest-first."""
    cmd = ["git", "-C", str(repo), "log", "--format=%H %at %s", "--reverse"]
    if max_count is not None:
        cmd += [f"-{max_count}"]
    if last is not None:
        cmd += [f"--after={last.strftime('%Y-%m-%dT%H:%M:%SZ')}"]
    if revision_range:
        cmd.append(revision_range)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    commits: list[tuple[str, int, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, _, rest = line.partition(" ")
        ts_str, _, subject = rest.partition(" ")
        try:
            ts = int(ts_str)
        except ValueError:
            ts = 0
        commits.append((sha, ts, subject))
    return commits


def git_initial_files(
    repo: Path,
    commit: str,
    exclude: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Return ``{relative_filepath: size}`` for all tracked blobs at *commit*.

    This is the O(files) baseline scan used only for the first commit.
    Subsequent commits should use :func:`git_apply_diff` to update the dict
    incrementally in O(changed files).
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--long", commit],
        capture_output=True,
        text=True,
        check=True,
    )
    files: dict[str, int] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        meta, sep, filepath = line.partition("\t")
        if not sep or not filepath:
            continue
        parts = meta.split()
        if len(parts) < 4 or parts[1] != "blob":
            continue
        if filepath.split("/")[0] in exclude:
            continue
        try:
            size = max(1, int(parts[3]))
        except ValueError:
            size = 1
        files[filepath] = size
    return files


def _blob_sizes(repo: Path, hashes: list[str]) -> dict[str, int]:
    """Return ``{blob_hash: size}`` for *hashes* via ``git cat-file --batch-check``.

    Runs a single subprocess regardless of how many hashes are requested.
    """
    if not hashes:
        return {}
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-check"],
        input="\n".join(hashes),
        capture_output=True,
        text=True,
        check=True,
    )
    out: dict[str, int] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == "blob":
            with contextlib.suppress(ValueError):
                out[parts[0]] = max(1, int(parts[2]))
    return out


def git_apply_diff(
    repo: Path,
    files: dict[str, int],
    prev_commit: str,
    curr_commit: str,
    exclude: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Update *files* in-place with the changes from *prev_commit* to *curr_commit*.

    Uses ``git diff-tree`` (O(changed files)) instead of re-scanning the full
    tree with ``git ls-tree`` (O(all files)).  Blob sizes for added/modified
    files are fetched in a single ``git cat-file --batch-check`` call.

    Returns a highlights dict ``{abs_path: event_type}`` suitable for passing
    to :func:`~dirplot.render_png.create_treemap`.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "diff-tree", "-r", "--no-commit-id", prev_commit, curr_commit],
        capture_output=True,
        text=True,
        check=True,
    )

    to_add: dict[str, str] = {}  # relative path → new blob hash
    to_delete: list[str] = []
    highlights: dict[str, str] = {}

    for line in result.stdout.splitlines():
        if not line.strip() or not line.startswith(":"):
            continue
        meta, sep, paths = line.partition("\t")
        if not sep:
            continue
        # meta: ":<old_mode> <new_mode> <old_hash> <new_hash> <status[score]>"
        meta_parts = meta.lstrip(":").split()
        if len(meta_parts) < 5:
            continue
        new_hash = meta_parts[3]
        status = meta_parts[4]
        path_list = paths.split("\t")

        if status == "A" and path_list:
            fp = path_list[0]
            if fp.split("/")[0] not in exclude:
                to_add[fp] = new_hash
                highlights[(repo / fp).as_posix()] = "created"
        elif status == "M" and path_list:
            fp = path_list[0]
            if fp.split("/")[0] not in exclude:
                to_add[fp] = new_hash
                highlights[(repo / fp).as_posix()] = "modified"
        elif status == "D" and path_list:
            fp = path_list[0]
            if fp.split("/")[0] not in exclude:
                to_delete.append(fp)
                highlights[(repo / fp).as_posix()] = "deleted"
        elif status.startswith("R") and len(path_list) >= 2:
            old_fp, new_fp = path_list[0], path_list[1]
            if old_fp.split("/")[0] not in exclude:
                to_delete.append(old_fp)
                highlights[str(repo / old_fp)] = "deleted"
            if new_fp.split("/")[0] not in exclude:
                to_add[new_fp] = new_hash
                highlights[str(repo / new_fp)] = "created"
        elif status.startswith("C") and len(path_list) >= 2:
            new_fp = path_list[1]
            if new_fp.split("/")[0] not in exclude:
                to_add[new_fp] = new_hash
                highlights[str(repo / new_fp)] = "created"

    # Fetch all new blob sizes in one batch call.
    if to_add:
        sizes = _blob_sizes(repo, list(to_add.values()))
        for fp, blob_hash in to_add.items():
            files[fp] = sizes.get(blob_hash, 1)

    for fp in to_delete:
        files.pop(fp, None)

    return highlights


def build_node_tree(
    repo: Path,
    files: dict[str, int],
    depth: int | None = None,
) -> Node:
    """Convert a ``{relative_filepath: size}`` dict into a Node tree rooted at *repo*."""
    tree: dict[str, Any] = {}

    for filepath, size in files.items():
        parts = filepath.split("/")

        if depth is not None and len(parts) > depth:
            parts = parts[:depth]

        d = tree
        for part in parts[:-1]:
            entry = d.get(part)
            if entry is None:
                d[part] = {}
                d = d[part]
            elif isinstance(entry, dict):
                d = entry
            else:
                break
        else:
            leaf = parts[-1]
            existing = d.get(leaf)
            if isinstance(existing, dict):
                pass
            elif isinstance(existing, int):
                d[leaf] = existing + size
            else:
                d[leaf] = size

    def _to_node(name: str, path: Path, data: dict[str, Any]) -> Node:
        children: list[Node] = []
        for child_name in sorted(data):
            child_val = data[child_name]
            child_path = path / child_name
            if isinstance(child_val, dict):
                child = _to_node(child_name, child_path, child_val)
            else:
                dot_idx = child_name.rfind(".")
                ext = child_name[dot_idx:].lower() if dot_idx > 0 else "(no ext)"
                child = Node(
                    name=child_name,
                    path=child_path,
                    size=child_val,
                    is_dir=False,
                    extension=ext,
                )
            children.append(child)
        total = sum(c.size for c in children)
        return Node(name=name, path=path, size=max(1, total), is_dir=True, children=children)

    return _to_node(repo.name, repo, tree)


RectMap = dict[str, tuple[int, int, int, int]]


def _render_frame_worker(args: tuple[Any, ...]) -> tuple[int, bytes, RectMap]:
    """Top-level picklable worker for parallel frame rendering.

    Accepts a single tuple so it works with both ``ProcessPoolExecutor.map``
    and ``submit``.  Defined at module level so it can be pickled by ``spawn``
    worker processes.

    Args:
        args: ``(repo_str, files, current_highlights, sha, ts, orig_i,
                 total_commits, depth, log_scale, width_px, height_px,
                 font_size, colormap, cushion, dark)``

    Returns:
        ``(orig_i, png_bytes, rect_map)``
    """
    (
        repo_str,
        files,
        current_highlights,
        sha,
        ts,
        orig_i,
        progress,
        depth,
        log_scale,
        width_px,
        height_px,
        font_size,
        colormap,
        cushion,
        dark,
    ) = args

    from datetime import datetime
    from pathlib import Path

    from dirplot.render_png import create_treemap
    from dirplot.scanner import apply_log_sizes

    repo = Path(repo_str)
    node = build_node_tree(repo, files, depth)
    if log_scale:
        apply_log_sizes(node)

    rect_map: dict[str, tuple[int, int, int, int]] = {}
    dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    buf = create_treemap(
        node,
        width_px,
        height_px,
        font_size,
        colormap,
        None,
        cushion,
        highlights=current_highlights or None,
        rect_map_out=rect_map,
        title_suffix=f"sha:{sha[:8]}  {dt_str}",
        progress=progress,
        dark=dark,
    )
    return (orig_i, buf.read(), rect_map)


def build_tree_from_git(
    repo: Path,
    commit: str,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> Node:
    """Convenience wrapper: full scan of *commit* → Node tree."""
    files = git_initial_files(repo, commit, exclude)
    return build_node_tree(repo, files, depth)
