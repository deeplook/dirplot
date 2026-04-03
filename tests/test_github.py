"""Tests for GitHub repository tree scanning."""

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dirplot.github import _gh_cli_token, build_tree_github, is_github_path, parse_github_path

# ---------------------------------------------------------------------------
# Mock helper
# ---------------------------------------------------------------------------


def mock_urlopen(responses: dict[str, Any]):
    """Patch urllib.request.urlopen mapping URL substrings to JSON responses."""

    def fake_urlopen(req: Any) -> Any:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for pattern, data in responses.items():
            if pattern in url:
                resp = MagicMock()
                resp.read.return_value = json.dumps(data).encode()
                resp.__enter__ = lambda s: s
                resp.__exit__ = MagicMock(return_value=False)
                return resp
        raise AssertionError(f"Unexpected URL in test: {url}")

    return patch("urllib.request.urlopen", side_effect=fake_urlopen)


def repo_response(default_branch: str = "main") -> dict[str, Any]:
    return {"default_branch": default_branch, "full_name": "owner/repo"}


def tree_response(items: list[dict[str, Any]], truncated: bool = False) -> dict[str, Any]:
    return {"sha": "abc123", "tree": items, "truncated": truncated}


def blob(path: str, size: int) -> dict[str, Any]:
    return {"path": path, "type": "blob", "size": size, "sha": "x"}


def tree(path: str) -> dict[str, Any]:
    return {"path": path, "type": "tree", "sha": "x"}


# ---------------------------------------------------------------------------
# URI helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "s",
    [
        "github://owner/repo",
        "github://owner/repo@main",
        "https://github.com/owner/repo",
        "https://github.com/owner/repo/tree/main",
    ],
)
def test_is_github_path(s: str) -> None:
    assert is_github_path(s)


@pytest.mark.parametrize("s", ["/local/path", "s3://bucket", "ssh://user@host/path", "."])
def test_is_not_github_path(s: str) -> None:
    assert not is_github_path(s)


def test_parse_github_url_scheme_no_branch() -> None:
    assert parse_github_path("github://owner/repo") == ("owner", "repo", None, "")


def test_parse_github_url_scheme_with_branch() -> None:
    assert parse_github_path("github://owner/repo@dev") == ("owner", "repo", "dev", "")


def test_parse_github_url_no_branch() -> None:
    assert parse_github_path("https://github.com/owner/repo") == ("owner", "repo", None, "")


def test_parse_github_url_with_branch() -> None:
    assert parse_github_path("https://github.com/owner/repo/tree/feature-x") == (
        "owner",
        "repo",
        "feature-x",
        "",
    )


def test_parse_github_url_scheme_with_subpath() -> None:
    assert parse_github_path("github://owner/repo/sub/path") == ("owner", "repo", None, "sub/path")


def test_parse_github_url_scheme_with_ref_and_subpath() -> None:
    assert parse_github_path("github://owner/repo@v1.0/sub/path") == (
        "owner",
        "repo",
        "v1.0",
        "sub/path",
    )


def test_parse_github_url_with_branch_and_subpath() -> None:
    assert parse_github_path("https://github.com/owner/repo/tree/main/src/foo") == (
        "owner",
        "repo",
        "main",
        "src/foo",
    )


# ---------------------------------------------------------------------------
# build_tree_github
# ---------------------------------------------------------------------------


def test_build_tree_github_resolves_default_branch() -> None:
    with mock_urlopen(
        {
            "/repos/owner/repo\x00": repo_response("trunk"),  # won't match
            "git/trees": tree_response([blob("README.md", 100)]),
            "/repos/owner/repo": repo_response("trunk"),
        }
    ):
        node, branch = build_tree_github("owner", "repo")
    assert branch == "trunk"


def test_build_tree_github_uses_explicit_branch() -> None:
    with mock_urlopen({"git/trees": tree_response([blob("README.md", 50)])}):
        node, branch = build_tree_github("owner", "repo", "my-branch")
    assert branch == "my-branch"


def test_build_tree_github_flat() -> None:
    items = [blob("app.py", 1000), blob("README.md", 500)]
    with mock_urlopen({"git/trees": tree_response(items)}):
        node, _ = build_tree_github("owner", "repo", "main")

    assert node.is_dir
    assert node.name == "repo"
    assert node.size == 1500
    assert {c.name for c in node.children} == {"app.py", "README.md"}


