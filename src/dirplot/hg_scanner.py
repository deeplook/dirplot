"""Build a Node tree from a Mercurial changeset and compute per-changeset change highlights."""

import hashlib
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from dirplot.filters import matches_exclude
from dirplot.git_scanner import build_node_tree
from dirplot.scanner import Node


def hg_log(
    repo: Path,
    revision_range: str | None = None,
    max_count: int | None = None,
    last: datetime | None = None,
) -> list[tuple[str, int, str]]:
    """Return changesets as (node_hash, unix_timestamp, subject), oldest-first."""
    if revision_range is not None:
        revset = revision_range
    elif last is not None:
        iso = last.strftime("%Y-%m-%d %H:%M:%S")
        revset = f"sort(date('>{iso}'), date)"
    else:
        revset = "sort(all(), date)"

    cmd = [
        "hg",
        "log",
        "-R",
        str(repo),
        "--template",
        "{node} {date|hgdate} {desc|firstline}\n",
        "-r",
        revset,
    ]
    if max_count is not None:
        cmd += ["--limit", str(max_count)]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    commits: list[tuple[str, int, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # Line format: "{node} {unix_ts} {tz_offset} {subject}"
        # hgdate emits "{unix} {offset}" — take only the first token as timestamp.
        parts = line.split(" ", 3)
        if len(parts) < 2:
            continue
        node = parts[0]
        try:
            ts = int(parts[1])
        except ValueError:
            ts = 0
        subject = parts[3] if len(parts) > 3 else ""
        commits.append((node, ts, subject))
    return commits


def hg_initial_files(
    repo: Path,
    commit: str,
    exclude: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Return ``{relative_filepath: size}`` for all tracked files at *commit*.

    Uses ``hg archive`` to extract the full tree into a temp directory, then
    walks the result to measure file sizes.  Only called once per animation
    (for the first commit).  Subsequent commits should use
    :func:`hg_apply_diff` to update incrementally.
    """
    with tempfile.TemporaryDirectory(prefix="dirplot-hg-") as tmpdir_str:
        # hg archive with -t files does not support --prefix.
        # It creates one subdirectory named "{reponame}-{localrev}/" inside
        # the destination.  We pass a non-existent sub-path so hg creates it,
        # then strip that top-level prefix directory when building paths.
        archive_dest = os.path.join(tmpdir_str, "archive")
        subprocess.run(
            [
                "hg",
                "archive",
                "-R",
                str(repo),
                "-r",
                commit,
                "-t",
                "files",
                archive_dest,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        archive_root = Path(archive_dest)
        # Strip the single prefix directory hg creates (e.g. "repo-3/").
        top_dirs = [d for d in archive_root.iterdir() if d.is_dir()]
        if len(top_dirs) == 1:
            archive_root = top_dirs[0]

        files: dict[str, int] = {}
        for dirpath, _dirs, filenames in os.walk(str(archive_root)):
            for fname in filenames:
                full = Path(dirpath) / fname
                rel_posix = full.relative_to(archive_root).as_posix()
                if rel_posix == ".hg_archival.txt":
                    continue
                if matches_exclude(rel_posix, exclude):
                    continue
                try:
                    size = max(1, full.stat().st_size)
                except OSError:
                    size = 1
                files[rel_posix] = size
        return files


def hg_apply_diff(
    repo: Path,
    files: dict[str, int],
    prev_commit: str,
    curr_commit: str,
    exclude: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Mutate *files* in-place; return highlights ``{abs_posix_path: event_type}``.

    Uses ``hg status --copies`` to detect adds, modifications, removals, and
    renames between *prev_commit* and *curr_commit*.  File sizes for added and
    modified files are fetched one at a time via ``hg cat``.

    Rename detection: when an ``A`` line is followed by an indented line, the
    indented path is the rename source (marked deleted).  The subsequent ``R``
    line for the same source path is then ignored as already handled.
    """
    result = subprocess.run(
        [
            "hg",
            "status",
            "--copies",
            "-R",
            str(repo),
            "--rev",
            prev_commit,
            "--rev",
            curr_commit,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    highlights: dict[str, str] = {}
    to_add: list[str] = []
    rename_sources: set[str] = set()

    lines = result.stdout.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if line.startswith("A "):
            fp = line[2:]
            # If the next line is indented it is the rename/copy source.
            if i + 1 < len(lines) and lines[i + 1].startswith("  "):
                source = lines[i + 1].lstrip()
                rename_sources.add(source)
                i += 1
                if not matches_exclude(fp, exclude):
                    to_add.append(fp)
                    highlights[(repo / fp).as_posix()] = "created"
                if not matches_exclude(source, exclude):
                    files.pop(source, None)
                    highlights[(repo / source).as_posix()] = "deleted"
            else:
                if not matches_exclude(fp, exclude):
                    to_add.append(fp)
                    highlights[(repo / fp).as_posix()] = "created"

        elif line.startswith("M "):
            fp = line[2:]
            if not matches_exclude(fp, exclude):
                to_add.append(fp)
                highlights[(repo / fp).as_posix()] = "modified"

        elif line.startswith("R "):
            fp = line[2:]
            if fp not in rename_sources and not matches_exclude(fp, exclude):
                files.pop(fp, None)
                highlights[(repo / fp).as_posix()] = "deleted"

        i += 1

    for fp in to_add:
        r = subprocess.run(
            ["hg", "cat", "-r", curr_commit, fp],
            capture_output=True,
            check=True,
            cwd=str(repo),
        )
        files[fp] = max(1, len(r.stdout))

    return highlights


def is_hg_repo(path: Path) -> bool:
    """Return True if *path* is the root of a Mercurial repository."""
    return (path / ".hg").is_dir()


def build_tree_hg_worktree(
    repo: Path,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> "Node":
    """Build a Node tree from the working tree, restricted to hg-tracked files.

    Uses ``hg locate`` to enumerate tracked paths, then reads actual on-disk
    sizes. Untracked files are ignored — matches ``hg diff`` semantics.
    """
    result = subprocess.run(
        ["hg", "locate", "-0"],
        capture_output=True,
        cwd=str(repo),
    )
    files: dict[str, int] = {}
    for filepath in result.stdout.split(b"\x00"):
        rel = filepath.decode("utf-8", errors="replace").strip()
        if not rel:
            continue
        if matches_exclude(rel, exclude):
            continue
        abs_path = repo / rel
        try:
            size = max(1, abs_path.stat().st_size)
        except OSError:
            size = 1
        files[rel] = size
    return build_node_tree(repo, files, depth)


def hg_worktree_hashes(repo: Path) -> dict[str, str]:
    """Return ``{relative_filepath: sha1}`` for tracked files in the hg working tree.

    Hashes the on-disk content of each tracked file so change detection is
    accurate regardless of file size.
    """
    result = subprocess.run(
        ["hg", "locate", "-0"],
        capture_output=True,
        cwd=str(repo),
    )
    hashes: dict[str, str] = {}
    for filepath in result.stdout.split(b"\x00"):
        rel = filepath.decode("utf-8", errors="replace").strip()
        if not rel:
            continue
        abs_path = repo / rel
        try:
            content = abs_path.read_bytes()
            hashes[rel] = hashlib.sha1(content).hexdigest()
        except OSError:
            pass
    return hashes
