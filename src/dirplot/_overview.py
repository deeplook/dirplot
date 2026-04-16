"""_overview.py: Reusable overview command for Typer applications.

This module provides a plug-and-play `overview` command that prints a
human-readable summary of any Typer application, including:
- Application name and description
- Global options (from @app.callback)
- All commands with their arguments and options
- Nested sub-commands (from add_typer) at any depth

Usage:
    from dirplot._overview import add_overview_command

    add_overview_command(app)  # call after defining all commands

Note:
    Call add_overview_command() AFTER registering all commands and sub-apps
    to ensure they appear in the overview output.
"""

from importlib import metadata
from typing import Any

import click
import typer


def add_overview_command(
    app: typer.Typer,
    name: str = "overview",
    help_text: str = (
        "Display an overview of all commands, global options, and"
        " command-specific options/arguments."
    ),
) -> None:
    """
    Register an overview command on the given Typer application.

    Args:
        app: The Typer application to add the overview command to.
        name: The name of the overview command (default: "overview").
        help_text: Help text for the overview command.
    """

    @app.command(name=name, help=help_text)
    def overview_command() -> None:
        _print_overview(app)


def _print_overview(app: typer.Typer) -> None:
    """Print the full application overview."""
    typer.echo("Application Overview")
    typer.echo("=" * 80)

    # Build the Click command/group from the Typer app.
    click_group = typer.main.get_command(app)

    app_name, app_description, app_version = _resolve_app_metadata(app, click_group)
    commands = getattr(click_group, "commands", {}) or {}
    global_params = getattr(click_group, "params", []) or []
    global_option_count = sum(isinstance(param, click.Option) for param in global_params)

    typer.echo("\nApplication")
    typer.echo(f"  Name        : {app_name}")
    typer.echo(f"  Description : {app_description}")
    if app_version:
        typer.echo(f"  Version     : {app_version}")
    typer.echo(f"  Commands    : {len(commands)} top-level")
    typer.echo(f"  Global opts : {global_option_count}")

    # Global options (from callback / group params)
    typer.echo("\nGlobal Options")
    if global_params:
        for param in global_params:
            _print_param(param, is_global=True)
    else:
        typer.echo("  (none)")

    # Commands (with recursive handling of nested groups)
    typer.echo("\nCommands")
    _print_commands(click_group, indent=1)


def _print_commands(
    group: click.Command,
    indent: int = 1,
    max_depth: int = 10,
    seen: set[int] | None = None,
) -> None:
    """Recursively print commands, handling nested command groups."""
    if seen is None:
        seen = set()

    # Cycle detection
    group_id = id(group)
    if group_id in seen:
        typer.echo("  " * indent + "(circular reference detected)")
        return
    seen.add(group_id)

    # Depth limit
    if indent > max_depth:
        typer.echo("  " * indent + "(max depth reached)")
        return

    commands = getattr(group, "commands", {}) or {}
    if not commands:
        typer.echo("  " * indent + "(no commands registered)")
        return

    base_indent = "  " * indent

    for cmd_name in sorted(commands.keys()):
        cmd = commands[cmd_name]
        cmd_help = getattr(cmd, "help", None) or "(no description)"

        # Check if this command is itself a group (nested sub-application)
        is_group = isinstance(cmd, click.Group)
        group_marker = " [group]" if is_group else ""

        typer.echo(f"\n{base_indent}{cmd_name}{group_marker}")
        typer.echo(f"{base_indent}  Help : {cmd_help}")

        # Print group-level options if this is a nested group
        if is_group:
            group_params = getattr(cmd, "params", []) or []
            group_opts = [p for p in group_params if isinstance(p, click.Option)]
            if group_opts:
                typer.echo(f"{base_indent}  Group Options:")
                for opt in group_opts:
                    _print_param(opt, indent=indent + 2)

            # Recursively print sub-commands
            typer.echo(f"{base_indent}  Sub-commands:")
            _print_commands(cmd, indent=indent + 2, max_depth=max_depth, seen=seen)
        else:
            # Regular command: print its parameters
            params = getattr(cmd, "params", []) or []
            if not params:
                typer.echo(f"{base_indent}  Parameters : (none)")
                continue

            args = [p for p in params if isinstance(p, click.Argument)]
            opts = [p for p in params if isinstance(p, click.Option)]

            if args:
                typer.echo(f"{base_indent}  Arguments:")
                for arg in args:
                    _print_param(arg, indent=indent + 2)

            if opts:
                typer.echo(f"{base_indent}  Options:")
                for opt in opts:
                    _print_param(opt, indent=indent + 2)


def _print_param(param: Any, is_global: bool = False, indent: int = 3) -> None:
    """Helper to format and display a Click Parameter object."""
    base_indent = "  " * indent
    prefix = "Global " if is_global else ""
    if isinstance(param, click.Option):
        names = ", ".join(param.opts) if getattr(param, "opts", None) else (param.name or "?")
        help_text = getattr(param, "help", None)
    else:
        # click.Argument has no .opts and no .help
        names = param.name or "?"
        help_text = None
    try:
        type_name = param.type.name if hasattr(param.type, "name") else str(param.type)
    except (AttributeError, TypeError):
        type_name = "unknown"
    default_str = (
        f" (default: {param.default!r})" if param.default is not None and not param.required else ""
    )
    required_str = " [required]" if param.required else ""

    line = f"{base_indent}{names:<18} : {type_name}{default_str}{required_str}"
    if help_text:
        line += f"  — {help_text}"

    typer.echo(prefix + line)


def _resolve_app_metadata(
    app: typer.Typer, click_group: click.Command
) -> tuple[str, str, str | None]:
    """Return a best-effort (name, description, version) tuple for the app."""
    app_name = _clean_text(getattr(click_group, "name", None))
    app_description = _clean_text(getattr(click_group, "help", None))
    app_version: str | None = None

    package_name = _infer_package_name(app)
    if package_name:
        app_name = app_name or package_name
        dist_names = metadata.packages_distributions().get(package_name, [package_name])
        for dist_name in dist_names:
            try:
                meta = metadata.metadata(dist_name)
                app_name = app_name or _clean_text(meta.get("Name"))
                app_description = app_description or _clean_text(meta.get("Summary"))
                app_version = metadata.version(dist_name)
                break
            except metadata.PackageNotFoundError:
                continue

    return app_name or "(unnamed)", app_description or "(no description)", app_version


def _infer_package_name(app: typer.Typer) -> str | None:
    """Infer the top-level package name from the app callback or commands."""
    callback_info = getattr(app, "registered_callback", None)
    callback = getattr(callback_info, "callback", None)
    module_name = getattr(callback, "__module__", None)
    if isinstance(module_name, str) and module_name and module_name != "__main__":
        return module_name.split(".", 1)[0]

    for command_info in getattr(app, "registered_commands", []):
        command_callback = getattr(command_info, "callback", None)
        module_name = getattr(command_callback, "__module__", None)
        if isinstance(module_name, str) and module_name and module_name != "__main__":
            return module_name.split(".", 1)[0]

    return None


def _clean_text(value: Any) -> str | None:
    """Normalise help text for compact single-line overview output."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None
