# SSH Remote Directory Tree Scanning via Paramiko

## 1. Goal

dirplot currently operates exclusively on local filesystems. Adding SSH support would allow users to scan and visualise directory trees on remote machines — production servers, NAS boxes, cloud VMs, or any host reachable via SSH — without first copying files locally. The typical workflow would be to run `dirplot ssh://user@host/var/log` and receive the same treemap that `dirplot /var/log` would produce when run on that host. This is useful for auditing disk usage on servers you administer, exploring large datasets stored on remote storage, or quickly identifying what is consuming space on a machine where you cannot (or do not want to) install dirplot itself.

---

## 2. Paramiko SFTP Primer

Paramiko is the de-facto pure-Python SSH implementation. The relevant API surface for directory scanning is small:

```python
import paramiko, stat
from pathlib import PurePosixPath

# 1. Open a connection
client = paramiko.SSHClient()
client.load_system_host_keys()          # trust ~/.ssh/known_hosts
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect(host, username=user, key_filename="/path/to/key")

# 2. Open SFTP subsystem
sftp = client.open_sftp()              # returns SFTPClient

# 3. List a directory — one round-trip gives names + all stat fields
attrs = sftp.listdir_attr("/remote/path")   # list[SFTPAttributes]

for attr in attrs:
    attr.filename   # str — basename only, no directory prefix
    attr.st_size    # int | None — bytes
    attr.st_mode    # int — Unix mode bits (use stat.S_IS* helpers)
    attr.st_mtime   # float | None — seconds since epoch
    attr.longname   # str — ls -l style line (informational only)

    stat.S_ISDIR(attr.st_mode)   # True if directory
    stat.S_ISLNK(attr.st_mode)   # True if symlink

# 4. Stat a single path (rarely needed if listdir_attr is used)
a = sftp.stat("/remote/path/file.txt")   # same SFTPAttributes type

# 5. Clean up
sftp.close()
client.close()
```

Key differences from `pathlib`:

- Paths are plain `str`, not `Path` objects. Use `PurePosixPath` for manipulation.
- There is no `.resolve()` equivalent; paths returned by `listdir_attr` are basenames only and must be joined manually.
- The SFTP server may return `None` for `st_size` or `st_mode` on some implementations; defensive defaulting is required.

---

## 3. Mapping to the Node Dataclass

| Node field | Local source | SFTP source |
|---|---|---|
| `name` | `path.name` | `attr.filename` |
| `size` | `path.stat().st_size` | `attr.st_size` (default `1` if `None`) |
| `extension` | `path.suffix` | `PurePosixPath(attr.filename).suffix` |
| `is_dir` | `path.is_dir()` | `stat.S_ISDIR(attr.st_mode)` |
| `mtime` (future) | `path.stat().st_mtime` | `attr.st_mtime` |

The `path` field on `Node` currently holds a `pathlib.Path`. For remote nodes this would hold a `PurePosixPath` cast to `Path`, which works on POSIX hosts but would be incorrect on Windows. A future refactor could make this field a `str | Path`, but for now the cast is acceptable since rendering only uses `path` for display.

---

## 4. Proposed `build_tree_ssh()` Function

```python
import stat
from pathlib import PurePosixPath, Path

def build_tree_ssh(
    sftp,                          # paramiko.SFTPClient
    remote_path: str,
    exclude: frozenset[str] = frozenset(),
    *,
    _progress: list[int] | None = None,
) -> "Node":
    """Recursively build a Node tree from an SFTP connection."""
    try:
        attrs = sftp.listdir_attr(remote_path)
    except PermissionError:
        # Inaccessible directory — return empty node, same as local behaviour
        return Node(
            name=PurePosixPath(remote_path).name,
            path=Path(remote_path),
            size=1,
            is_dir=True,
            extension="",
            children=[],
        )

    children = []
    for attr in sorted(attrs, key=lambda a: a.filename):
        full = remote_path.rstrip("/") + "/" + attr.filename

        # Skip excludes and hidden files
        if full in exclude or attr.filename.startswith("."):
            continue

        # Skip symlinks to avoid cycles
        if attr.st_mode is not None and stat.S_ISLNK(attr.st_mode):
            continue

        if attr.st_mode is not None and stat.S_ISDIR(attr.st_mode):
            child = build_tree_ssh(sftp, full, exclude, _progress=_progress)
        else:
            ext = PurePosixPath(attr.filename).suffix or "(no ext)"
            child = Node(
                name=attr.filename,
                path=Path(full),
                size=attr.st_size or 1,
                is_dir=False,
                extension=ext,
            )

        if _progress is not None:
            _progress[0] += 1
            if _progress[0] % 100 == 0:
                print(f"\r  scanned {_progress[0]} entries…", end="", file=sys.stderr, flush=True)

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
```

