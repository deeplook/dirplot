"""Tests for SSH remote directory scanning."""

import getpass
import os
import stat as stat_module
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dirplot.scanner import build_tree
from dirplot.ssh import build_tree_ssh, is_ssh_path, parse_ssh_path

# ---------------------------------------------------------------------------
# Localhost integration helpers
# ---------------------------------------------------------------------------


def _localhost_sftp():
    """Return an open SFTPClient connected to localhost, or None if unavailable.

    Tries the user's default key files. Returns None (causes test to skip)
    if the SSH server is unreachable or auth fails for any reason.
    """
    try:
        import paramiko  # type: ignore[import-untyped]
    except ImportError:
        return None

    candidate_keys = [
        os.path.expanduser(p)
        for p in ("~/.ssh/id_ed25519", "~/.ssh/id_rsa", "~/.ssh/id_ecdsa")
        if os.path.exists(os.path.expanduser(p))
    ]

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    for key_file in candidate_keys:
        try:
            client.connect(
                "localhost",
                username=getpass.getuser(),
                key_filename=key_file,
                timeout=5,
            )
            return client.open_sftp()
        except Exception:
            continue

    # Last resort: agent or any cached creds
    try:
        client.connect("localhost", username=getpass.getuser(), timeout=5)
        return client.open_sftp()
    except Exception:
        return None


def make_attr(
    filename: str, size: int, *, is_dir: bool = False, is_link: bool = False
) -> MagicMock:
    attr = MagicMock()
    attr.filename = filename
    attr.st_size = size
    attr.st_mtime = 1_700_000_000.0
    if is_link:
        attr.st_mode = stat_module.S_IFLNK | 0o777
    elif is_dir:
        attr.st_mode = stat_module.S_IFDIR | 0o755
    else:
        attr.st_mode = stat_module.S_IFREG | 0o644
    return attr


# ---------------------------------------------------------------------------
# URI helpers
# ---------------------------------------------------------------------------


def test_is_ssh_path_ssh_uri() -> None:
    assert is_ssh_path("ssh://user@host/path")


def test_is_ssh_path_scp_style() -> None:
    assert is_ssh_path("user@host:/path")


@pytest.mark.parametrize("path", ["/local/path", "relative/path", "."])
def test_is_ssh_path_local(path: str) -> None:
    assert not is_ssh_path(path)


def test_parse_ssh_path_ssh_uri() -> None:
    user, host, path = parse_ssh_path("ssh://alice@prod.example.com/var/www")
    assert user == "alice"
    assert host == "prod.example.com"
    assert path == "/var/www"


def test_parse_ssh_path_scp_style() -> None:
    user, host, path = parse_ssh_path("alice@prod.example.com:/var/www")
    assert user == "alice"
    assert host == "prod.example.com"
    assert path == "/var/www"


# ---------------------------------------------------------------------------
# build_tree_ssh
# ---------------------------------------------------------------------------


def test_build_tree_ssh_flat_directory() -> None:
    sftp = MagicMock()
    sftp.listdir_attr.return_value = [
        make_attr("file.py", 1000),
        make_attr("README.md", 500),
    ]

    node = build_tree_ssh(sftp, "/home/user/project")
    assert node.is_dir
    assert node.name == "project"
    assert node.size == 1500
    assert {c.name for c in node.children} == {"file.py", "README.md"}


def test_build_tree_ssh_extensions() -> None:
    sftp = MagicMock()
    sftp.listdir_attr.return_value = [
        make_attr("script.py", 100),
        make_attr("Makefile", 50),
    ]

    node = build_tree_ssh(sftp, "/project")
    py = next(c for c in node.children if c.name == "script.py")
    mk = next(c for c in node.children if c.name == "Makefile")
    assert py.extension == ".py"
    assert mk.extension == "(no ext)"


def test_build_tree_ssh_skips_dotfiles() -> None:
    sftp = MagicMock()
    sftp.listdir_attr.return_value = [
        make_attr(".hidden", 100),
        make_attr("visible.txt", 200),
    ]

    node = build_tree_ssh(sftp, "/project")
    names = {c.name for c in node.children}
    assert "visible.txt" in names
    assert ".hidden" not in names


def test_build_tree_ssh_skips_symlinks() -> None:
    sftp = MagicMock()
    sftp.listdir_attr.return_value = [
        make_attr("real.txt", 100),
        make_attr("link.txt", 0, is_link=True),
    ]

    node = build_tree_ssh(sftp, "/project")
    names = {c.name for c in node.children}
    assert "real.txt" in names
    assert "link.txt" not in names


