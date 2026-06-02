"""JSON serialization of Node trees for the web interface."""

from __future__ import annotations

from pathlib import Path

from dirplot.colors import RGBAColor, assign_colors
from dirplot.defaults import DEFAULT_COLORMAP
from dirplot.scanner import Node, collect_extensions

_DIR_COLOR = "#2a2d3e"


def _rgba_to_hex(color: RGBAColor) -> str:
    r, g, b, _ = color
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"  # unreachable


def build_color_map(root: Node, colormap: str = DEFAULT_COLORMAP) -> dict[str, str]:
    """Return extension → '#rrggbb' mapping for all extensions in the tree."""
    exts = collect_extensions(root)
    rgba_map = assign_colors(exts, colormap)
    return {ext: _rgba_to_hex(color) for ext, color in rgba_map.items()}


def node_to_dict(
    node: Node,
    color_map: dict[str, str],
    *,
    dir_color: str = _DIR_COLOR,
) -> dict[str, object]:
    """Recursively convert a Node to a JSON-serialisable dict."""
    color = dir_color if node.is_dir else color_map.get(node.extension, "#888888")
    result: dict[str, object] = {
        "name": node.name,
        "path": node.path.as_posix(),
        "size": node.size,
        "display_size": _fmt_size(node.size),
        "is_dir": node.is_dir,
        "extension": node.extension,
        "color": color,
    }
    if node.is_dir:
        result["children"] = [
            node_to_dict(c, color_map, dir_color=dir_color) for c in node.children
        ]
    return result


def is_readonly_source(root: str) -> bool:
    """Return True if the source does not support write operations."""
    _READONLY_PREFIXES = (
        "github://",
        "https://github.com/",
        "http://github.com/",
        "s3://",
        "ssh://",
        "docker://",
        "pod://",
        "gdrive://",
        "hg://",
    )
    if any(root.startswith(p) for p in _READONLY_PREFIXES):
        return True
    # Archives and git refs are read-only
    try:
        from dirplot.archives import is_archive_path

        if is_archive_path(root):
            return True
    except Exception:
        pass
    try:
        from dirplot.git_scanner import is_git_ref_path

        if is_git_ref_path(root):
            return True
    except Exception:
        pass
    return False


def resolve_root_path(root: str) -> Path | None:
    """Return the local filesystem Path for root, or None if it's a remote source."""
    if is_readonly_source(root):
        return None
    p = Path(root).expanduser().resolve()
    return p if p.exists() else None