The `_progress` parameter is a one-element list (mutable counter) threaded through recursion to avoid a global variable.

---

## 5. CLI Interface

### URI formats accepted

| Format | Example |
|---|---|
| `ssh://user@host/path` | `ssh://alice@prod.example.com/var/www` |
| `user@host:/path` (SCP-style) | `alice@prod.example.com:/var/www` |

### New options

```
--ssh-key PATH        Path to private key file [default: ~/.ssh/id_rsa]
--ssh-password TEXT   Password (prefer env var SSH_PASSWORD)
--depth INTEGER       Maximum recursion depth for remote trees
```

### Detection logic in `main.py`

```python
def is_ssh_path(path_str: str) -> bool:
    return path_str.startswith("ssh://") or ("@" in path_str and ":" in path_str)

def parse_ssh_path(path_str: str) -> tuple[str, str, str]:
    """Returns (user, host, remote_path)."""
    if path_str.startswith("ssh://"):
        parsed = urllib.parse.urlparse(path_str)
        return parsed.username or getpass.getuser(), parsed.hostname, parsed.path
    # SCP format: user@host:/path
    userhost, remote_path = path_str.split(":", 1)
    user, host = userhost.split("@", 1)
    return user, host, remote_path
```

This detection happens before the `root.exists()` check in `main.py`, so the existing local path validation is not disrupted.

---

## 6. Authentication

Paramiko supports multiple auth mechanisms. The priority order for dirplot should be:

1. **`--ssh-key` flag** — explicit key file passed on the command line.
2. **`SSH_KEY` environment variable** — path to key file, useful in scripts and CI.
3. **ssh-agent** — paramiko picks this up automatically via `paramiko.Agent()`; no extra code needed if `key_filename` is not set.
4. **`--ssh-password` / `SSH_PASSWORD` env var** — password auth as a fallback.
5. **Interactive prompt** — `getpass.getpass()` as a last resort when all other methods fail.

Implementation sketch:

```python
def connect(host: str, user: str, ssh_key: str | None, ssh_password: str | None):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    key_file = ssh_key or os.environ.get("SSH_KEY")
    password = ssh_password or os.environ.get("SSH_PASSWORD")

    try:
        client.connect(
            host,
            username=user,
            key_filename=key_file,      # None → tries ssh-agent automatically
            password=password,
        )
    except paramiko.AuthenticationException:
        # Fall back to interactive prompt
        password = getpass.getpass(f"Password for {user}@{host}: ")
        client.connect(host, username=user, password=password)

    return client
```

Note: `RejectPolicy` is safer than `AutoAddPolicy` for production use, since it refuses connections to hosts not in `known_hosts`. Users can override with a `--trust-host` flag if desired.

### SSH config file (`~/.ssh/config`)

Paramiko can read the user's SSH config via `paramiko.SSHConfig`. This is important because users often alias hosts there with custom ports, usernames, key files, and proxy jumps — none of which would be visible to dirplot without reading it.

```python
import os
from paramiko import SSHConfig

def load_ssh_config(host: str) -> dict:
    config_path = os.path.expanduser("~/.ssh/config")
    cfg = SSHConfig()
    if os.path.exists(config_path):
        with open(config_path) as f:
            cfg.parse(f)
    return cfg.lookup(host)   # resolves wildcard Host blocks, returns merged dict
```

`cfg.lookup(host)` returns a dict that may include:

| Key | SSH config directive | Example value |
|---|---|---|
| `hostname` | `HostName` | `"192.168.1.10"` |
| `user` | `User` | `"alice"` |
| `identityfile` | `IdentityFile` | `["~/.ssh/prod_key"]` |
| `port` | `Port` | `"2222"` |
| `proxyjump` | `ProxyJump` | `"bastion.example.com"` |

These values should be used as defaults, with CLI flags taking precedence:

```python
def connect(host: str, user: str | None, ssh_key: str | None, ssh_password: str | None, port: int | None):
    ssh_cfg = load_ssh_config(host)

    resolved_host = ssh_cfg.get("hostname", host)
    resolved_user = user or ssh_cfg.get("user") or os.environ.get("USER", "root")
    resolved_port = port or int(ssh_cfg.get("port", 22))
    key_file = ssh_key or os.environ.get("SSH_KEY") or (
        os.path.expanduser(ssh_cfg["identityfile"][0])
        if ssh_cfg.get("identityfile") else None
    )
    password = ssh_password or os.environ.get("SSH_PASSWORD")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        client.connect(resolved_host, port=resolved_port, username=resolved_user,
                       key_filename=key_file, password=password)
    except paramiko.AuthenticationException:
        password = getpass.getpass(f"Password for {resolved_user}@{resolved_host}: ")
        client.connect(resolved_host, port=resolved_port, username=resolved_user,
                       password=password)

    return client
```

