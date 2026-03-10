from importlib.metadata import version

from dirplot.display import display_inline, display_window
from dirplot.render import create_treemap
from dirplot.scanner import apply_log_sizes, build_tree
from dirplot.svg_render import create_treemap_svg

__version__ = version("dirplot")

__all__ = [
    "build_tree",
    "apply_log_sizes",
    "create_treemap",
    "create_treemap_svg",
    "display_inline",
    "display_window",
]
