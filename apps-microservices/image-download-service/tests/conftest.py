"""Shared fixtures for image-download-service tests."""

import io
from pathlib import Path

import pytest
from PIL import Image


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "images"


# =============================================================================
# Helpers de génération d'images in-memory
# =============================================================================

def _rgba_with_transparent_corner(size=(10, 10)):
    """Base : rouge uni avec pixel (0,0) totalement transparent."""
    img = Image.new("RGBA", size, (255, 0, 0, 255))
    img.putpixel((0, 0), (0, 0, 0, 0))
    return img


def make_transparent_png(size=(10, 10)) -> bytes:
    """PNG 10×10 rouge avec pixel (0,0) totalement transparent."""
    buf = io.BytesIO()
    _rgba_with_transparent_corner(size).save(buf, "PNG")
    return buf.getvalue()


def make_transparent_webp(size=(10, 10)) -> bytes:
    """WebP 10×10 rouge avec pixel (0,0) totalement transparent."""
    buf = io.BytesIO()
    _rgba_with_transparent_corner(size).save(buf, "WEBP")
    return buf.getvalue()


def make_transparent_gif(size=(10, 10)) -> bytes:
    """GIF 10×10 avec pixel (0,0) transparent via info['transparency']."""
    img = _rgba_with_transparent_corner(size)
    buf = io.BytesIO()
    # Pillow convertit RGBA → P automatiquement ; `transparency=0` pose
    # l'index de la couleur transparente dans la palette GIF.
    img.save(buf, "GIF", transparency=0)
    return buf.getvalue()


def make_opaque_jpeg(size=(10, 10), color=(255, 0, 0)) -> bytes:
    """JPEG 10×10 couleur unie (par défaut rouge)."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


# =============================================================================
# Fixtures pytest (exposées aux tests)
# =============================================================================

@pytest.fixture
def transparent_png_bytes():
    return make_transparent_png()


@pytest.fixture
def transparent_webp_bytes():
    return make_transparent_webp()


@pytest.fixture
def transparent_gif_bytes():
    return make_transparent_gif()


@pytest.fixture
def opaque_jpeg_bytes():
    return make_opaque_jpeg()
