"""GitHub repository tree source implementation."""

from __future__ import annotations

import os
import urllib.request
from typing import TYPE_CHECKING

from dirplot.github import (
    _default_branch,
    _gh_cli_token,
    build_tree_github,
    is_github_path,
    parse_github_path,
)
from dirplot.sources import register_source

if TYPE_CHECKING:
    from dirplot.scanner import Node


class GitHubSource:
    """Tree source for GitHub repositories via the Git trees API."""

    @property
    def name(self) -> str:
        return "github"

    def can_handle(self, path: str) -> bool:
        """Check if path is a GitHub reference."""
        return is_github_path(path)

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        """Scan a GitHub repository tree.

        Args:
            path: GitHub URL (github://owner/repo[@ref][/subpath] or https://github.com/...)
            exclude: Glob patterns to skip.
            depth: Maximum recursion depth (applied after fetching).

        Returns:
            Root node representing the repository tree.
        """
        owner, repo, ref, subpath = parse_github_path(path)

        # Use the existing build_tree_github function
        root_node, resolved_ref = build_tree_github(
            owner,
            repo,
            ref,
            exclude=exclude,
            depth=depth,
            subpath=subpath,
        )
        return root_node

    def read_file(self, root: str, path: str) -> bytes:
        """Fetch raw file content from GitHub."""
        owner, repo, ref, subpath = parse_github_path(root)
        token = os.environ.get("GITHUB_TOKEN") or _gh_cli_token()
        if not ref:
            ref = _default_branch(owner, repo, token)
        full_path = "/".join(p for p in [subpath, path] if p)
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{full_path}"
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req) as resp:
            return bytes(resp.read())

    def get_display_name(self, path: str) -> str:
        """Get display name for GitHub repository."""
        owner, repo, ref, subpath = parse_github_path(path)
        display = f"{owner}/{repo}"
        if ref:
            display += f"@{ref}"
        if subpath:
            display += f"/{subpath}"
        return display


# Register the source
github_source = GitHubSource()
register_source(github_source)
