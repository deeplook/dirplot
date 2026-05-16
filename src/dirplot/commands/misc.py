"""Small standalone commands: termsize, read-meta, demo."""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import typer

from dirplot.app import app
from dirplot.terminal import get_terminal_size

_TERMSIZE_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot termsize  [dim]# print cols × rows and pixel dimensions[/dim]\n\n"
    "  dirplot termsize  [dim]# run before dirplot map to check the default canvas size[/dim]"
)

_READ_META_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot read-meta treemap.png  [dim]# read metadata from a PNG[/dim]\n\n"
    "  dirplot read-meta treemap.svg  [dim]# read metadata from an SVG[/dim]\n\n"
    "  dirplot read-meta history.mp4  [dim]# read metadata from an MP4 (requires ffprobe)[/dim]\n\n"
    "  dirplot read-meta a.png b.png c.svg  [dim]# multiple files[/dim]\n\n"
    "  dirplot read-meta *.png  [dim]# glob expansion[/dim]"
)

_DEMO_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot demo  [dim]# run all examples, save to ./demo/[/dim]\n\n"
    "  dirplot demo --output ~/dirplot-demo  [dim]# custom output folder[/dim]\n\n"
    "  dirplot demo --github-url https://github.com/pallets/flask"
    "  [dim]# use a different GitHub repo for remote examples[/dim]\n\n"
    "  dirplot demo --interactive  [dim]# step through each command with confirmation[/dim]"
)


@app.command(name="termsize", epilog=_TERMSIZE_EPILOG)
def termsize() -> None:
    """Show the current terminal size in characters and pixels."""
    cols, rows, width_px, height_px = get_terminal_size()
    typer.echo(f"Characters : {cols} cols × {rows} rows")
    typer.echo(f"Pixels     : {width_px} × {height_px}")


@app.command(name="read-meta", epilog=_READ_META_EPILOG)
def read_meta(
    files: list[Path] = typer.Argument(
        ..., help="PNG, SVG, or MP4/MOV file(s) to read dirplot metadata from"
    ),
) -> None:
    """Read dirplot metadata embedded in one or more PNG, SVG, or MP4/MOV files."""
    any_error = False

    for file in files:
        if len(files) > 1:
            typer.echo(f"==> {file} <==")

        if not file.exists():
            typer.echo(f"Error: file not found: {file}", err=True)
            any_error = True
            continue

        suffix = file.suffix.lower()

        if suffix == ".png":
            from PIL import Image

            img = Image.open(file)
            info = img.info
            meta_keys = {"Date", "Software", "URL", "Python", "OS", "Command"}
            found = {k: v for k, v in info.items() if k in meta_keys}
            if not found:
                typer.echo("No dirplot metadata found in PNG.", err=True)
                any_error = True
                continue
            for k, v in found.items():
                typer.echo(f"{k}: {v}")

        elif suffix == ".svg":
            content = file.read_text(encoding="utf-8")
            try:
                root = ET.fromstring(content)
            except ET.ParseError as exc:
                typer.echo(f"Error parsing SVG: {exc}", err=True)
                any_error = True
                continue
            svg_meta: dict[str, str] = {}
            for desc in root.iter("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
                for child in desc:
                    local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    ns_uri = child.tag.split("}")[0].lstrip("{") if "}" in child.tag else ""
                    if ns_uri == "https://github.com/deeplook/dirplot#" and child.text:
                        svg_meta[local] = child.text
            if not svg_meta:
                typer.echo("No dirplot metadata found in SVG.", err=True)
                any_error = True
                continue
            for k, v in svg_meta.items():
                typer.echo(f"{k}: {v}")

        elif suffix in {".mp4", ".mov"}:
            import json
            import shutil
            import subprocess

            if not shutil.which("ffprobe"):
                typer.echo("Error: ffprobe not found on PATH (install ffmpeg).", err=True)
                any_error = True
                continue
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file)],
                capture_output=True,
            )
            if result.returncode != 0:
                typer.echo(
                    f"Error reading MP4 metadata: {result.stderr.decode(errors='replace')}",
                    err=True,
                )
                any_error = True
                continue
            tags = json.loads(result.stdout).get("format", {}).get("tags", {})
            meta_keys = {"Date", "Software", "URL", "Python", "OS", "Command"}
            found = {k: v for k, v in tags.items() if k in meta_keys}
            if not found:
                typer.echo("No dirplot metadata found in MP4.", err=True)
                any_error = True
                continue
            for k, v in found.items():
                typer.echo(f"{k}: {v}")

        else:
            typer.echo(
                f"Unsupported file type: {suffix!r}. Expected .png, .svg, or .mp4/.mov", err=True
            )
            any_error = True

    if any_error:
        raise typer.Exit(1)


