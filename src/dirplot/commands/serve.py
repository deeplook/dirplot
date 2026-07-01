"""The ``serve`` command: launch an interactive treemap website."""

from __future__ import annotations

import webbrowser

import typer

from dirplot.app import app
from dirplot.defaults import DEFAULT_COLORMAP

_DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git",
    ".venv",
    "node_modules",
    ".yarn",
    ".pnpm-store",
    "__pycache__",
    "*.pyc",
    ".mypy_cache",
)

_SERVE_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot serve .  [dim]# serve current directory[/dim]\n\n"
    "  dirplot serve src --port 9000  [dim]# custom port[/dim]\n\n"
    "  dirplot serve github://owner/repo --no-browser  [dim]# read-only remote[/dim]\n\n"
    "  dirplot serve . --depth 4  [dim]# limit tree depth[/dim]\n\n"
    "Requires [bold]dirplot[serve][/bold] extras:\n"
    "  pip install dirplot[serve]"
)


def _check_deps() -> None:
    missing = []
    for pkg in ("fastapi", "uvicorn", "jinja2"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        typer.echo(
            f"[serve] Missing dependencies: {', '.join(missing)}\n"
            "Install with: pip install 'dirplot[serve]'",
            err=True,
        )
        raise typer.Exit(1)


@app.command(name="serve", epilog=_SERVE_EPILOG)
def serve_cmd(
    root: str = typer.Argument(
        default=".",
        help=(
            "Root path or source URL to serve. Accepts the same inputs as "
            r"[bold]dirplot map[/bold]: local path, github://owner/repo, ssh://…, etc."
        ),
    ),
    port: int = typer.Option(8765, "--port", "-p", help="HTTP port to bind.", show_default=True),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address.", show_default=True),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Don't open the browser automatically."
    ),
    depth: int | None = typer.Option(
        None, "--depth", "-d", help="Maximum directory depth to scan.", metavar="N"
    ),
    exclude: list[str] = typer.Option(
        [],
        "--exclude",
        "-e",
        help="Glob pattern(s) to exclude (repeatable).",
        metavar="PATTERN",
    ),
    colormap: str = typer.Option(
        DEFAULT_COLORMAP, "--colormap", help="Matplotlib colormap name for file colors."
    ),
    breadcrumbs: bool = typer.Option(
        True,
        "--breadcrumbs/--no-breadcrumbs",
        help="Collapse single-subdirectory chains into breadcrumb labels.",
    ),
    watch: bool = typer.Option(
        True,
        "--watch/--no-watch",
        help="Auto-reload the treemap when files change on disk (local sources only).",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress uvicorn access logs."),
) -> None:
    """Launch an interactive treemap in the browser.

    Opens a local web server and renders the directory tree as a zoomable,
    navigable D3.js treemap.  File operations (delete, move) are available
    for local filesystem sources only.
    """
    _check_deps()

    import uvicorn

    from dirplot.tree_json import is_readonly_source, resolve_root_path
    from dirplot.web.server import ServeConfig, create_app

    allow_write = not is_readonly_source(root)
    root_path = resolve_root_path(root)

    config = ServeConfig(
        root=root,
        root_path=root_path,
        colormap=colormap,
        depth=depth,
        exclude=frozenset(exclude) if exclude else frozenset(_DEFAULT_EXCLUDES),
        breadcrumbs=breadcrumbs,
        allow_write=allow_write,
        watch=watch,
    )

    fastapi_app = create_app(config)

    url = f"http://{host}:{port}/"
    if not no_browser:
        import threading

        threading.Timer(0.8, webbrowser.open, args=[url]).start()

    typer.echo(f"[serve] Serving {root!r} at {url}  (Ctrl-C to stop)")
    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        log_level="warning" if quiet else "info",
        lifespan="off",
    )
