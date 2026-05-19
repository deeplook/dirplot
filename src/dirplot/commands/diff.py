"""The ``diff`` command: treemap of two directory trees with diff highlights."""

from __future__ import annotations

import os
import subprocess
import time
import webbrowser
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.defaults import DEFAULT_COLORMAP, DEFAULT_FONT_SIZE
from dirplot.display import display_inline, display_window
from dirplot.helpers.highlights import resolve_highlight_specs
from dirplot.scanner import Node, prune_to_subtrees
from dirplot.terminal import default_canvas_size, get_terminal_size

# Border colours for diff status — applied to file tile borders only.
# Fill colours remain the standard Linguist/colormap palette.
DIFF_COLORS: dict[str, str] = {
    "removed": "deleted",  # red   — in A but not in B
    "added": "created",  # green — in B but not in A
    "changed": "modified",  # blue  — in both, but size differs
}

_DIFF_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot diff src/ build/  [dim]# compare two local directories[/dim]\n\n"
    "  dirplot diff v1/ v2/ --output diff.png  [dim]# save to file[/dim]\n\n"
    "  dirplot diff v1/ v2/ --no-show --output diff.svg  [dim]# SVG output[/dim]\n\n"
    "  dirplot diff v1/ v2/ --canvas 1920x1080  [dim]# fixed resolution[/dim]\n\n"
    "  dirplot diff v1/ v2/ --depth 3  [dim]# limit directory depth[/dim]\n\n"
    "  dirplot diff github://owner/repo@v1 github://owner/repo@v2"
    "  [dim]# compare two GitHub tags[/dim]\n\n"
    "  dirplot diff archive_v1.tar.gz archive_v2.zip  [dim]# compare two archives[/dim]\n\n"
    "\n[bold]Highlight colours (borders only)[/bold]\n\n"
    "  [green]green[/green]  — added (in B, not in A)\n"
    "  [red]red[/red]    — removed (in A, not in B)\n"
    "  [blue]blue[/blue]   — changed (in both, but size differs in B)\n"
)


