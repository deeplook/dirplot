"""Unified tree-scanning helper shared by the map and metrics commands.

This module now uses the unified TreeSource protocol for all scanning operations.
Legacy imports are maintained for backwards compatibility during transition.
"""

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import typer

# Import all sources to ensure they self-register
from dirplot import sources  # noqa: F401
from dirplot.archives import PasswordRequired, build_tree_archive, is_archive_path
from dirplot.docker import build_tree_docker, is_docker_path, parse_docker_path
from dirplot.gdrive import build_tree_gdrive, is_gdrive_path, parse_gdrive_path
from dirplot.git_scanner import build_tree_git_ref, is_git_ref_path
from dirplot.github import build_tree_github, is_github_path, parse_github_path
from dirplot.k8s import build_tree_pod, is_pod_path, parse_pod_path
from dirplot.pathlist import parse_pathlist
from dirplot.s3 import build_tree_s3, is_s3_path, make_s3_client, parse_s3_path
from dirplot.scanner import NO_EXT, Node, build_tree, build_tree_multi
from dirplot.sources import registry as source_registry
from dirplot.ssh import build_tree_ssh, connect, is_ssh_path, parse_ssh_path


def _tilde(p: str) -> str:
    home = str(Path.home())
    return "~" + p[len(home) :] if p.startswith(home) else p


def scan_with_unified_sources(
    root: str,
    *,
    exclude: frozenset[str] = frozenset(),
    depth: int | None = None,
) -> Node | None:
    """Try to scan using the unified TreeSource registry.

    This is the new preferred way to scan paths. It automatically detects
    the source type and uses the appropriate scanner.

    Args:
        root: Path/URL to scan.
        exclude: Glob patterns to skip.
        depth: Maximum recursion depth.

    Returns:
        Root node if a source can handle the path, None otherwise.
    """
    try:
        # Check if any source can handle this path
        source = source_registry.find_source(root)
        return source.scan(root, exclude=exclude, depth=depth)
    except ValueError:
        # No source found
        return None


