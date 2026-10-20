"""Helpers for optional raster output formats."""

from __future__ import annotations

import io


def encode_jxl(png: io.BytesIO) -> io.BytesIO:
    """Encode a rendered PNG buffer as JPEG XL using the optional Pillow plugin."""
    try:
        import pillow_jxl  # noqa: F401  # Registers JXL with Pillow.
    except ImportError:
        raise RuntimeError(
            "JPEG XL output requires an optional dependency. Install it with: "
            "pip install 'dirplot[jxl]'"
        ) from None

    from PIL import Image

    png.seek(0)
    with Image.open(png) as image:
        result = io.BytesIO()
        image.save(result, format="JXL", lossless=True)
    result.seek(0)
    return result
