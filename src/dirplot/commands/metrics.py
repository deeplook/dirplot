"""The ``metrics`` command: print detailed tree metrics."""

import os
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.helpers.scan import scan_tree
from dirplot.scanner import prune_to_subtrees, tree_metrics, tree_metrics_dict


@app.command(name="metrics")
def metrics_command(
    roots: list[str] = typer.Argument(
        default=None,
        help="Root(s) to scan. Supports the same sources as the map command.",
    ),
    paths_from: Path | None = typer.Option(
        None,
        "--paths-from",
        help="File containing a path list in tree or find output format. Use - for stdin.",
        metavar="FILE",
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Paths to exclude (repeatable)"),
    include: list[str] = typer.Option(
        [],
        "--include",
        help="Show only this subtree (repeatable; supports nested paths). Allowlist complement to --exclude.",  # noqa: E501
    ),
    depth: int | None = typer.Option(
        None, "--depth", help="Maximum recursion depth (local and remote)"
    ),
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
    top_n: int = typer.Option(
        10, "--top", help="Number of top extensions / largest files / largest dirs to show."
    ),
    sort_by: str = typer.Option(
        "count",
        "--sort-by",
        help="Sort top extensions by: count (default) or size.",
        metavar="FIELD",
    ),
    as_json: bool = typer.Option(False, "--json/--no-json", help="Output metrics as JSON."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
    no_input: bool = typer.Option(
        False,
        "--no-input",
        help="Disable all interactive prompts; fail instead of prompting for passwords.",
    ),
) -> None:
    """Print detailed metrics for a scanned directory tree."""
    roots = roots or []

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

    def _metrics_log(msg: str) -> None:
        if not quiet:
            typer.echo(msg, err=True)

    root_node, t_scan, _ = scan_tree(
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
        log=_metrics_log,
    )
    if include:
        root_node = prune_to_subtrees(root_node, set(include))
    if sort_by not in ("count", "size"):
        typer.echo(f"Invalid --sort-by value '{sort_by}'. Choose: count, size", err=True)
        raise typer.Exit(1)
    if as_json:
        import json

        typer.echo(
            json.dumps(tree_metrics_dict(root_node, t_scan, top_n=top_n, sort_by=sort_by), indent=2)
        )
    else:
        typer.echo(tree_metrics(root_node, t_scan, top_n=top_n, sort_by=sort_by))
