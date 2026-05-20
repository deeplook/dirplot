#!/usr/bin/env bash
# Generate example images for docs/examples.md.
set -euo pipefail

CANVAS="800x400"
OUT="docs/images"

# --- highlight.png -----------------------------------------------------------
# dirplot src tree with two highlight patterns to show the feature.
dirplot map src/dirplot \
    --highlight "**/*.py@orange" \
    --highlight "src/dirplot/fonts@cyan" \
    --canvas "$CANVAS" --no-show --output "$OUT/highlight.png"

# --- diff.png ----------------------------------------------------------------
# Diff between two recent commits on the local repo.
dirplot diff .@HEAD~50 .@HEAD \
    --changed-only \
    --canvas "$CANVAS" --no-show --output "$OUT/diff.png"

# --- nologscale.png ----------------------------------------------------------
# The dirplot src without log scaling (baseline for the before/after pair).
dirplot map src/dirplot \
    --canvas "$CANVAS" --no-show --output "$OUT/nologscale.png"

# --- logscale.png ------------------------------------------------------------
# Same tree with --log-scale 4 to show how it compresses size differences.
dirplot map src/dirplot \
    --log-scale 4 \
    --canvas "$CANVAS" --no-show --output "$OUT/logscale.png"

# --- archive.png -------------------------------------------------------------
# pip wheel — a real-world archive with meaningful internal structure.
PIP_WHL=$(find .venv -name "pip-*.whl" | sort -V | tail -1)
dirplot map "$PIP_WHL" \
    --canvas "$CANVAS" --no-show --output "$OUT/archive.png"

# --- treemap.svg -------------------------------------------------------------
# Interactive SVG of the dirplot src tree — hover tooltips and CSS highlights.
dirplot map src/dirplot \
    --log-scale 4 \
    --canvas "$CANVAS" --no-show --output "$OUT/treemap.svg"
