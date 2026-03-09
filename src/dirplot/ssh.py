"""SSH remote directory scanning via paramiko (optional dependency)."""

from __future__ import annotations

import os
import stat
import sys
import urllib.parse
from getpass import getpass, getuser
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from dirplot.scanner import Node

if TYPE_CHECKING:
    pass  # paramiko types only used as strings below


def _require_paramiko() -> Any:
    try:
        import paramiko  # type: ignore[import-untyped]

        return paramiko
    except ImportError:
        raise ImportError(
            "SSH support requires paramiko. Install it with:\n  pip install dirplot[ssh]"
        ) from None


def load_ssh_config(host: str) -> dict[str, Any]:
    """Parse ~/.ssh/config and return resolved options for *host*."""
    try:
        from paramiko import SSHConfig  # type: ignore[import-untyped]
    except ImportError:
        return {}

    config_path = os.path.expanduser("~/.ssh/config")
    cfg = SSHConfig()
    if os.path.exists(config_path):
        with open(config_path) as f:
            cfg.parse(f)
    return cfg.lookup(host)  # type: ignore[no-any-return]


def is_ssh_path(path_str: str) -> bool:
    """Return True if *path_str* looks like an SSH URI."""
    return path_str.startswith("ssh://") or ("@" in path_str and ":" in path_str)


def parse_ssh_path(path_str: str) -> tuple[str, str, str]:
    """Parse an SSH path string into *(user, host, remote_path)*.

    Accepted formats::

        ssh://user@host/path
        user@host:/path
    """
    if path_str.startswith("ssh://"):
        parsed = urllib.parse.urlparse(path_str)
        user = parsed.username or getuser()
        host = parsed.hostname or ""
        remote_path = parsed.path or "/"
        return user, host, remote_path

    # SCP format: user@host:/path
    userhost, remote_path = path_str.split(":", 1)
    user, host = userhost.split("@", 1)
    return user, host, remote_path


def connect(
    host: str,
    user: str,
    *,
    ssh_key: str | None = None,
    ssh_password: str | None = None,
    port: int | None = None,
) -> Any:
    """Open and return a connected ``paramiko.SSHClient``.

    Resolution order for credentials:

    1. *ssh_key* argument
    2. ``SSH_KEY`` environment variable
    3. ``IdentityFile`` from ``~/.ssh/config``
    4. ssh-agent (paramiko picks this up automatically)
    5. *ssh_password* argument / ``SSH_PASSWORD`` env var
    6. Interactive password prompt as last resort
    """
    paramiko = _require_paramiko()

    ssh_cfg = load_ssh_config(host)
    resolved_host = str(ssh_cfg.get("hostname", host))
    resolved_user = user or str(ssh_cfg.get("user") or os.environ.get("USER") or "root")
    resolved_port = port or int(ssh_cfg.get("port", 22))

    identity_files: list[str] = ssh_cfg.get("identityfile", [])
    key_file = (
        ssh_key
        or os.environ.get("SSH_KEY")
        or (os.path.expanduser(identity_files[0]) if identity_files else None)
    )
    password = ssh_password or os.environ.get("SSH_PASSWORD")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        client.connect(
            resolved_host,
            port=resolved_port,
            username=resolved_user,
            key_filename=key_file,
            password=password,
        )
    except paramiko.AuthenticationException:
        password = getpass(f"Password for {resolved_user}@{resolved_host}: ")
        client.connect(
            resolved_host,
            port=resolved_port,
            username=resolved_user,
            password=password,
        )
    except paramiko.SSHException as exc:
        msg = str(exc)
        if "not found in known_hosts" in msg or "Unknown server" in msg:
            raise SystemExit(
                f"Host '{resolved_host}' not in known_hosts.\n"
                f"Run:  ssh-keyscan {resolved_host} >> ~/.ssh/known_hosts"
            ) from exc
        raise

    return client


def build_tree_ssh(
    sftp: Any,
    remote_path: str,
    exclude: frozenset[str] = frozenset(),
    *,
    depth: int | None = None,
    _progress: list[int] | None = None,
) -> Node:
    """Recursively build a :class:`~dirplot.scanner.Node` tree via SFTP.

    Args:
        sftp: An open ``paramiko.SFTPClient``.
        remote_path: Absolute path on the remote host.
        exclude: Set of absolute remote paths to skip.
        depth: Maximum recursion depth. ``None`` means unlimited.
            ``depth=1`` lists direct children without recursing into subdirs.
        _progress: Internal one-element counter for progress reporting.
    """
    try:
        attrs = sftp.listdir_attr(remote_path)
    except PermissionError:
        return Node(
            name=PurePosixPath(remote_path).name or remote_path,
            path=Path(remote_path),
            size=1,
            is_dir=True,
            extension="",
            children=[],
        )
    except (OSError, EOFError) as exc:
        raise OSError(f"SSH connection lost while scanning {remote_path}: {exc}") from exc

    children: list[Node] = []
    for attr in sorted(attrs, key=lambda a: a.filename):
        full = remote_path.rstrip("/") + "/" + attr.filename

        if full in exclude or attr.filename.startswith("."):
            continue

        mode: int | None = attr.st_mode
        if mode is not None and stat.S_ISLNK(mode):
            continue

        if _progress is not None:
            _progress[0] += 1
            if _progress[0] % 100 == 0:
                print(
                    f"\r  scanned {_progress[0]} entries…",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

        if mode is not None and stat.S_ISDIR(mode):
            if depth is not None and depth <= 1:
                # Depth limit reached — include the dir node but don't recurse.
                child = Node(
                    name=attr.filename,
                    path=Path(full),
                    size=1,
                    is_dir=True,
                    extension="",
                )
            else:
                child = build_tree_ssh(
                    sftp,
                    full,
                    exclude,
                    depth=None if depth is None else depth - 1,
                    _progress=_progress,
                )
        else:
            ext = PurePosixPath(attr.filename).suffix.lower() or "(no ext)"
            child = Node(
                name=attr.filename,
                path=Path(full),
                size=attr.st_size or 1,
                is_dir=False,
                extension=ext,
            )

        children.append(child)

    total = sum(c.size for c in children) or 1
    return Node(
        name=PurePosixPath(remote_path).name or remote_path,
        path=Path(remote_path),
        size=total,
        is_dir=True,
        extension="",
        children=children,
    )
