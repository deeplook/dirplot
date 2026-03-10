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


def parse_github_path(s: str) -> tuple[str, str, str | None]:
    """Parse a GitHub reference into *(owner, repo, branch_or_None)*.

    Accepted formats::

        github://owner/repo
        github://owner/repo@branch
        https://github.com/owner/repo
        https://github.com/owner/repo/tree/branch
    """
    if s.startswith("github://"):
        rest = s[len("github://") :]
        branch: str | None
        if "@" in rest:
            repo_part, branch = rest.rsplit("@", 1)
        else:
            repo_part, branch = rest, None
        owner, repo = repo_part.split("/", 1)
        return owner, repo.rstrip("/"), branch

    # URL form: https://github.com/owner/repo[/tree/branch]
    parts = s.split("github.com/", 1)[1].strip("/").split("/")
    owner = parts[0]
    repo = parts[1]
    branch = parts[3] if len(parts) > 3 and parts[2] == "tree" else None
    return owner, repo, branch


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


def _default_branch(owner: str, repo: str, token: str | None) -> str:
    data = _api_get(f"https://api.github.com/repos/{owner}/{repo}", token)
    return str(data["default_branch"])


def build_tree_github(
    owner: str,
    repo: str,
    branch: str | None = None,
    *,
    token: str | None = None,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> tuple[Node, str]:
    """Fetch a GitHub repository tree and return *(root_node, resolved_branch)*.

    Uses ``GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1`` — a single
    API call that returns the complete file tree with sizes for all blobs.

    Args:
        owner: GitHub username or organisation.
        repo: Repository name.
        branch: Branch, tag, or commit SHA. Defaults to the repo's default branch.
        token: GitHub personal access token. Falls back to ``GITHUB_TOKEN`` env var.
            Public repos work without a token but are rate-limited (60 req/h).
        exclude: Set of paths (relative to repo root) to skip.
        depth: Maximum recursion depth. ``None`` means unlimited.
    """
    token = token or os.environ.get("GITHUB_TOKEN")
    resolved = branch or _default_branch(owner, repo, token)

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

    node = _items_to_tree(data["tree"], repo, exclude, depth)
    return node, resolved


def _items_to_tree(
    items: list[dict[str, Any]],
    repo: str,
    exclude: frozenset[str],
    depth: int | None,
) -> Node:
    """Build a Node tree from the flat list returned by the GitHub trees API."""
    by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        p = PurePosixPath(item["path"])
        parent = str(p.parent)
        if parent == ".":
            parent = ""
        item["_name"] = p.name
        by_parent[parent].append(item)

    def recurse(prefix: str, name: str, current_depth: int | None) -> Node:
        children: list[Node] = []
        for item in sorted(by_parent.get(prefix, []), key=lambda i: i["_name"]):
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
            path=Path(prefix) if prefix else Path(repo),
            size=total,
            is_dir=True,
            extension="",
            children=children,
        )

    return recurse("", repo, depth)
