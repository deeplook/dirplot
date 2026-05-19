"""The ``map`` command: render a directory tree as a treemap."""

import sys
import time
import webbrowser
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import cmap as _cmap_lib
import typer
from rich.console import Console as _Console

from dirplot.app import app
from dirplot.defaults import DEFAULT_COLORMAP, DEFAULT_FONT_SIZE
from dirplot.display import display_inline, display_window
from dirplot.filters import SizeRange, parse_size_range
from dirplot.helpers.highlights import resolve_highlight_specs
from dirplot.helpers.scan import scan_tree
from dirplot.render_png import create_treemap
from dirplot.scanner import (
    Node,
    apply_breadcrumbs,
    apply_log_sizes,
    collect_extensions,
    filter_by_size,
    max_depth,
    prune_to_subtrees,
    tree_metrics,
)
from dirplot.svg_render import create_treemap_svg
from dirplot.terminal import default_canvas_size, get_terminal_size


@contextmanager
def _no_op_ctx() -> Generator[None, None, None]:
    yield


_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot map .  [dim]# open in system viewer[/dim]\n\n"
    "  dirplot map . --no-show --output treemap.png  [dim]# save to file[/dim]\n\n"
    "  dirplot map github://owner/repo  [dim]# map a GitHub repo[/dim]\n\n"
    "  dirplot map . --inline  [dim]# render inline (iTerm2 / Kitty / Ghostty)[/dim]\n\n"
    "  dirplot map . --legend 20  [dim]# show file-count legend (top 20)[/dim]\n\n"
    "  dirplot map . --exclude .venv --exclude .git  [dim]# skip paths[/dim]\n\n"
    "  dirplot map . --colormap Set2 --font-size 14  [dim]# custom colours and label size[/dim]\n\n"
    "  dirplot map . --canvas 1920x1080 --no-show --output out.png  [dim]# fixed canvas[/dim]\n\n"
    "  dirplot map . --no-header --inline  [dim]# suppress info lines before the plot[/dim]\n\n"
    "  dirplot map . --no-cushion  [dim]# makes tiles look flat[/dim]\n\n"
    "  dirplot map archive.zip  [dim]# map a zip archive without unpacking[/dim]\n\n"
    "  dirplot map release.tar.gz --depth 2  [dim]# limit depth into a tarball[/dim]\n\n"
    "  dirplot map app.jar --exclude META-INF  [dim]# skip a member directory[/dim]\n\n"
    "  dirplot map src tests  [dim]# map two subtrees under their common parent[/dim]\n\n"
    "  dirplot map . --include src --include tests  [dim]# same result, explicit root[/dim]"
)


