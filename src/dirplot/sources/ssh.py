"""SSH remote directory tree source implementation."""

from __future__ import annotations

from dirplot.scanner import Node
from dirplot.sources import register_source
from dirplot.ssh import (
    build_tree_ssh,
    connect,
    is_ssh_path,
    parse_ssh_path,
)


class SSHSource:
    """Tree source for remote directories via SSH."""

    @property
    def name(self) -> str:
        return "ssh"

    def can_handle(self, path: str) -> bool:
        """Check if path is an SSH reference."""
        return is_ssh_path(path)

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
        **kwargs: object,
    ) -> Node:
        """Scan a remote directory via SSH.

        Args:
            path: SSH path (ssh://user@host/path or user@host:/path)
            exclude: Glob patterns to skip.
            depth: Maximum recursion depth.
            **kwargs: Additional SSH options (ssh_key, ssh_password, port)

        Returns:
            Root node representing the remote directory tree.
        """
        user, host, remote_path = parse_ssh_path(path)

        # Connect and scan
        ssh_key = kwargs.get("ssh_key")
        ssh_password = kwargs.get("ssh_password")
        port = kwargs.get("port")
        client = connect(
            host,
            user,
            ssh_key=ssh_key if isinstance(ssh_key, str) else None,
            ssh_password=ssh_password if isinstance(ssh_password, str) else None,
            port=port if isinstance(port, int) else None,
        )

        try:
            sftp = client.open_sftp()
            try:
                # Use existing build_tree_ssh function
                root = build_tree_ssh(
                    sftp,
                    remote_path,
                    exclude=exclude,
                    depth=depth,
                )
                # Update root name to show it's remote
                root.name = f"{user}@{host}:{remote_path}"
                return root
            finally:
                sftp.close()
        finally:
            client.close()

    def get_display_name(self, path: str) -> str:
        """Get display name for SSH path."""
        user, host, remote_path = parse_ssh_path(path)
        return f"{user}@{host}:{remote_path}"


# Register the source
ssh_source = SSHSource()
register_source(ssh_source)
