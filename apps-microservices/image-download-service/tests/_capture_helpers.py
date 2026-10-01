"""
_capture_helpers.py — Shared test utilities for capture scripts (T3 Chantier D).

This module is a test-only utility (underscore prefix = not a public module).
It is imported by both capture_process_image_fixture.py and
capture_process_image_post.py so that image factories and normalisation logic
remain in sync between the two scripts.

Keeping them here prevents silent drift: a bug fix in one script would
otherwise invalidate the diff between pre/post capture JSON files.
"""

import io
import os
from pathlib import Path

from PIL import Image


# ---------------------------------------------------------------------------
# Image factory helpers
# ---------------------------------------------------------------------------

def _rgba_transparent_corner(size=(20, 20)) -> Image.Image:
    """20x20 red image with one fully transparent pixel at (0,0)."""
    img = Image.new("RGBA", size, (255, 0, 0, 255))
    img.putpixel((0, 0), (0, 0, 0, 0))
    return img


def make_png_bytes(size=(20, 20)) -> bytes:
    buf = io.BytesIO()
    _rgba_transparent_corner(size).save(buf, "PNG")
    return buf.getvalue()


def make_jpeg_bytes(size=(20, 20)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 50, 50)).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def make_webp_bytes(size=(20, 20)) -> bytes:
    buf = io.BytesIO()
    _rgba_transparent_corner(size).save(buf, "WEBP")
    return buf.getvalue()


def make_gif_bytes(size=(20, 20)) -> bytes:
    buf = io.BytesIO()
    img = _rgba_transparent_corner(size)
    img.save(buf, "GIF", transparency=0)
    return buf.getvalue()


def make_opaque_png_bytes(size=(20, 20)) -> bytes:
    """PNG opaque (no alpha) — edge case for flatten branch."""
    buf = io.BytesIO()
    Image.new("RGB", size, (0, 128, 255)).save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Sample catalogue — shared constant so both scripts exercise identical inputs
# ---------------------------------------------------------------------------

SAMPLES = [
    ("png_transparent",  make_png_bytes,       "test.com", "42001", "produit-test", ".png"),
    ("jpeg_opaque",      make_jpeg_bytes,       "test.com", "42001", "produit-test", ".jpg"),
    ("webp_transparent", make_webp_bytes,       "test.com", "42001", "produit-test", ".webp"),
    ("gif_transparent",  make_gif_bytes,        "test.com", "42001", "produit-test", ".gif"),
    ("png_opaque",       make_opaque_png_bytes, "test.com", "42001", "produit-test", ".png"),
]


# ---------------------------------------------------------------------------
# Normalise result: strip absolute paths, keep relative basenames + metadata
# ---------------------------------------------------------------------------

def normalise_result(result: dict) -> dict:
    """
    Replace absolute filesystem paths with path basenames only.
    This makes the fixture portable across machines / container runs.
    """
    normalised = {}
    for key, value in result.items():
        if key in ("main_path", "thumb_path") and isinstance(value, str):
            # Keep only the last 5 path components to capture the sharding structure:
            # e.g. /nfs/images/test.com/produit-2/1/0/0/foo.jpg
            #   -> produit-2/1/0/0/foo.jpg  (last 5 parts: dir+3shards+filename)
            parts = Path(value).parts
            relative = os.path.join(*parts[-5:]) if len(parts) >= 5 else os.path.basename(value)
            normalised[key] = relative.replace("\\", "/")
        else:
            normalised[key] = value
    return normalised