def test_build_tree_ssh_recurses_into_dirs() -> None:
    sftp = MagicMock()

    def listdir_attr(path: str) -> list[MagicMock]:
        if path == "/project":
            return [make_attr("subdir", 0, is_dir=True), make_attr("top.txt", 100)]
        if path == "/project/subdir":
            return [make_attr("inner.py", 200)]
        return []

    sftp.listdir_attr.side_effect = listdir_attr

    node = build_tree_ssh(sftp, "/project")
    assert node.size == 300
    subdir = next(c for c in node.children if c.name == "subdir")
    assert subdir.is_dir
    assert subdir.size == 200


def test_build_tree_ssh_permission_error() -> None:
    sftp = MagicMock()
    sftp.listdir_attr.side_effect = PermissionError("denied")

    node = build_tree_ssh(sftp, "/restricted")
    assert node.is_dir
    assert node.children == []
    assert node.size == 1


def test_build_tree_ssh_none_size_defaults_to_1() -> None:
    sftp = MagicMock()
    attr = make_attr("file.bin", 0)
    attr.st_size = None
    sftp.listdir_attr.return_value = [attr]

    node = build_tree_ssh(sftp, "/project")
    assert node.children[0].size == 1


def test_build_tree_ssh_exclude() -> None:
    sftp = MagicMock()
    sftp.listdir_attr.return_value = [
        make_attr("keep.py", 100),
        make_attr("skip.py", 200),
    ]

    node = build_tree_ssh(sftp, "/project", exclude=frozenset({"/project/skip.py"}))
    names = {c.name for c in node.children}
    assert "keep.py" in names
    assert "skip.py" not in names


def test_build_tree_ssh_depth_limit() -> None:
    sftp = MagicMock()

    def listdir_attr(path: str) -> list[MagicMock]:
        if path == "/project":
            return [make_attr("subdir", 0, is_dir=True), make_attr("top.txt", 100)]
        if path == "/project/subdir":
            return [make_attr("deep.py", 500)]
        return []

    sftp.listdir_attr.side_effect = listdir_attr

    # depth=1: list root's direct children, no recursion into subdirs
    node = build_tree_ssh(sftp, "/project", depth=1)
    subdir = next(c for c in node.children if c.name == "subdir")
    assert subdir.is_dir
    assert subdir.children == []
    # listdir_attr should only have been called once (for the root)
    sftp.listdir_attr.assert_called_once_with("/project")


def test_build_tree_ssh_ioerror_raises() -> None:
    sftp = MagicMock()
    sftp.listdir_attr.side_effect = OSError("connection reset")

    with pytest.raises(IOError, match="SSH connection lost"):
        build_tree_ssh(sftp, "/project")


# ---------------------------------------------------------------------------
# Localhost integration tests (skipped when SSH to localhost is unavailable)
# ---------------------------------------------------------------------------


def test_ssh_localhost_matches_local_scan(tmp_path: Path) -> None:
    """SSH scan of a local directory must produce the same tree as build_tree()."""
    sftp = _localhost_sftp()
    if sftp is None:
        pytest.skip("SSH to localhost not available")

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_bytes(b"x" * 100)
    (tmp_path / "src" / "util.py").write_bytes(b"x" * 200)
    (tmp_path / "README.md").write_bytes(b"x" * 50)

    try:
        ssh_node = build_tree_ssh(sftp, str(tmp_path))
    finally:
        sftp.close()

    local_node = build_tree(tmp_path)

    assert ssh_node.size == local_node.size
    assert ssh_node.name == local_node.name
    assert {c.name for c in ssh_node.children} == {c.name for c in local_node.children}


def test_ssh_localhost_file_attributes(tmp_path: Path) -> None:
    """SSH scan returns correct sizes and extensions for each file."""
    sftp = _localhost_sftp()
    if sftp is None:
        pytest.skip("SSH to localhost not available")

    (tmp_path / "hello.py").write_bytes(b"x" * 123)
    (tmp_path / "Makefile").write_bytes(b"x" * 45)

    try:
        node = build_tree_ssh(sftp, str(tmp_path))
    finally:
        sftp.close()

    py = next(c for c in node.children if c.name == "hello.py")
    mk = next(c for c in node.children if c.name == "Makefile")

    assert py.size == 123
    assert py.extension == ".py"
    assert mk.size == 45
    assert mk.extension == "(no ext)"


def test_ssh_localhost_exclude(tmp_path: Path) -> None:
    """Excluded paths are omitted from the SSH scan."""
    sftp = _localhost_sftp()
    if sftp is None:
        pytest.skip("SSH to localhost not available")

    (tmp_path / "keep.py").write_bytes(b"x" * 10)
    (tmp_path / "skip.py").write_bytes(b"x" * 20)

    try:
        node = build_tree_ssh(
            sftp,
            str(tmp_path),
            exclude=frozenset({str(tmp_path / "skip.py")}),
        )
    finally:
        sftp.close()

    names = {c.name for c in node.children}
    assert "keep.py" in names
    assert "skip.py" not in names
