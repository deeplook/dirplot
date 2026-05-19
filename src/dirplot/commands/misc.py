"""Small standalone commands: termsize, meta, demo."""

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

_META_EPILOG = (
    "[bold]Examples[/bold]\n\n"
    "  dirplot meta treemap.png  [dim]# read metadata from a PNG[/dim]\n\n"
    "  dirplot meta treemap.svg  [dim]# read metadata from an SVG[/dim]\n\n"
    "  dirplot meta history.mp4  [dim]# read metadata from an MP4 (requires ffprobe)[/dim]\n\n"
    "  dirplot meta a.png b.png c.svg  [dim]# multiple files[/dim]\n\n"
    "  dirplot meta *.png  [dim]# glob expansion[/dim]\n\n"
    "  dirplot meta --json treemap.png  [dim]# structured JSON output[/dim]"
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


def _read_meta_from_file(file: Path) -> tuple[dict[str, str] | None, str | None]:
    """Extract dirplot metadata from a file. Returns (meta_dict, error_message)."""
    if not file.exists():
        return None, f"file not found: {file}"

    suffix = file.suffix.lower()

    if suffix == ".png":
        from PIL import Image

        img = Image.open(file)
        meta_keys = {"Date", "Software", "URL", "Python", "OS", "Command"}
        found: dict[str, str] = {str(k): str(v) for k, v in img.info.items() if k in meta_keys}
        return (found if found else {}), None

    elif suffix == ".svg":
        content = file.read_text(encoding="utf-8")
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            return None, f"Error parsing SVG: {exc}"
        svg_meta: dict[str, str] = {}
        for desc in root.iter("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
            for child in desc:
                local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                ns_uri = child.tag.split("}")[0].lstrip("{") if "}" in child.tag else ""
                if ns_uri == "https://github.com/deeplook/dirplot#" and child.text:
                    svg_meta[local] = child.text
        return svg_meta, None

    elif suffix in {".mp4", ".mov"}:
        import json as _json
        import shutil
        import subprocess

        if not shutil.which("ffprobe"):
            return None, "ffprobe not found on PATH (install ffmpeg)"
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file)],
            capture_output=True,
        )
        if result.returncode != 0:
            return None, f"Error reading MP4 metadata: {result.stderr.decode(errors='replace')}"
        tags = _json.loads(result.stdout).get("format", {}).get("tags", {})
        meta_keys = {"Date", "Software", "URL", "Python", "OS", "Command"}
        mp4_found: dict[str, str] = {str(k): str(v) for k, v in tags.items() if k in meta_keys}
        return (mp4_found if mp4_found else {}), None

    else:
        return None, f"Unsupported file type: {suffix!r}. Expected .png, .svg, or .mp4/.mov"


@app.command(name="meta", epilog=_META_EPILOG)
def meta_cmd(
    files: list[Path] = typer.Argument(
        ..., help="PNG, SVG, or MP4/MOV file(s) to read dirplot metadata from"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output metadata as structured JSON"),
) -> None:
    """Read dirplot metadata embedded in one or more PNG, SVG, or MP4/MOV files."""
    import json

    any_error = False

    if json_output:
        results: list[dict[str, object]] = []
        for file in files:
            meta, error = _read_meta_from_file(file)
            if error and meta is None:
                results.append({"file": file.name, "has_metadata": False, "error": error})
                any_error = True
            else:
                has = bool(meta)
                entry: dict[str, object] = {
                    "file": file.name,
                    "has_metadata": has,
                    "created": (meta or {}).get("Date"),
                    "version": (meta or {}).get("Software"),
                    "command": (meta or {}).get("Command"),
                    "os": (meta or {}).get("OS"),
                    "python": (meta or {}).get("Python"),
                }
                results.append(entry)
                if not has:
                    any_error = True
        typer.echo(json.dumps(results if len(files) > 1 else results[0], indent=2))
    else:
        for file in files:
            if len(files) > 1:
                typer.echo(f"==> {file.name} <==")

            meta, error = _read_meta_from_file(file)

            if error and meta is None:
                typer.echo(f"Error: {error}", err=True)
                any_error = True
                continue

            if not meta:
                typer.echo("No dirplot metadata found.")
                any_error = True
                continue

            label_map = {
                "Date": "Created",
                "Software": "Version",
                "URL": "URL",
                "Command": "Command",
                "OS": "OS",
                "Python": "Python",
            }
            for k, v in meta.items():
                label = label_map.get(k, k)
                typer.echo(f"{label}: {v}")

            if len(files) > 1:
                typer.echo("")

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
                "--canvas",
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
                "--canvas",
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
                "--canvas",
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
                "--canvas",
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
                "--canvas",
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
                "--canvas",
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
                "--canvas",
                "800x600",
                "--range",
                "HEAD~10..HEAD",
                "--total-duration",
                "20",
                "--fade-out",
            ],
        ),
        (
            "meta — metadata embedded in a generated PNG",
            ["meta", str(output / "map-local.png")],
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
