"""
Alpha flattening (flatten_alpha) — regression test for the transparent-background
false-negative: the SAME visual encoded with different colors hidden under the
transparent pixels (white in PNG exports, black in WordPress WebP conversions)
must extract identical features. Real case: capsa-container.com
visuels-catalogue-2023-easy-bar-10.png vs .png.webp scored 35/100 (pHash
distance 34/64) with the bare convert('RGB'); 100/100 once flattened on white.
"""
import imagehash
from PIL import Image, ImageDraw

from app.core.image_processor import ImageProcessor


def _visual_rgba(under_color):
    """Same visible content (yellow box + circle on transparent bg); the fully
    transparent pixels carry under_color as their hidden RGB payload."""
    img = Image.new("RGBA", (320, 240), under_color + (0,))
    draw = ImageDraw.Draw(img)
    draw.rectangle([60, 50, 260, 190], fill=(240, 200, 20, 255))
    draw.ellipse([120, 90, 200, 150], fill=(30, 60, 200, 255))
    return img


def test_flatten_alpha_makes_features_encoder_independent():
    png_like = _visual_rgba((255, 255, 255))   # PNG export: white under alpha
    webp_like = _visual_rgba((0, 0, 0))        # WP WebP conversion: black under alpha

    # Bare convert('RGB') (old behaviour) exposes the hidden colors -> far apart.
    buggy_dist = imagehash.phash(png_like.convert("RGB")) - imagehash.phash(webp_like.convert("RGB"))
    assert buggy_dist > 10, f"le bug de reference a disparu ? dist={buggy_dist}"

    # Flattened on white -> identical features.
    fixed_dist = (imagehash.phash(ImageProcessor.flatten_alpha(png_like))
                  - imagehash.phash(ImageProcessor.flatten_alpha(webp_like)))
    assert fixed_dist == 0, f"flatten_alpha doit annuler l'ecart (dist={fixed_dist})"


def test_flatten_alpha_full_pipeline_scores_100():
    feats_a = ImageProcessor.extract_features(ImageProcessor.flatten_alpha(_visual_rgba((255, 255, 255))))
    feats_b = ImageProcessor.extract_features(ImageProcessor.flatten_alpha(_visual_rgba((0, 0, 0))))
    score, details = ImageProcessor.calculate_similarity(feats_a, feats_b)
    assert score == 100.0, f"paire identique attendue a 100, obtenu {score} ({details})"


def test_flatten_alpha_keeps_opaque_images_unchanged():
    opaque = Image.new("RGB", (64, 64), (10, 120, 240))
    out = ImageProcessor.flatten_alpha(opaque)
    assert out.mode == "RGB"
    assert list(out.getdata()) == list(opaque.getdata())


def test_flatten_alpha_handles_palette_transparency():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([16, 16, 48, 48], fill=(200, 30, 30, 255))
    pal = img.convert("P")
    pal.info["transparency"] = 0
    out = ImageProcessor.flatten_alpha(pal)
    assert out.mode == "RGB"