`ProxyJump` is not handled automatically by paramiko (unlike OpenSSH). If `proxyjump` is present in the config, dirplot should either warn the user that proxy jumps are unsupported, or implement it manually by opening a `Transport` through a forwarded socket — a significant complication best deferred to a later iteration.

---

## 7. Performance Considerations

- **`listdir_attr()` vs `listdir()` + `stat()`**: `listdir_attr()` fetches names and all stat fields in a single round-trip per directory, making it significantly faster than calling `stat()` on each entry individually. Always use `listdir_attr()`.

- **Large trees are slow**: An SSH round-trip per directory is expensive compared to a local syscall. A tree with 10 000 directories will require ~10 000 round-trips. For reference, a typical NFS scan that takes <1 s locally might take 10–60 s over SSH.

- **Progress reporting**: Print a running count to stderr (every 100 entries) so the user knows the scan is alive. Clear with `\r` for a clean display.

- **`--depth` limit**: Provide a `--depth N` option to cap recursion at N levels below the root. This allows quick top-level overviews without scanning deeply nested structures.

- **Connection reuse**: Open exactly one `SSHClient` and one `SFTPClient` per invocation and pass the `SFTPClient` through the recursion. Do not open a new connection per directory.

- **Async future**: For very large trees, a concurrent approach using `asyncio` + `asyncssh` (a different library) could fire multiple `listdir_attr` calls in parallel. This is outside the scope of paramiko, which is synchronous, but worth noting as a future direction.

---

## 8. Error Handling

| Condition | Behaviour |
|---|---|
| `PermissionError` on `listdir_attr` | Return empty `Node` with `size=1`; continue scan (same as local `scanner.py`) |
| `FileNotFoundError` | Warn to stderr, skip entry |
| `IOError` / `EOFError` | Connection drop — re-raise with message: `"SSH connection to {host} lost. Check network stability."` |
| `attr.st_size is None` | Default to `1` (consistent with local `OSError` path in scanner) |
| `attr.st_mode is None` | Treat entry as a regular file (conservative fallback) |
| Unknown host in `known_hosts` | `paramiko.SSHException` — surface with actionable hint: `"Run: ssh-keyscan {host} >> ~/.ssh/known_hosts"` |

---

## 9. Optional Dependency

Paramiko should be an optional dependency to avoid bloating the default install for users who never use SSH.

In `pyproject.toml`:

```toml
[project.optional-dependencies]
ssh = ["paramiko>=3.0"]
```

Users who need SSH support install with:

```bash
pip install dirplot[ssh]
```

Inside `build_tree_ssh()`, import paramiko lazily:

```python
def build_tree_ssh(sftp, remote_path: str, ...) -> Node:
    try:
        import paramiko  # noqa: F401 — only needed for type hints elsewhere
        import stat
    except ImportError:
        raise ImportError(
            "SSH support requires paramiko. Install it with:\n"
            "  pip install dirplot[ssh]"
        ) from None
    ...
```

The `SFTPClient` type hint can be quoted (`"paramiko.SFTPClient"`) or use `TYPE_CHECKING` to avoid a hard import at module level.

---

## 10. Testing Approach

No real SSH connection is needed in the test suite. Mock `paramiko.SFTPClient` using `unittest.mock`.

### Fake SFTPAttributes

```python
from unittest.mock import MagicMock
import stat as stat_module

def make_attr(filename: str, size: int, is_dir: bool = False) -> MagicMock:
    attr = MagicMock()
    attr.filename = filename
    attr.st_size = size
    attr.st_mtime = 1_700_000_000.0
    attr.st_mode = (
        stat_module.S_IFDIR | 0o755 if is_dir else stat_module.S_IFREG | 0o644
    )
    return attr
```

### Example test

```python
def test_build_tree_ssh_flat_directory():
    sftp = MagicMock()
    sftp.listdir_attr.return_value = [
        make_attr("file.py",  1000),
        make_attr("README.md", 500),
        make_attr("subdir",      0, is_dir=True),
    ]
    # Recursion into subdir returns empty listing
    sftp.listdir_attr.side_effect = lambda path: (
        [] if path.endswith("subdir") else sftp.listdir_attr.return_value
    )

    node = build_tree_ssh(sftp, "/home/user/project")
    assert node.is_dir
    assert node.name == "project"
    assert any(c.name == "file.py" for c in node.children)
    assert any(c.extension == ".py" for c in node.children)
```

### What to test

- Flat directory with mixed file types.
- Nested directories (recursion).
- Symlinks are skipped.
- Hidden files (`.dotfiles`) are skipped.
- `PermissionError` returns an empty node without crashing.
- `st_size=None` defaults to `1`.
- File extensions are extracted via `PurePosixPath`.
