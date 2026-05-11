"""CLI entry point."""

# ruff: noqa: F401
# Import command modules so their @app.command decorators register against the app.
import dirplot.commands.diff
import dirplot.commands.metrics
import dirplot.commands.misc
import dirplot.commands.replay
import dirplot.commands.treemap
import dirplot.commands.vcs
import dirplot.commands.watch
from dirplot._overview import add_overview_command
from dirplot.app import app as app

add_overview_command(app)

# Reorder help output regardless of definition order.
_CMD_ORDER = [
    "demo",
    "overview",
    "termsize",
    "map",
    "diff",
    "metrics",
    "git",
    "hg",
    "watch",
    "replay",
    "read-meta",
]
app.registered_commands.sort(key=lambda c: _CMD_ORDER.index(c.name or ""))
