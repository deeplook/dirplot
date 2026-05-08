"""Typer application instance and top-level callback."""

import typer

from dirplot import __version__

app = typer.Typer(
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode="rich",
    epilog="Docs & issues: https://github.com/deeplook/dirplot",
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
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable ANSI color output (equivalent to setting NO_COLOR=1).",
        is_eager=True,
        hidden=False,
    ),
) -> None:
    if no_color:
        import os

        os.environ["NO_COLOR"] = "1"
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()
