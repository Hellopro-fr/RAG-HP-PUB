"""Tests TDD pour process_logo — traitement logo-safe (Chantier logo fournisseur, Task 1).

Un logo NE doit PAS être détruit :
  - SVG   : octets bruts verbatim (pas de rastérisation).
  - Raster (PNG/WEBP/GIF/JPEG) : pas de flatten fond blanc, pas de resize,
    alpha/mode conservé (passthrough des octets).
"""

import io

from PIL import Image

from core.image_processor import process_logo


# =============================================================================
# SVG
# =============================================================================

def test_svg_passthrough_bytes_identical():
    """SVG avec viewBox : octets renvoyés à l'identique, dims depuis viewBox."""
    raw = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60"><rect/></svg>'
    out = process_logo(raw, domain="acme.fr", filename="acme")

    assert out["format"] == "svg"
    assert out["extension"] == ".svg"
    assert out["bytes"] == raw            # aucun ré-encodage
    assert out["width"] == 200 and out["height"] == 60   # depuis viewBox


def test_svg_without_viewbox_dims_none():
    """SVG sans viewBox ni width/height : dimensions non déterminables → None."""
    raw = b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
    out = process_logo(raw, domain="acme.fr", filename="acme")

    assert out["format"] == "svg"
    assert out["bytes"] == raw
    assert out["width"] is None
    assert out["height"] is None


def test_svg_without_viewbox_uses_width_height_attrs():
    """SVG sans viewBox mais avec attributs width/height numériques."""
    raw = b'<svg xmlns="http://www.w3.org/2000/svg" width="150" height="45"><rect/></svg>'
    out = process_logo(raw, domain="acme.fr", filename="acme")

    assert out["format"] == "svg"
    assert out["width"] == 150 and out["height"] == 45


def test_svg_detected_via_xml_prolog():
    """SVG précédé du prolog XML (`<?xml ...?>`) est bien détecté comme SVG."""
    raw = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect/></svg>'
    )
    out = process_logo(raw, domain="acme.fr", filename="acme")

    assert out["format"] == "svg"
    assert out["bytes"] == raw
    assert out["width"] == 100 and out["height"] == 100


# =============================================================================
# Raster — PNG (alpha préservé, pas de flatten, pas de resize)
# =============================================================================

def test_png_alpha_preserved_no_flatten(transparent_png_bytes):
    """PNG transparent : mode alpha (RGBA/LA/P) conservé, pas d'aplatissement blanc."""
    out = process_logo(transparent_png_bytes, domain="acme.fr", filename="acme")

    assert out["format"] == "png"
    assert out["extension"] == ".png"

    img = Image.open(io.BytesIO(out["bytes"]))
    assert img.mode in ("RGBA", "LA", "P")  # alpha non aplati

    # Le pixel (0,0) doit rester transparent (pas de canvas blanc derrière).
    rgba = img.convert("RGBA")
    assert rgba.getpixel((0, 0))[3] == 0, "le pixel transparent source ne doit pas être aplati"


def test_png_dimensions_unchanged_no_resize(transparent_png_bytes):
    """Pas de resize : dimensions sortie == dimensions source, quelle que soit la taille."""
    src_img = Image.open(io.BytesIO(transparent_png_bytes))
    src_w, src_h = src_img.size

    out = process_logo(transparent_png_bytes, domain="acme.fr", filename="acme")

    assert out["width"] == src_w
    assert out["height"] == src_h

    out_img = Image.open(io.BytesIO(out["bytes"]))
    assert out_img.size == (src_w, src_h)


def test_png_bytes_are_passthrough(transparent_png_bytes):
    """Les octets de sortie sont strictement identiques à l'entrée (passthrough)."""
    out = process_logo(transparent_png_bytes, domain="acme.fr", filename="acme")
    assert out["bytes"] == transparent_png_bytes


# =============================================================================
# Raster — autres formats (webp, gif, jpeg)
# =============================================================================

def test_webp_format_and_extension(transparent_webp_bytes):
    out = process_logo(transparent_webp_bytes, domain="acme.fr", filename="acme")

    assert out["format"] == "webp"
    assert out["extension"] == ".webp"
    assert out["bytes"] == transparent_webp_bytes

    img = Image.open(io.BytesIO(out["bytes"]))
    assert img.mode in ("RGBA", "LA", "P")


def test_gif_format_and_extension(transparent_gif_bytes):
    out = process_logo(transparent_gif_bytes, domain="acme.fr", filename="acme")

    assert out["format"] == "gif"
    assert out["extension"] == ".gif"
    assert out["bytes"] == transparent_gif_bytes


def test_jpeg_format_and_extension_no_resize(opaque_jpeg_bytes):
    src_img = Image.open(io.BytesIO(opaque_jpeg_bytes))
    src_w, src_h = src_img.size

    out = process_logo(opaque_jpeg_bytes, domain="acme.fr", filename="acme")

    assert out["format"] == "jpg"
    assert out["extension"] == ".jpg"
    assert out["width"] == src_w and out["height"] == src_h
    assert out["bytes"] == opaque_jpeg_bytes


# =============================================================================
# Erreur — contenu non décodable
# =============================================================================

def test_undecodable_content_raises():
    """Un contenu ni SVG ni image décodable doit lever une exception claire."""
    garbage = b"this is definitely not an image nor an svg file"
    try:
        process_logo(garbage, domain="acme.fr", filename="acme")
        assert False, "une exception était attendue pour un contenu non décodable"
    except Exception:
        pass
