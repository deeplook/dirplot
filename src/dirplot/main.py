"""CLI entry point."""

import sys
import time
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib.pyplot as plt
import typer

from dirplot import __version__
from dirplot.archives import PasswordRequired, build_tree_archive, is_archive_path
from dirplot.display import display_inline, display_window
from dirplot.docker import build_tree_docker, is_docker_path, parse_docker_path
from dirplot.github import build_tree_github, is_github_path, parse_github_path
from dirplot.k8s import build_tree_pod, is_pod_path, parse_pod_path
from dirplot.render import create_treemap
from dirplot.s3 import build_tree_s3, is_s3_path, make_s3_client, parse_s3_path
from dirplot.scanner import (
    Node,
    apply_log_sizes,
    build_tree,
    build_tree_multi,
    collect_extensions,
    prune_to_subtrees,
)
from dirplot.ssh import build_tree_ssh, connect, is_ssh_path, parse_ssh_path
from dirplot.svg_render import create_treemap_svg
from dirplot.terminal import get_terminal_pixel_size, get_terminal_size

app = typer.Typer(
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _app_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot map .  [dim]# open in system viewer[/dim]\n\n"
    "  dirplot map . --no-show --output treemap.png  [dim]# save to file[/dim]\n\n"
    "  dirplot map github://owner/repo  [dim]# map a GitHub repo[/dim]\n\n"
    "  dirplot map . --inline  [dim]# render inline (iTerm2 / Kitty / Ghostty)[/dim]\n\n"
    "  dirplot map . --legend 20  [dim]# show file-count legend (top 20)[/dim]\n\n"
    "  dirplot map . --exclude .venv --exclude .git  [dim]# skip paths[/dim]\n\n"
    "  dirplot map . --colormap Set2 --font-size 14  [dim]# custom colours and label size[/dim]\n\n"
    "  dirplot map . --size 1920x1080 --no-show --output out.png  [dim]# fixed resolution[/dim]\n\n"
    "  dirplot map . --no-header --inline  [dim]# suppress info lines before the plot[/dim]\n\n"
    "  dirplot map . --no-cushion  [dim]# makes tiles look flat[/dim]\n\n"
    "  dirplot map archive.zip  [dim]# map a zip archive without unpacking[/dim]\n\n"
    "  dirplot map release.tar.gz --depth 2  [dim]# limit depth into a tarball[/dim]\n\n"
    "  dirplot map app.jar --exclude META-INF  [dim]# skip a member directory[/dim]\n\n"
    "  dirplot map src tests  [dim]# map two subtrees under their common parent[/dim]\n\n"
    "  dirplot map . --subtree src --subtree tests  [dim]# same result, explicit root[/dim]"
)


@app.command(name="termsize")
def termsize() -> None:
    """Show the current terminal size in characters and pixels."""
    cols, rows, width_px, height_px = get_terminal_size()
    typer.echo(f"Characters : {cols} cols × {rows} rows")
    typer.echo(f"Pixels     : {width_px} × {height_px}")