@app.command(name="diff", epilog=_DIFF_EPILOG)
def diff_cmd(
    tree_a: str = typer.Argument(
        ...,
        metavar="A",
        help="Source tree (baseline), or a local git/hg repo for uncommitted changes",
    ),
    tree_b: str | None = typer.Argument(
        None, metavar="B", help="Target tree (comparison). Omit to diff A against its working tree."
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Save image to file"),
    fmt: str | None = typer.Option(
        None,
        "--format",
        help="Output format: png or svg (inferred from --output extension if omitted)",
        metavar="FORMAT",
    ),
    show: bool = typer.Option(True, "--show/--no-show", help="Display the image after rendering"),
    inline: bool = typer.Option(
        False,
        "--inline",
        help="Show in terminal (auto-detects iTerm2/Kitty protocol) instead of a separate window",
    ),
    font_size: int = typer.Option(
        DEFAULT_FONT_SIZE, "--font-size", help="Directory label font size in pixels"
    ),
    colormap: str = typer.Option(
        DEFAULT_COLORMAP,
        "--colormap",
        help="Colormap for file-extension fill colours (default: tab20 uses Linguist palette)",
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    include: list[str] = typer.Option(
        [],
        "--include",
        help="Show only this subtree (repeatable; supports nested paths). Allowlist complement to --exclude.",  # noqa: E501
    ),
    depth: int | None = typer.Option(None, "--depth", help="Maximum directory depth"),
    canvas: str | None = typer.Option(
        None, "--canvas", help="Output dimensions as WIDTHxHEIGHT", metavar="WIDTHxHEIGHT"
    ),
    cushion: bool = typer.Option(True, "--cushion/--no-cushion", help="Van Wijk cushion shading"),
    dark: bool = typer.Option(True, "--dark/--light", help="Dark background (default) or light"),
    log_scale: float = typer.Option(
        0.0,
        "--log-scale",
        help="Log-scale compression ratio (> 1 to enable)",
        show_default=True,
    ),
    context: bool = typer.Option(
        True,
        "--context/--no-context",
        help="Include unchanged files for context. --no-context shows only diff files.",
    ),
    header: bool = typer.Option(True, "--header/--no-header", help="Print info lines to stderr"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output"),
    ssh_key: str | None = typer.Option(
        None, "--ssh-key", help="SSH private key file (default: ~/.ssh/id_rsa)"
    ),
    aws_profile: str | None = typer.Option(
        None, "--aws-profile", envvar="AWS_PROFILE", help="AWS profile name for S3 access"
    ),
    no_sign: bool = typer.Option(
        False, "--no-sign", help="Skip AWS signing for anonymous access to public S3 buckets"
    ),
    k8s_namespace: str | None = typer.Option(
        None, "--k8s-namespace", help="Kubernetes namespace (overrides @namespace in pod URL)"
    ),
    k8s_container: str | None = typer.Option(
        None, "--k8s-container", help="Container name for multi-container pods"
    ),
    password_file: Path | None = typer.Option(
        None,
        "--password-file",
        help="File containing the archive password (avoids exposing it in shell history).",
        metavar="FILE",
    ),
    ssh_password_file: Path | None = typer.Option(
        None,
        "--ssh-password-file",
        help="File containing the SSH password (avoids exposing it in shell history).",
        metavar="FILE",
    ),
    github_token_file: Path | None = typer.Option(
        None,
        "--github-token-file",
        help="File containing a GitHub personal access token (avoids exposing it in shell history).",  # noqa: E501
        metavar="FILE",
    ),
    no_input: bool = typer.Option(
        False,
        "--no-input",
        help="Disable all interactive prompts; fail instead of prompting for passwords.",
    ),
    highlight: list[str] = typer.Option(
        [],
        "--highlight",
        "-H",
        help=(
            "Highlight matching paths with a coloured border (repeatable). "
            "Accepts exact paths or glob patterns including ** (e.g. src/**/*.py). "
            "Append @color to set the border colour (e.g. '**/*.py@orange'); "
            "defaults to red."
        ),
    ),
) -> None:
    """Compare two directory trees A and B as a treemap with diff highlights.

    Example: dirplot diff old/ new/ --inline

    A and B can be local directories, GitHub repos (github://owner/repo[@ref]),
    archives (.zip/.tar.gz), S3 paths (s3://bucket/prefix), SSH paths, Docker
    containers, or Kubernetes pods — any source supported by the map command.

    Files are sized by their size in B (the target tree). Borders indicate
    diff status: [green]green[/green] = added, [red]red[/red] = removed,
    [blue]blue[/blue] = changed (size differs).
    Unchanged files show no border. Use --no-context to hide them entirely.
    """
    import sys

    import cmap as _cmap_lib

    from dirplot.git_scanner import (
        build_node_tree,
        build_tree_git_worktree,
        git_file_hashes,
        git_worktree_hashes,
        is_git_ref_path,
        parse_git_ref_path,
    )
    from dirplot.helpers.scan import scan_tree
    from dirplot.hg_scanner import (
        build_tree_hg_worktree,
        hg_worktree_hashes,
        is_hg_repo,
    )
    from dirplot.render_png import create_treemap
    from dirplot.scanner import apply_log_sizes
    from dirplot.svg_render import create_treemap_svg

    def _info(msg: str) -> None:
        if not quiet and header:
            typer.echo(msg, err=True)

    # Single-argument shorthand: `dirplot diff .` → `dirplot diff .@HEAD .`
    resolved_b: str
    if tree_b is None:
        p = Path(tree_a)
        is_git = (
            p.is_dir()
            and subprocess.run(
                ["git", "-C", str(p), "rev-parse", "--git-dir"], capture_output=True
            ).returncode
            == 0
        )
        is_hg = p.is_dir() and (p / ".hg").is_dir()
        if is_git:
            resolved_b = tree_a
            tree_a = f"{tree_a}@HEAD"
        elif is_hg:
            resolved_b = tree_a
            tree_a = f"{tree_a}@tip"
        else:
            typer.echo("Error: B is required when A is not a local git or hg repository.", err=True)
            raise typer.Exit(1)
    else:
        resolved_b = tree_b

    # Validate colormap
    _valid_cmaps = set(_cmap_lib.Catalog().short_keys())
    if colormap not in _valid_cmaps:
        valid = ", ".join(sorted(_valid_cmaps))
        typer.echo(f"Unknown colormap '{colormap}'. Valid options:\n{valid}", err=True)
        raise typer.Exit(1)

    # Resolve credentials/tokens from files
    github_token: str | None = os.environ.get("GITHUB_TOKEN")
    ssh_password: str | None = None
    password: str | None = None

    if password_file is not None:
        if not password_file.exists():
            typer.echo(f"Error: --password-file not found: {password_file}", err=True)
            raise typer.Exit(1)
        password = password_file.read_text().strip()

    if ssh_password_file is not None:
        if not ssh_password_file.exists():
            typer.echo(f"Error: --ssh-password-file not found: {ssh_password_file}", err=True)
            raise typer.Exit(1)
        ssh_password = ssh_password_file.read_text().strip()

    if github_token_file is not None:
        if not github_token_file.exists():
            typer.echo(f"Error: --github-token-file not found: {github_token_file}", err=True)
            raise typer.Exit(1)
        github_token = github_token_file.read_text().strip()

    def _is_local_git_repo(s: str) -> bool:
        import subprocess as _sp

        p = Path(s)
        if not p.is_dir():
            return False
        return (
            _sp.run(
                ["git", "-C", str(p), "rev-parse", "--git-dir"],
                capture_output=True,
            ).returncode
            == 0
        )

    def _scan(label: str, src: str) -> tuple[object, str | None]:
        p = Path(src)
        if not is_git_ref_path(src) and _is_local_git_repo(src):
            _info(f"Scanning {label}: {src} (tracked files only) ...")
            excluded_set = frozenset(exclude)
            node = build_tree_git_worktree(p.resolve(), excluded_set, depth)
            return node, None
        if not is_git_ref_path(src) and p.is_dir() and is_hg_repo(p.resolve()):
            _info(f"Scanning {label}: {src} (tracked files only) ...")
            excluded_set = frozenset(exclude)
            node = build_tree_hg_worktree(p.resolve(), excluded_set, depth)
            return node, None
        return scan_tree(
            roots=[src],
            paths_from=None,
            exclude=exclude,
            depth=depth,
            ssh_key=ssh_key,
            ssh_password=ssh_password,
            aws_profile=aws_profile,
            no_sign=no_sign,
            github_token=github_token,
            k8s_namespace=k8s_namespace,
            k8s_container=k8s_container,
            password=password,
            no_input=no_input,
            log=_info,
        )[::2]  # (node, title) — drop t_scan

    # Scan both trees
    t0 = time.monotonic()
    _info(f"Scanning A: {tree_a} ...")
    node_a, title_a = _scan("A", tree_a)
    _info(f"Scanning B: {resolved_b} ...")
    node_b, title_b = _scan("B", resolved_b)
    t_scan = time.monotonic() - t0
    _info(f"Scanned in {t_scan:.1f}s")

    # Build flat file maps {rel_path: size}
    def _flatten(node: object, prefix: str = "") -> dict[str, int]:
        from dirplot.scanner import Node as ScanNode

        n: ScanNode = node  # type: ignore[assignment]
        result: dict[str, int] = {}
        if not n.is_dir:
            result[prefix] = n.size
        else:
            for child in n.children:
                child_prefix = f"{prefix}/{child.name}" if prefix else child.name
                result.update(_flatten(child, child_prefix))
        return result

    files_a = _flatten(node_a)
    files_b = _flatten(node_b)

    # Use a stable virtual root path for highlight key generation.
    # build_node_tree keys highlights as (virtual_root / rel).as_posix().
    virtual_root_b = Path(resolved_b)

    # For git ref sources, compare blob hashes for accurate change detection.
    # Size comparison alone misses edits that don't change the file size.
    hashes_a: dict[str, str] = {}
    hashes_b: dict[str, str] = {}
    if is_git_ref_path(tree_a):
        repo_a, ref_a = parse_git_ref_path(tree_a)
        hashes_a = git_file_hashes(repo_a.resolve(), ref_a)
    elif _is_local_git_repo(tree_a):
        hashes_a = git_worktree_hashes(Path(tree_a).resolve())
    elif is_hg_repo(Path(tree_a).resolve()):
        hashes_a = hg_worktree_hashes(Path(tree_a).resolve())
    if is_git_ref_path(resolved_b):
        repo_b, ref_b = parse_git_ref_path(resolved_b)
        hashes_b = git_file_hashes(repo_b.resolve(), ref_b)
    elif _is_local_git_repo(resolved_b):
        hashes_b = git_worktree_hashes(Path(resolved_b).resolve())
    elif is_hg_repo(Path(resolved_b).resolve()):
        hashes_b = hg_worktree_hashes(Path(resolved_b).resolve())

    # Compute diff highlights keyed to match rect_map keys produced by build_node_tree.
    diff_status: dict[str, str] = {}
    highlights: dict[str, str] = {}
    all_keys = set(files_a) | set(files_b)
    for rel in all_keys:
        key = (virtual_root_b / rel).as_posix()
        if rel in files_a and rel not in files_b:
            diff_status[rel] = DIFF_COLORS["removed"]
            highlights[key] = DIFF_COLORS["removed"]
        elif rel not in files_a and rel in files_b:
            diff_status[rel] = DIFF_COLORS["added"]
            highlights[key] = DIFF_COLORS["added"]
        elif rel in files_a and rel in files_b:
            if hashes_a and hashes_b:
                if hashes_a.get(rel) != hashes_b.get(rel):
                    diff_status[rel] = DIFF_COLORS["changed"]
                    highlights[key] = DIFF_COLORS["changed"]
            elif files_a[rel] != files_b[rel]:
                diff_status[rel] = DIFF_COLORS["changed"]
                highlights[key] = DIFF_COLORS["changed"]

    def _included(rel: str) -> bool:
        if not include:
            return True
        return any(rel == path or rel.startswith(f"{path}/") for path in include)

    counted_statuses = [status for rel, status in diff_status.items() if _included(rel)]
    n_removed = sum(1 for v in counted_statuses if v == DIFF_COLORS["removed"])
    n_added = sum(1 for v in counted_statuses if v == DIFF_COLORS["added"])
    n_changed = sum(1 for v in counted_statuses if v == DIFF_COLORS["changed"])
    _info(f"Diff: {n_added} added, {n_removed} removed, {n_changed} changed")

    # Build combined node tree sized by B.
    # With --context: include all files (unchanged for context + diff files).
    # With --no-context: include only files that changed, were added, or were removed.
    # Use hash comparison when available so LFS files (pointer size != disk size)
    # are not falsely counted as changed.
    def _is_changed(rel: str) -> bool:
        if rel not in files_b:
            return True  # removed
        if rel not in files_a:
            return True  # added
        if hashes_a and hashes_b:
            return hashes_a.get(rel) != hashes_b.get(rel)
        return files_a[rel] != files_b[rel]

    changed_keys = {rel for rel in set(files_a) | set(files_b) if _is_changed(rel)}
    if context:
        combined_files = dict(files_b)
        for rel in files_a:
            if rel not in combined_files:
                combined_files[rel] = files_a[rel]
    else:
        combined_files = {
            rel: (files_b[rel] if rel in files_b else files_a[rel]) for rel in changed_keys
        }

    root_node = build_node_tree(virtual_root_b, combined_files, depth)

    if include:
        root_node = prune_to_subtrees(root_node, set(include))

    if highlight:

        def _collect_paths(node: Node) -> list[str]:
            paths = []
            if hasattr(node, "path"):
                paths.append(node.path.as_posix())
            for child in node.children:
                paths.extend(_collect_paths(child))
            return paths

        highlights.update(resolve_highlight_specs(highlight, _collect_paths(root_node)))

    if log_scale > 1:
        apply_log_sizes(root_node, log_scale)

    # Resolve output size
    to_stdout = output is not None and str(output) == "-"
    if to_stdout:
        show = False
    inline_cols: int | None = None
    if canvas is not None:
        try:
            w_str, h_str = canvas.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(f"Invalid --canvas '{canvas}'. Expected WIDTHxHEIGHT.", err=True)
            raise typer.Exit(1) from None
        if width_px == 0 or height_px == 0:
            typer.echo(
                f"Invalid --canvas '{canvas}': width and height must both be positive.", err=True
            )
            raise typer.Exit(1)
        _info(f"Output size: {width_px}x{height_px}px")
    else:
        width_px, height_px = default_canvas_size()
        if inline:
            inline_cols, *_ = get_terminal_size()
        _info(f"Terminal size: {width_px}x{height_px}px")

    # Resolve format
    if fmt is not None:
        if fmt not in ("png", "svg"):
            typer.echo(f"Unknown format '{fmt}'. Valid options: png, svg", err=True)
            raise typer.Exit(1)
        use_svg = fmt == "svg"
    elif output is not None and output.suffix.lower() == ".svg":
        use_svg = True
    else:
        use_svg = False

    label_a = title_a or Path(tree_a).name
    label_b = title_b or Path(resolved_b).name
    title_suffix = f"{label_a} → {label_b}"

    t_render_start = time.monotonic()
    if use_svg:
        buf = create_treemap_svg(
            root_node,
            width_px,
            height_px,
            font_size,
            colormap,
            None,
            cushion,
            depth,
            dark,
            highlights=highlights or None,
        )
    else:
        buf = create_treemap(
            root_node,
            width_px,
            height_px,
            font_size,
            colormap,
            None,
            cushion,
            depth,
            highlights=highlights,
            title_suffix=title_suffix,
            dark=dark,
            logscale=log_scale,
        )
    t_render = time.monotonic() - t_render_start

    if output is not None:
        if to_stdout:
            sys.stdout.buffer.write(buf.read())
            buf.seek(0)
        else:
            output.write_bytes(buf.read())
            _info(f"Saved diff to {output}  [{t_render:.1f}s]")
            buf.seek(0)

    if show and not to_stdout:
        if use_svg:
            if output is not None:
                webbrowser.open(output.resolve().as_uri())
            else:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
                    tmp.write(buf.read())
                    webbrowser.open(Path(tmp.name).resolve().as_uri())
        elif inline:
            display_inline(buf, cols=inline_cols)
        else:
            display_window(buf, title=f"dirplot diff: {title_suffix}")