@app.command(name="map", epilog=_EPILOG)
def main(
    ctx: typer.Context,
    roots: list[str] = typer.Argument(
        default=None,
        help="Root(s) to map: one or more local directories (multiple → shows only those "
        "subtrees under their common parent), archive file, ssh://…, s3://…, "
        r"github://owner/repo\[@branch], https://github.com/owner/repo\[/tree/branch], "
        r"docker://container:/path, or pod://pod-name\[@namespace]/path. "
        "Omit to read paths from --paths-from or stdin (tree/find output).",
    ),
    paths_from: Path | None = typer.Option(
        None,
        "--paths-from",
        help="File containing a path list in tree or find output format. Use - for stdin.",
        metavar="FILE",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path (optional). Use .svg extension for SVG output. Use - for stdout.",
    ),
    fmt: str | None = typer.Option(
        None,
        "--format",
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
        DEFAULT_FONT_SIZE, "--font-size", help="Directory label font size in pixels (default: 12)"
    ),
    colormap: str = typer.Option(
        DEFAULT_COLORMAP,
        "--colormap",
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
    include: list[str] = typer.Option(
        [],
        "--include",
        "--subtree",  # hidden backwards-compat alias
        help=(
            "Show only this subtree (repeatable; supports nested paths like src/fonts). "
            "Allowlist complement to --exclude."
        ),
    ),
    ssh_key: str | None = typer.Option(
        None, "--ssh-key", help="SSH private key file (default: ~/.ssh/id_rsa)"
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
    k8s_namespace: str | None = typer.Option(
        None, "--k8s-namespace", help="Kubernetes namespace (overrides @namespace in pod URL)"
    ),
    k8s_container: str | None = typer.Option(
        None, "--k8s-container", help="Container name for multi-container pods"
    ),
    canvas: str | None = typer.Option(
        None,
        "--canvas",
        help="Output size as WIDTHxHEIGHT in pixels (e.g. 1920x1080). Defaults to terminal size.",
        metavar="WIDTHxHEIGHT",
    ),
    size_filter: list[str] | None = typer.Option(
        None,
        "--size",
        "-S",
        help=(
            "Filter files by size range (e.g. 10M..500M, 100M.., ..50K, 1G). "
            "Repeatable — multiple ranges are combined with OR logic."
        ),
        metavar="RANGE",
    ),
    keep_empty_dirs: bool = typer.Option(
        False,
        "--keep-empty-dirs",
        help="Retain directories that become empty after --size filtering.",
    ),
    header: bool = typer.Option(
        True, "--header/--no-header", help="Print info lines before rendering (default: on)"
    ),
    cushion: bool = typer.Option(
        True,
        "--cushion/--no-cushion",
        help="Apply van Wijk cushion shading: gives each tile a raised 3-D look.",
    ),
    dark: bool = typer.Option(True, "--dark/--light", help="Dark background (default) or light"),
    logscale: float = typer.Option(
        0.0,
        "--log-scale",
        help="Log-scale compression ratio (max/min ratio). 0 disables; must be > 1 to enable.",
        show_default=True,
    ),
    password_file: Path | None = typer.Option(
        None,
        "--password-file",
        help="File containing the archive password (avoids exposing the password in shell history).",  # noqa: E501
        metavar="FILE",
    ),
    ssh_password_file: Path | None = typer.Option(
        None,
        "--ssh-password-file",
        help="File containing the SSH password (avoids exposing the password in shell history).",
        metavar="FILE",
    ),
    github_token_file: Path | None = typer.Option(
        None,
        "--github-token-file",
        help="File containing a GitHub personal access token (avoids exposing the token in shell history).",  # noqa: E501
        metavar="FILE",
    ),
    breadcrumbs: bool = typer.Option(
        True,
        "--breadcrumbs/--no-breadcrumbs",
        help=(
            "Collapse single-subdirectory chains into breadcrumb labels"
            " (e.g. foo / bar / baz). Default: on."
        ),
    ),
    show_metrics: bool = typer.Option(
        False,
        "--metrics/--no-metrics",
        help="Print detailed metrics after scanning (same output as the metrics command).",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
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
    """Create a nested treemap bitmap for a directory tree.

    Example: dirplot map . --inline
    """
    import os

    roots = roots or []

    # Show help when called with no arguments and no piped input.
    if not roots and paths_from is None and sys.stdin.isatty():
        typer.echo(ctx.get_help())
        raise typer.Exit()

    to_stdout = output is not None and str(output) == "-"
    if to_stdout:
        show = False

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

    def _info(msg: str) -> None:
        if not quiet:
            typer.echo(msg, err=True)

    _valid_cmaps = set(_cmap_lib.Catalog().short_keys())
    if colormap not in _valid_cmaps:
        valid = ", ".join(sorted(_valid_cmaps))
        typer.echo(f"Unknown colormap '{colormap}'. Valid options:\n{valid}", err=True)
        raise typer.Exit(1)

    root_node, t_scan, _display_title = scan_tree(
        roots=roots,
        paths_from=paths_from,
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
        log=_info if header else None,
    )

    if include:
        root_node = prune_to_subtrees(root_node, set(include))

    if size_filter:
        parsed_ranges: list[SizeRange] = []
        for spec in size_filter:
            try:
                parsed_ranges.append(parse_size_range(spec))
            except ValueError as exc:
                typer.echo(f"Invalid --size value: {exc}", err=True)
                raise typer.Exit(1) from exc
        result = filter_by_size(root_node, parsed_ranges, keep_empty_dirs)
        if result is None:
            typer.echo("No files match the --size filter.", err=True)
            raise typer.Exit(1)
        root_node = result

    tree_depth = max_depth(root_node)

    if breadcrumbs:
        root_node = apply_breadcrumbs(root_node)

    if logscale > 1:
        apply_log_sizes(root_node, logscale)
    total_files = len(collect_extensions(root_node))
    if header:
        _f = "file" if total_files == 1 else "files"
        _info(f"Found {total_files:,} {_f}, total size: {root_node.size:,} bytes  [{t_scan:.1f}s]")

    if show_metrics:
        typer.echo(tree_metrics(root_node, t_scan), err=to_stdout)

    # Build highlight map from --highlight patterns
    highlights_dict: dict[str, str] = {}
    if highlight:

        def _collect_paths(node: Node) -> list[str]:
            paths = []
            if hasattr(node, "path"):
                paths.append(node.path.as_posix())
            for child in node.children:
                paths.extend(_collect_paths(child))
            return paths

        highlights_dict = resolve_highlight_specs(highlight, _collect_paths(root_node))

    inline_cols: int | None = None
    if canvas is not None:
        try:
            w_str, h_str = canvas.lower().split("x", 1)
            width_px, height_px = int(w_str), int(h_str)
        except ValueError:
            typer.echo(
                f"Invalid --canvas value '{canvas}'. Expected: WIDTHxHEIGHT (e.g. 1920x1080)",
                err=True,
            )
            raise typer.Exit(1) from None
        if width_px == 0 or height_px == 0:
            typer.echo(
                f"Invalid --canvas '{canvas}': width and height must both be positive.", err=True
            )
            raise typer.Exit(1)
        if header:
            _info(f"Output size: {width_px}x{height_px}px")
    else:
        width_px, height_px = default_canvas_size()
        if inline:
            inline_cols, *_ = get_terminal_size()
        if header:
            _info(f"Terminal size: {width_px}x{height_px}px")

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

    _stderr_console = _Console(stderr=True)
    t_render_start = time.monotonic()
    with _stderr_console.status("Rendering…", spinner="dots") if not quiet else _no_op_ctx():
        if use_svg:
            buf = create_treemap_svg(
                root_node,
                width_px,
                height_px,
                font_size,
                colormap,
                legend,
                cushion,
                tree_depth,
                dark,
                highlights=highlights_dict or None,
            )
        else:
            buf = create_treemap(
                root_node,
                width_px,
                height_px,
                font_size,
                colormap,
                legend,
                cushion,
                tree_depth,
                dark=dark,
                logscale=logscale,
                highlights=highlights_dict or None,
            )
    t_render = time.monotonic() - t_render_start

    if output is not None:
        if to_stdout:
            sys.stdout.buffer.write(buf.read())
            buf.seek(0)
        else:
            output.write_bytes(buf.read())
            if header:
                _info(f"Saved dirplot to {output}  [{t_render:.1f}s]")
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
            display_window(buf, title=_display_title)