def test_build_tree_github_extensions() -> None:
    items = [blob("script.py", 100), blob("Makefile", 50)]
    with mock_urlopen({"git/trees": tree_response(items)}):
        node, _ = build_tree_github("owner", "repo", "main")

    py = next(c for c in node.children if c.name == "script.py")
    mk = next(c for c in node.children if c.name == "Makefile")
    assert py.extension == ".py"
    assert mk.extension == "(no ext)"


def test_build_tree_github_nested() -> None:
    items = [tree("src"), blob("src/app.py", 200), blob("src/util.py", 100), blob("README.md", 50)]
    with mock_urlopen({"git/trees": tree_response(items)}):
        node, _ = build_tree_github("owner", "repo", "main")

    assert node.size == 350
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir
    assert src.size == 300
    assert {c.name for c in src.children} == {"app.py", "util.py"}


def test_build_tree_github_skips_dotfiles() -> None:
    items = [blob(".env", 100), blob("app.py", 200), tree(".github"), blob(".github/ci.yml", 50)]
    with mock_urlopen({"git/trees": tree_response(items)}):
        node, _ = build_tree_github("owner", "repo", "main")

    names = {c.name for c in node.children}
    assert "app.py" in names
    assert ".env" not in names
    assert ".github" not in names


def test_build_tree_github_exclude() -> None:
    items = [blob("keep.py", 100), blob("skip.py", 200)]
    with mock_urlopen({"git/trees": tree_response(items)}):
        node, _ = build_tree_github("owner", "repo", "main", exclude=frozenset({"skip.py"}))

    names = {c.name for c in node.children}
    assert "keep.py" in names
    assert "skip.py" not in names


def test_build_tree_github_depth_limit() -> None:
    items = [tree("src"), blob("src/app.py", 200), blob("top.txt", 50)]
    with mock_urlopen({"git/trees": tree_response(items)}):
        node, _ = build_tree_github("owner", "repo", "main", depth=1)

    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir
    assert src.children == []


def test_build_tree_github_zero_size_defaults_to_1() -> None:
    items = [blob("empty.txt", 0)]
    with mock_urlopen({"git/trees": tree_response(items)}):
        node, _ = build_tree_github("owner", "repo", "main")

    assert node.children[0].size == 1


def test_build_tree_github_truncated_warns(capsys: pytest.CaptureFixture[str]) -> None:
    items = [blob("file.py", 100)]
    with mock_urlopen({"git/trees": tree_response(items, truncated=True)}):
        build_tree_github("owner", "repo", "main")


# ---------------------------------------------------------------------------
# _gh_cli_token
# ---------------------------------------------------------------------------


def test_gh_cli_token_not_installed() -> None:
    """Returns None when gh is not on PATH."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert _gh_cli_token() is None


def test_gh_cli_token_authenticated() -> None:
    """Returns the stripped token when gh exits 0."""
    mock_result = MagicMock(returncode=0, stdout="ghp_testtoken123\n")
    with patch("subprocess.run", return_value=mock_result):
        assert _gh_cli_token() == "ghp_testtoken123"


def test_gh_cli_token_not_authenticated() -> None:
    """Returns None when gh exits non-zero (not logged in)."""
    mock_result = MagicMock(returncode=1, stdout="")
    with patch("subprocess.run", return_value=mock_result):
        assert _gh_cli_token() is None


def test_gh_cli_token_timeout() -> None:
    """Returns None when gh times out."""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 5)):
        assert _gh_cli_token() is None


def test_gh_cli_token_empty_output() -> None:
    """Returns None when gh outputs only whitespace."""
    mock_result = MagicMock(returncode=0, stdout="   \n")
    with patch("subprocess.run", return_value=mock_result):
        assert _gh_cli_token() is None


def test_build_tree_github_falls_back_to_gh_cli_token() -> None:
    """build_tree_github uses the gh CLI token when GITHUB_TOKEN is absent."""
    items = [blob("README.md", 100)]
    captured_headers: list[str] = []

    def fake_urlopen(req: Any) -> Any:
        auth = req.get_header("Authorization")
        if auth:
            captured_headers.append(auth)
        resp = MagicMock()
        if "git/trees" in req.full_url:
            resp.read.return_value = json.dumps(tree_response(items)).encode()
        else:
            resp.read.return_value = json.dumps(repo_response()).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    gh_token = MagicMock(return_value="ghp_fromcli")
    with (
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        patch("os.environ.get", return_value=None),
        patch("dirplot.github._gh_cli_token", gh_token),
    ):
        build_tree_github("owner", "repo", "main")

    gh_token.assert_called_once()
    assert any("ghp_fromcli" in h for h in captured_headers)