@app.command(name="demo", epilog=_DEMO_EPILOG)
def demo_cmd(
    output: Path = typer.Option(
        Path("demo"), "--output", "-o", help="Folder for generated output files"
    ),
    github_url: str = typer.Option(
        "https://github.com/deeplook/dirplot",
        "--github-url",
        help="GitHub repository URL used for remote examples",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Ask for confirmation before each command is run"
    ),
) -> None:
    """Run a set of example commands to illustrate dirplot features."""
    import subprocess

    output.mkdir(parents=True, exist_ok=True)

    # Convert https://github.com/owner/repo → github://owner/repo
    m = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", github_url)
    gh_path = f"github://{m.group(1)}" if m else github_url

    base_cmd = [sys.executable, "-m", "dirplot"]

    examples: list[tuple[str, list[str]]] = [
        (
            "termsize — show current terminal dimensions",
            ["termsize"],
        ),
        (
            "map local directory (dark mode, PNG)",
            [
                "map",
                ".",
                "--no-show",
                "--output",
                str(output / "map-local.png"),
                "--size",
                "800x600",
            ],
        ),
        (
            "map local directory — highlight one file, a glob, and a folder",
            [
                "map",
                "tests",
                "--no-show",
                "--output",
                str(output / "map-highlight.png"),
                "--size",
                "800x600",
                "--log-scale",
                "4",
                "--highlight",
                "tests/conftest.py@red",
                "--highlight",
                "**/test_git*.py@cyan",
                "--highlight",
                "tests/fixtures@lime",
            ],
        ),
        (
            "map github repo (dark mode, PNG)",
            [
                "map",
                gh_path,
                "--no-show",
                "--output",
                str(output / "map-github.png"),
                "--size",
                "800x600",
            ],
        ),
        (
            "map local directory (light mode, SVG)",
            [
                "map",
                ".",
                "--no-show",
                "--output",
                str(output / "map-local.svg"),
                "--size",
                "800x600",
                "--light",
            ],
        ),
        (
            "git — last 5 commits of github repo (static PNG)",
            [
                "git",
                gh_path,
                "--output",
                str(output / "git-static.png"),
                "--size",
                "800x600",
                "--range",
                "HEAD~5..HEAD",
            ],
        ),
        (
            "git — last 10 commits of github repo (animated MP4)",
            [
                "git",
                gh_path,
                "--output",
                str(output / "git.mp4"),
                "--size",
                "800x600",
                "--range",
                "HEAD~10..HEAD",
                "--total-duration",
                "20",
            ],
        ),
        (
            "git — last 10 commits of github repo (animated PNG with fade-out)",
            [
                "git",
                gh_path,
                "--output",
                str(output / "git-animated.png"),
                "--size",
                "800x600",
                "--range",
                "HEAD~10..HEAD",
                "--total-duration",
                "20",
                "--fade-out",
            ],
        ),
        (
            "git — last 10 commits of steipete/peekaboo (animated MP4, log scale)",
            [
                "git",
                "github://steipete/peekaboo",
                "--output",
                str(output / "git-steipete-peekaboo.mp4"),
                "--size",
                "1920x1080",
                "--range",
                "HEAD~10..HEAD",
                "--log-scale",
                "4",
            ],
        ),
        (
            "read-meta — metadata embedded in a generated PNG",
            ["read-meta", str(output / "map-local.png")],
        ),
    ]

    skipped = [
        ("watch", "interactive; watches a directory for changes indefinitely"),
        ("replay", "interactive; requires a JSONL event log produced by `watch --event-log`"),
    ]

    from rich.console import Console
    from rich.panel import Panel

    console = Console(highlight=False)

    console.print()
    console.print(
        Panel(
            f"[bold cyan]dirplot demo[/bold cyan]\n[dim]Outputs →[/dim] {output.resolve()}/",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    n_total = len(examples)
    for i, (label, args) in enumerate(examples, 1):
        cmd_display = "dirplot " + " ".join(args)
        console.print()
        console.rule(f"[bold]{i}/{n_total}[/bold]  {label}", style="cyan")
        console.print(f"  [dim]$[/dim] [bold cyan]{cmd_display}[/bold cyan]")
        console.print()

        if interactive:
            from rich.prompt import Confirm

            if not Confirm.ask("  Run this command?", default=True, console=console):
                console.print("  [yellow]⏭  Skipped[/yellow]")
                continue

        result = subprocess.run(base_cmd + args)

        console.print()
        if result.returncode == 0:
            console.print("  [bold green]✓  Done[/bold green]")
        else:
            console.print(f"  [bold red]✗  Exited with code {result.returncode}[/bold red]")

    console.print()
    console.rule(style="dim")
    for cmd_name, reason in skipped:
        console.print(f"  [dim]⏭  [bold]{cmd_name}[/bold]: {reason}[/dim]")

    console.print()
    console.print(
        Panel(
            f"[bold green]✓  Demo complete[/bold green]\n"
            f"[dim]Outputs saved to:[/dim] {output.resolve()}/",
            border_style="green",
            padding=(0, 2),
        )
    )
