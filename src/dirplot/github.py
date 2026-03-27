"""GitHub repository tree scanning via the Git trees API (no extra dependencies)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from dirplot.scanner import Node


def is_github_path(s: str) -> bool:
    """Return True if *s* looks like a GitHub repository reference."""
    return s.startswith("github://") or "github.com/" in s


def parse_github_path(s: str) -> tuple[str, str, str | None, str]:
    """Parse a GitHub reference into *(owner, repo, ref_or_None, subpath)*.

    The ref may be a branch name, tag, or commit SHA — all are passed directly
    to the GitHub trees API which accepts any git ref.

    Accepted formats::

        github://owner/repo
        github://owner/repo@ref
        github://owner/repo/sub/path
        github://owner/repo@ref/sub/path
        https://github.com/owner/repo
        https://github.com/owner/repo/tree/ref
        https://github.com/owner/repo/tree/ref/sub/path
    """
    if s.startswith("github://"):
        rest = s[len("github://") :]
        parts = rest.split("/")
        owner = parts[0]
        repo_seg = parts[1] if len(parts) > 1 else ""
        ref: str | None
        if "@" in repo_seg:
            repo, ref = repo_seg.split("@", 1)
        else:
            repo, ref = repo_seg, None
        subpath = "/".join(parts[2:])
        return owner, repo, ref, subpath

    # URL form: https://github.com/owner/repo[/tree/ref[/subpath]]
    parts = s.split("github.com/", 1)[1].strip("/").split("/")
    owner = parts[0]
    repo = parts[1]
    if len(parts) > 3 and parts[2] == "tree":
        ref = parts[3]
        subpath = "/".join(parts[4:])
    else:
        ref = None
        subpath = ""
    return owner, repo, ref, subpath


def _api_get(url: str, token: str | None) -> Any:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise PermissionError(
                "GitHub authentication failed — token invalid or expired. "
                "Set GITHUB_TOKEN or use --github-token."
            ) from exc
        if exc.code == 403:
            # Could be rate-limit (unauthenticated: 60 req/h) or repo permissions.
            body = exc.read().decode(errors="replace")
            if "rate limit" in body.lower():
                raise PermissionError(
                    "GitHub API rate limit exceeded (60 req/h without a token). "
                    "Set GITHUB_TOKEN or use --github-token to raise the limit to 5,000 req/h."
                ) from exc
            raise PermissionError(
                "GitHub access denied — the repository may be private. "
                "Set GITHUB_TOKEN or use --github-token."
            ) from exc
        if exc.code == 404:
            raise FileNotFoundError(
                f"GitHub repository or branch not found: {url}\n"
                "Check the owner/repo spelling and branch name. "
                "Private repositories require GITHUB_TOKEN or --github-token."
            ) from exc
        raise


def count_commits_github(owner: str, repo: str, ref: str | None, token: str | None) -> int | None:
    """Return the total commit count on *ref* using a single cheap API call.

    Fetches one commit and reads the ``page`` number from the ``Link: rel="last"``
    response header.  Returns ``None`` if the count cannot be determined.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1"
    if ref:
        url += f"&sha={ref}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            link = resp.getheader("Link") or ""
            for part in link.split(","):
                if 'rel="last"' in part:
                    url_part = part.split(";")[0].strip().strip("<>")
                    for param in url_part.split("?", 1)[-1].split("&"):
                        if param.startswith("page="):
                            return int(param[5:])
            # No "last" link — all commits fit on one page (≤1 here since per_page=1)
            data = json.loads(resp.read())
            return len(data)
    except Exception:
        return None


def _default_branch(owner: str, repo: str, token: str | None) -> str:
    data = _api_get(f"https://api.github.com/repos/{owner}/{repo}", token)
    return str(data["default_branch"])


def build_tree_github(
    owner: str,
    repo: str,
    ref: str | None = None,
    *,
    token: str | None = None,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
    subpath: str = "",
) -> tuple[Node, str]:
    """Fetch a GitHub repository tree and return *(root_node, resolved_ref)*.

    Uses ``GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1`` — a single
    API call that returns the complete file tree with sizes for all blobs.

    Args:
        owner: GitHub username or organisation.
        repo: Repository name.
        ref: Branch, tag, or commit SHA. Defaults to the repo's default branch.
        token: GitHub personal access token. Falls back to ``GITHUB_TOKEN`` env var.
            Public repos work without a token but are rate-limited (60 req/h).
        exclude: Set of paths (relative to repo root) to skip.
        depth: Maximum recursion depth. ``None`` means unlimited.
        subpath: Optional subdirectory within the repo to use as the tree root.
    """
    token = token or os.environ.get("GITHUB_TOKEN")
    resolved = ref or _default_branch(owner, repo, token)

    data = _api_get(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{resolved}?recursive=1",
        token,
    )

    if data.get("truncated"):
        print(
            "Warning: GitHub truncated the tree (repository too large). "
            "Results are incomplete — use --depth to limit the scan.",
            file=sys.stderr,
        )

    node = _items_to_tree(data["tree"], repo, exclude, depth, subpath)
    return node, resolved


def _items_to_tree(
    items: list[dict[str, Any]],
    repo: str,
    exclude: frozenset[str],
    depth: int | None,
    subpath: str = "",
) -> Node:
    """Build a Node tree from the flat list returned by the GitHub trees API."""
    prefix = subpath.strip("/")
    if prefix:
        root_name = PurePosixPath(prefix).name
        filtered: list[dict[str, Any]] = []
        for item in items:
            p = item["path"]
            if p == prefix:
                continue  # the directory itself — not a child
            if p.startswith(prefix + "/"):
                item = dict(item, path=p[len(prefix) + 1 :])
                filtered.append(item)
        if not filtered:
            raise FileNotFoundError(f"Subpath '{prefix}' not found in repository '{repo}'.")
        items = filtered
    else:
        root_name = repo

    by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        p = PurePosixPath(item["path"])
        parent = str(p.parent)
        if parent == ".":
            parent = ""
        item["_name"] = p.name
        by_parent[parent].append(item)

    def recurse(rel_prefix: str, name: str, current_depth: int | None) -> Node:
        children: list[Node] = []
        for item in sorted(by_parent.get(rel_prefix, []), key=lambda i: i["_name"]):
            if item["_name"].startswith("."):
                continue
            if item["path"] in exclude:
                continue
            if item["type"] == "tree":
                if current_depth is not None and current_depth <= 1:
                    child: Node = Node(
                        name=item["_name"],
                        path=Path(item["path"]),
                        size=1,
                        is_dir=True,
                        extension="",
                    )
                else:
                    child = recurse(
                        item["path"],
                        item["_name"],
                        None if current_depth is None else current_depth - 1,
                    )
            else:
                ext = PurePosixPath(item["_name"]).suffix.lower() or "(no ext)"
                child = Node(
                    name=item["_name"],
                    path=Path(item["path"]),
                    size=max(1, item.get("size") or 1),
                    is_dir=False,
                    extension=ext,
                )
            children.append(child)

        total = sum(c.size for c in children) or 1
        return Node(
            name=name,
            path=Path(rel_prefix) if rel_prefix else Path(root_name),
            size=total,
            is_dir=True,
            extension="",
            children=children,
        )

    return recurse("", root_name, depth)