def scan_tree(
    roots: list[str],
    paths_from: Path | None,
    exclude: list[str],
    depth: int | None,
    ssh_key: str | None,
    ssh_password: str | None,
    aws_profile: str | None,
    no_sign: bool,
    github_token: str | None,
    k8s_namespace: str | None,
    k8s_container: str | None,
    password: str | None,
    no_input: bool = False,
    log: Callable[[str], None] | None = None,
) -> tuple[Node, float, str | None]:
    """Scan a root path and return (root_node, t_scan_seconds, display_title).

    *log* is called with each "Scanning ..." message when provided.
    """

    def _emit(msg: str) -> None:
        if log is not None:
            log(msg)

    use_stdin = paths_from is not None or (not roots and not sys.stdin.isatty())
    if use_stdin and roots:
        typer.echo(
            "Error: cannot combine positional paths with --paths-from / piped stdin.",
            err=True,
        )
        raise typer.Exit(1)

    root = roots[0] if len(roots) == 1 else ""
    display_title: str | None = None
    t_scan_start = time.monotonic()

    if use_stdin:
        if paths_from is None or str(paths_from) == "-":
            raw = sys.stdin.read()
        else:
            if not paths_from.exists():
                typer.echo(f"Error: --paths-from path does not exist: {paths_from}", err=True)
                raise typer.Exit(1)
            raw = paths_from.read_text()
        parsed = parse_pathlist(raw.splitlines())
        if not parsed:
            typer.echo("Error: no paths found in path-list input.", err=True)
            raise typer.Exit(1)
        for p in parsed:
            if not p.exists():
                typer.echo(f"Path does not exist: {p}", err=True)
                raise typer.Exit(1)
        excluded = frozenset(exclude)
        root_paths = [p.resolve() for p in parsed]
        common_str = os.path.commonpath([str(p) for p in root_paths])
        _emit(f"Scanning {len(root_paths)} paths under {_tilde(common_str)} ...")
        root_node = build_tree_multi(root_paths, excluded, depth)
    elif not roots:
        typer.echo("Error: at least one path is required.", err=True)
        raise typer.Exit(1)
    elif len(roots) > 1:
        for r in roots:
            if any(
                f(r)
                for f in (
                    is_docker_path,
                    is_pod_path,
                    is_github_path,
                    is_gdrive_path,
                    is_s3_path,
                    is_ssh_path,
                    is_git_ref_path,
                )
            ):
                typer.echo(
                    f"Multiple roots are only supported for local paths and archives, got: {r}",
                    err=True,
                )
                raise typer.Exit(1)
        excluded = frozenset(exclude)
        archive_roots = [r for r in roots if is_archive_path(r)]
        local_roots = [r for r in roots if not is_archive_path(r)]
        if archive_roots and not local_roots:
            sub_nodes: list[Node] = []
            for r in archive_roots:
                ap = Path(r)
                if not ap.exists():
                    typer.echo(f"Path does not exist: {r}", err=True)
                    raise typer.Exit(1)
                _emit(f"Reading archive {r} ...")
                try:
                    sub_nodes.append(
                        build_tree_archive(ap, exclude=excluded, depth=depth, password=password)
                    )
                except PasswordRequired as exc:
                    if password is not None:
                        typer.echo("Error: incorrect password.", err=True)
                        raise typer.Exit(1) from exc
                    if no_input:
                        typer.echo(
                            "Error: archive requires a password."
                            " Pass --password or --password-file.",
                            err=True,
                        )
                        raise typer.Exit(1) from exc
                    pw = typer.prompt("Password", hide_input=True)
                    try:
                        sub_nodes.append(
                            build_tree_archive(ap, exclude=excluded, depth=depth, password=pw)
                        )
                    except PasswordRequired as exc2:
                        typer.echo("Error: incorrect password.", err=True)
                        raise typer.Exit(1) from exc2
                except (ImportError, OSError, RuntimeError) as exc:
                    typer.echo(f"Error: {exc}", err=True)
                    raise typer.Exit(1) from exc
            common_str = os.path.commonpath([str(Path(r).resolve()) for r in archive_roots])
            root_node = Node(
                name=Path(common_str).name or common_str,
                path=Path(common_str),
                size=sum(n.size for n in sub_nodes),
                is_dir=True,
                children=sub_nodes,
            )
        else:
            root_paths = []
            for r in local_roots:
                rp = Path(r)
                if not rp.exists():
                    typer.echo(f"Path does not exist: {r}", err=True)
                    raise typer.Exit(1)
                if not rp.is_dir() and not rp.is_file():
                    typer.echo(f"Not a file or directory: {r}", err=True)
                    raise typer.Exit(1)
                root_paths.append(rp.resolve())
            common_str = os.path.commonpath([str(p) for p in root_paths])
            _emit(f"Scanning {len(roots)} paths under {_tilde(common_str)} ...")
            root_node = build_tree_multi(root_paths, excluded, depth)
    elif is_gdrive_path(root):
        gdrive_folder_id = parse_gdrive_path(root)
        label = f"gdrive://{gdrive_folder_id}" if gdrive_folder_id else "gdrive://"
        _emit(f"Scanning {label} ...")
        progress = [0]
        try:
            root_node = build_tree_gdrive(
                gdrive_folder_id,
                exclude=frozenset(exclude),
                depth=depth,
                _progress=progress,
            )
        except (FileNotFoundError, OSError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_docker_path(root):
        docker_container, docker_path = parse_docker_path(root)
        _emit(f"Scanning docker://{docker_container}:{docker_path} ...")
        progress = [0]
        try:
            root_node = build_tree_docker(
                docker_container,
                docker_path,
                exclude=frozenset(exclude),
                depth=depth,
                _progress=progress,
            )
        except (FileNotFoundError, OSError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_pod_path(root):
        pod_name, pod_ns, pod_path = parse_pod_path(root)
        namespace = k8s_namespace or pod_ns
        ns_label = f"@{namespace}" if namespace else ""
        _emit(f"Scanning pod://{pod_name}{ns_label}:{pod_path} ...")
        progress = [0]
        try:
            root_node = build_tree_pod(
                pod_name,
                pod_path,
                namespace=namespace,
                container=k8s_container,
                exclude=frozenset(exclude),
                depth=depth,
                _progress=progress,
            )
        except (FileNotFoundError, OSError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_github_path(root):
        gh_owner, gh_repo, gh_ref, gh_subpath = parse_github_path(root)
        display_title = f"{gh_owner}-{gh_repo}"
        try:
            root_node, resolved_ref = build_tree_github(
                gh_owner,
                gh_repo,
                gh_ref,
                token=github_token,
                exclude=frozenset(exclude),
                depth=depth,
                subpath=gh_subpath,
            )
        except (PermissionError, FileNotFoundError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        subpath_label = f"/{gh_subpath}" if gh_subpath else ""
        _emit(f"Scanning github:{gh_owner}/{gh_repo}@{resolved_ref}{subpath_label} ...")
    elif is_s3_path(root):
        bucket, prefix = parse_s3_path(root)
        _emit(f"Scanning {root} ...")
        try:
            s3 = make_s3_client(profile=aws_profile, no_sign=no_sign)
        except ImportError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        progress = [0]
        root_node = build_tree_s3(
            s3,
            bucket,
            prefix,
            exclude=frozenset(exclude),
            depth=depth,
            _progress=progress,
        )
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_ssh_path(root):
        ssh_user, ssh_host, remote_path = parse_ssh_path(root)
        _emit(f"Scanning {root} ...")
        try:
            client = connect(ssh_host, ssh_user, ssh_key=ssh_key, ssh_password=ssh_password)
        except ImportError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        sftp = client.open_sftp()
        progress = [0]
        try:
            root_node = build_tree_ssh(
                sftp,
                remote_path,
                exclude=frozenset(exclude),
                depth=depth,
                _progress=progress,
            )
        finally:
            sftp.close()
            client.close()
        if progress[0] >= 100:
            print("", file=sys.stderr)
    elif is_git_ref_path(root):
        _emit(f"Scanning git repo {root} ...")
        try:
            root_node, git_ref_title = build_tree_git_ref(
                root, exclude=frozenset(exclude), depth=depth
            )
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        display_title = git_ref_title
    elif is_archive_path(root):
        archive_path = Path(root)
        if not archive_path.exists():
            typer.echo(f"Path does not exist: {root}", err=True)
            raise typer.Exit(1)
        if not archive_path.is_file():
            typer.echo(f"Not a file: {root}", err=True)
            raise typer.Exit(1)
        _emit(f"Reading archive {root} ...")
        try:
            root_node = build_tree_archive(
                archive_path, exclude=frozenset(exclude), depth=depth, password=password
            )
        except PasswordRequired as exc:
            if password is not None:
                typer.echo("Error: incorrect password.", err=True)
                raise typer.Exit(1) from exc
            if no_input:
                typer.echo(
                    "Error: archive requires a password. Pass --password or --password-file.",
                    err=True,
                )
                raise typer.Exit(1) from exc
            pw = typer.prompt("Password", hide_input=True)
            try:
                root_node = build_tree_archive(
                    archive_path, exclude=frozenset(exclude), depth=depth, password=pw
                )
            except PasswordRequired as exc2:
                typer.echo("Error: incorrect password.", err=True)
                raise typer.Exit(1) from exc2
        except (ImportError, OSError, RuntimeError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    else:
        # Try unified sources first (new architecture)
        try:
            unified_result = scan_with_unified_sources(
                root, exclude=frozenset(exclude), depth=depth
            )
        except FileNotFoundError as exc:
            typer.echo(f"Path does not exist: {root}", err=True)
            raise typer.Exit(1) from exc
        except NotADirectoryError as exc:
            # Handle single file case - construct tree directly
            root_path = Path(root)
            if root_path.is_file():
                rp = root_path.resolve()
                try:
                    file_size = max(1, rp.stat().st_size)
                except OSError:
                    file_size = 1
                ext = rp.suffix.lower() if rp.suffix else NO_EXT
                file_node = Node(name=rp.name, path=rp, size=file_size, is_dir=False, extension=ext)
                root_node = Node(
                    name=rp.parent.name,
                    path=rp.parent,
                    size=file_size,
                    is_dir=True,
                    children=[file_node],
                )
                _emit(f"Scanning {_tilde(root)} ...")
                # Skip the rest of the else block - we already have root_node
                t_scan = time.monotonic() - t_scan_start
                return root_node, t_scan, display_title
            else:
                typer.echo(f"Not a file or directory: {root}", err=True)
                raise typer.Exit(1) from exc

        if unified_result is not None:
            source = source_registry.find_source(root)
            _emit(f"Scanning {source.get_display_name(root)} ...")
            root_node = unified_result
        else:
            # Fall back to legacy filesystem handling
            root_path = Path(root)
            if not root_path.exists():
                typer.echo(f"Path does not exist: {root}", err=True)
                raise typer.Exit(1)
            if not root_path.is_dir():
                if not root_path.is_file():
                    typer.echo(f"Not a file or directory: {root}", err=True)
                    raise typer.Exit(1)
                rp = root_path.resolve()
                try:
                    file_size = max(1, rp.stat().st_size)
                except OSError:
                    file_size = 1
                ext = rp.suffix.lower() if rp.suffix else NO_EXT
                file_node = Node(name=rp.name, path=rp, size=file_size, is_dir=False, extension=ext)
                root_node = Node(
                    name=rp.parent.name,
                    path=rp.parent,
                    size=file_size,
                    is_dir=True,
                    children=[file_node],
                )
                _emit(f"Scanning {_tilde(root)} ...")
            else:
                excluded = frozenset(exclude)
                _emit(f"Scanning {_tilde(root)} ...")
                root_node = build_tree(root_path.resolve(), excluded, depth)

    t_scan = time.monotonic() - t_scan_start
    return root_node, t_scan, display_title