@app.command(name="watch")
def watch_cmd(
    path: Path = typer.Argument(..., help="Directory to watch"),
    output: Path = typer.Option(..., "--output", "-o", help="Output file (.png or .svg)"),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    font_size: int = typer.Option(12, "--font-size", help="Directory label font size in pixels"),
    colormap: str = typer.Option("tab20", "--colormap", "-c", help="Matplotlib colormap"),
    size: str | None = typer.Option(
        None, "--size", help="Output size as WIDTHxHEIGHT", metavar="WIDTHxHEIGHT"
    ),
    cushion: bool = typer.Option(
        True, "--cushion/--no-cushion", help="Apply van Wijk cushion shading"
    ),
    animate: bool = typer.Option(
        False,
        "--animate/--no-animate",
        help="Build an animated PNG (APNG) by appending each new frame",
    ),
    log: bool = typer.Option(
        False,
        "--log/--no-log",
        help="Use log of file sizes for layout, making small files more visible",
    ),
) -> None:
    """Watch a directory and regenerate the treemap on every file change."""
    from dirplot.watch import TreemapEventHandler

    try:
        from watchdog.observers import Observer
    except ImportError:
        typer.echo("Error: watchdog is required. Run: pip install watchdog", err=True)
        raise typer.Exit(1) from None

    if not path.exists() or not path.is_dir():
        typer.echo(f"Error: not a directory: {path}", err=True)
        raise typer.Exit(1)

    if animate and output.suffix.lower() == ".svg":
        typer.echo("Error: --animate requires a PNG output file.", err=True)
        raise typer.Exit(1)

    if size is not None:
        try:
            w_str, h_str = size.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(f"Invalid --size '{size}'. Expected WIDTHxHEIGHT.", err=True)
            raise typer.Exit(1) from None
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px

    excluded = frozenset(Path(e).resolve() for e in exclude)
    root = path.resolve()

    handler = TreemapEventHandler(
        root,
        output,
        exclude=excluded,
        width_px=width_px,
        height_px=height_px,
        font_size=font_size,
        colormap=colormap,
        cushion=cushion,
        animate=animate,
        log=log,
    )

    # Generate an initial treemap immediately
    handler._regenerate()

    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    typer.echo(f"Watching {root} → {output}  (Ctrl-C to stop)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


@app.command(name="read-meta")
def read_meta(
    file: Path = typer.Argument(..., help="PNG or SVG file to read dirplot metadata from"),
) -> None:
    """Read dirplot metadata embedded in a PNG or SVG file."""
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(1)

    suffix = file.suffix.lower()

    if suffix == ".png":
        from PIL import Image

        img = Image.open(file)
        info = img.info
        meta_keys = {"Date", "Software", "URL", "Python", "OS", "Command"}
        found = {k: v for k, v in info.items() if k in meta_keys}
        if not found:
            typer.echo("No dirplot metadata found in PNG.", err=True)
            raise typer.Exit(1)
        for k, v in found.items():
            typer.echo(f"{k}: {v}")

    elif suffix == ".svg":
        content = file.read_text(encoding="utf-8")
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            typer.echo(f"Error parsing SVG: {exc}", err=True)
            raise typer.Exit(1) from exc
        svg_meta: dict[str, str] = {}
        for desc in root.iter("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
            for child in desc:
                local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                ns_uri = child.tag.split("}")[0].lstrip("{") if "}" in child.tag else ""
                if ns_uri == "https://github.com/deeplook/dirplot#" and child.text:
                    svg_meta[local] = child.text
        if not svg_meta:
            typer.echo("No dirplot metadata found in SVG.", err=True)
            raise typer.Exit(1)
        for k, v in svg_meta.items():
            typer.echo(f"{k}: {v}")

    else:
        typer.echo(f"Unsupported file type: {suffix!r}. Expected .png or .svg", err=True)
        raise typer.Exit(1)


@app.command(name="map", epilog=_EPILOG)
def main(
    roots: list[str] = typer.Argument(
        ...,
        help="Root(s) to map: one or more local directories (multiple → shows only those "
        "subtrees under their common parent), archive file, ssh://…, s3://…, "
        r"github://owner/repo\[@branch], https://github.com/owner/repo\[/tree/branch], "
        r"docker://container:/path, or pod://pod-name\[@namespace]/path",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output path (optional). Use .svg extension for SVG output."
    ),
    fmt: str | None = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format: png or svg. Defaults to svg if --output ends in .svg, else png.",
        metavar="FORMAT",
    ),
    show: bool = typer.Option(True, "--show/--no-show", help="Display the image after rendering"),
    inline: bool = typer.Option(
        False,
        "--inline",
        help="Show in terminal (auto-detects iTerm2/Kitty protocol) instead of a separate window",
    ),
    legend: int | None = typer.Option(
        None,
        "--legend",
        help="Show file-count legend; value sets max entries shown (default: 20)",
        metavar="N",
    ),
    font_size: int = typer.Option(
        12, "--font-size", help="Directory label font size in pixels (default: 12)"
    ),
    colormap: str = typer.Option(
        "tab20",
        "--colormap",
        "-c",
        help=(
            "Matplotlib colormap for file-extension colours (default: tab20). "
            "The default uses the GitHub Linguist palette for known extensions; "
            "any other colormap overrides Linguist and applies to all extensions. "
            "Qualitative maps (tab10, tab20, Set1-3, Paired, Accent, Dark2, Pastel1-2) "
            "give distinct hues. "
            "Sequential maps (viridis, plasma, inferno, Blues, Greens, …) "
            "blend across a gradient. "
            "Diverging maps (coolwarm, RdBu, Spectral, …) "
            "have two contrasting hues. "
            "Run with an invalid name to see all options."
        ),
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    subtrees: list[str] = typer.Option(
        [],
        "--subtree",
        "-s",
        help=(
            "Show only this named direct child of the root (repeatable). "
            "Allowlist complement to --exclude: use when it is easier to name what you want."
        ),
    ),
    ssh_key: str | None = typer.Option(
        None, "--ssh-key", help="SSH private key file (default: ~/.ssh/id_rsa)"
    ),
    ssh_password: str | None = typer.Option(
        None, "--ssh-password", envvar="SSH_PASSWORD", help="SSH password"
    ),
    depth: int | None = typer.Option(
        None, "--depth", help="Maximum recursion depth (local and remote)"
    ),
    aws_profile: str | None = typer.Option(
        None, "--aws-profile", envvar="AWS_PROFILE", help="AWS profile name for S3 access"
    ),
    no_sign: bool = typer.Option(
        False, "--no-sign", help="Skip AWS signing for anonymous access to public S3 buckets"
    ),
    github_token: str | None = typer.Option(
        None, "--github-token", envvar="GITHUB_TOKEN", help="GitHub personal access token"
    ),
    k8s_namespace: str | None = typer.Option(
        None, "--k8s-namespace", "-N", help="Kubernetes namespace (overrides @namespace in pod URL)"
    ),
    k8s_container: str | None = typer.Option(
        None, "--k8s-container", help="Container name for multi-container pods"
    ),
    size: str | None = typer.Option(
        None,
        "--size",
        help="Output size as WIDTHxHEIGHT in pixels (e.g. 1920x1080). Defaults to terminal size.",
        metavar="WIDTHxHEIGHT",
    ),
    header: bool = typer.Option(
        True, "--header/--no-header", help="Print info lines before rendering (default: on)"
    ),
    cushion: bool = typer.Option(
        True,
        "--cushion/--no-cushion",
        help="Apply van Wijk cushion shading: gives each tile a raised 3-D look.",
    ),
    log: bool = typer.Option(
        False,
        "--log/--no-log",
        help="Use log of file sizes for layout, making small files more visible.",
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        help="Password for encrypted archives. Prompted interactively if not supplied and needed.",
    ),
) -> None:
    """Create a nested treemap bitmap for a directory tree."""
    if not roots:
        typer.echo("Error: at least one path is required.", err=True)
        raise typer.Exit(1)
    root = roots[0]  # alias used by all single-root branches below

    if colormap not in plt.colormaps():
        valid = ", ".join(sorted(plt.colormaps()))
        typer.echo(f"Unknown colormap '{colormap}'. Valid options:\n{valid}", err=True)
        raise typer.Exit(1)

    t_scan_start = time.monotonic()
    if len(roots) > 1:
        for r in roots:
            if any(
                f(r)
                for f in (
                    is_docker_path,
                    is_pod_path,
                    is_github_path,
                    is_s3_path,
                    is_ssh_path,
                    is_archive_path,
                )
            ):
                typer.echo(
                    f"Multiple roots are only supported for local directories, got: {r}",
                    err=True,
                )
                raise typer.Exit(1)
        root_paths: list[Path] = []
        for r in roots:
            rp = Path(r)
            if not rp.exists():
                typer.echo(f"Path does not exist: {r}", err=True)
                raise typer.Exit(1)
            if not rp.is_dir():
                typer.echo(f"Not a directory: {r}", err=True)
                raise typer.Exit(1)
            root_paths.append(rp.resolve())
        excluded = frozenset(Path(e).resolve() for e in exclude)
        if header:
            import os

            common_str = os.path.commonpath([str(p) for p in root_paths])
            typer.echo(f"Scanning {len(roots)} paths under {common_str} ...")
        root_node = build_tree_multi(root_paths, excluded, depth)
    elif is_docker_path(root):
        docker_container, docker_path = parse_docker_path(root)
        if header:
            typer.echo(f"Scanning docker://{docker_container}:{docker_path} ...")
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
        if header:
            ns_label = f"@{namespace}" if namespace else ""
            typer.echo(f"Scanning pod://{pod_name}{ns_label}:{pod_path} ...")
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
        if header:
            subpath_label = f"/{gh_subpath}" if gh_subpath else ""
            typer.echo(f"Scanning github:{gh_owner}/{gh_repo}@{resolved_ref}{subpath_label} ...")
    elif is_s3_path(root):
        bucket, prefix = parse_s3_path(root)
        if header:
            typer.echo(f"Scanning {root} ...")
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
        if header:
            typer.echo(f"Scanning {root} ...")
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
    elif is_archive_path(root):
        archive_path = Path(root)
        if not archive_path.exists():
            typer.echo(f"Path does not exist: {root}", err=True)
            raise typer.Exit(1)
        if not archive_path.is_file():
            typer.echo(f"Not a file: {root}", err=True)
            raise typer.Exit(1)
        if header:
            typer.echo(f"Reading archive {root} ...")
        try:
            root_node = build_tree_archive(
                archive_path, exclude=frozenset(exclude), depth=depth, password=password
            )
        except PasswordRequired as exc:
            if password is not None:
                typer.echo("Error: incorrect password.", err=True)
                raise typer.Exit(1) from exc
            pw = typer.prompt("Password", hide_input=True)
            try:
                root_node = build_tree_archive(
                    archive_path, exclude=frozenset(exclude), depth=depth, password=pw
                )
            except PasswordRequired as exc2:
                typer.echo("Error: incorrect password.", err=True)
                raise typer.Exit(1) from exc2
        except (OSError, RuntimeError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    else:
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
            ext = rp.suffix.lower() if rp.suffix else "(no ext)"
            file_node = Node(name=rp.name, path=rp, size=file_size, is_dir=False, extension=ext)
            root_node = Node(
                name=rp.parent.name,
                path=rp.parent,
                size=file_size,
                is_dir=True,
                children=[file_node],
            )
            if header:
                typer.echo(f"Scanning {root} ...")
        else:
            excluded = frozenset(Path(e).resolve() for e in exclude)
            if header:
                typer.echo(f"Scanning {root} ...")
            root_node = build_tree(root_path.resolve(), excluded, depth)

    if subtrees:
        root_node = prune_to_subtrees(root_node, set(subtrees))

    t_scan = time.monotonic() - t_scan_start
    if log:
        apply_log_sizes(root_node)
    total_files = len(collect_extensions(root_node))
    if header:
        _f = "file" if total_files == 1 else "files"
        typer.echo(
            f"Found {total_files:,} {_f}, total size: {root_node.size:,} bytes  [{t_scan:.1f}s]"
        )

    if size is not None:
        try:
            w_str, h_str = size.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(
                f"Invalid --size value '{size}'. Expected format: WIDTHxHEIGHT (e.g. 1920x1080)",
                err=True,
            )
            raise typer.Exit(1) from None
        if header:
            typer.echo(f"Output size: {width_px}x{height_px}px")
    else:
        term_w, term_h, row_px = get_terminal_pixel_size()
        width_px = term_w + 1
        height_px = term_h - 3 * row_px
        if header:
            typer.echo(f"Terminal size: {width_px}x{height_px}px")

    # Resolve output format: explicit --format > inferred from --output extension > png
    if fmt is not None:
        if fmt not in ("png", "svg"):
            typer.echo(f"Unknown format '{fmt}'. Valid options: png, svg", err=True)
            raise typer.Exit(1)
        use_svg = fmt == "svg"
    elif output is not None and output.suffix.lower() == ".svg":
        use_svg = True
    else:
        use_svg = False

    t_render_start = time.monotonic()
    if use_svg:
        buf = create_treemap_svg(
            root_node, width_px, height_px, font_size, colormap, legend, cushion
        )
    else:
        buf = create_treemap(root_node, width_px, height_px, font_size, colormap, legend, cushion)
    t_render = time.monotonic() - t_render_start

    if output is not None:
        output.write_bytes(buf.read())
        if header:
            typer.echo(f"Saved dirplot to {output}  [{t_render:.1f}s]")
        buf.seek(0)

    if show:
        if use_svg:
            if output is not None:
                webbrowser.open(output.resolve().as_uri())
            else:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
                    tmp.write(buf.read())
                    webbrowser.open(Path(tmp.name).resolve().as_uri())
        elif inline:
            display_inline(buf)
        else:
            display_window(buf)
