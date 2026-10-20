"""Tests for optional raster image encoders."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from dirplot.image_formats import encode_jxl


def test_encode_jxl_round_trip() -> None:
    pytest.importorskip("pillow_jxl")

    source = BytesIO()
    Image.new("RGB", (3, 2), (12, 34, 56)).save(source, format="PNG")

    result = encode_jxl(source)

    with Image.open(result) as decoded:
        assert decoded.format == "JXL"
        assert decoded.size == (3, 2)
        assert decoded.convert("RGB").getpixel((0, 0)) == (12, 34, 56)
