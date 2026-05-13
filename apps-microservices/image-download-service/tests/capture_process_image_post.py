"""
capture_process_image_post.py — Post-refactor regression capture script (T3 Chantier D).

PURPOSE
-------
Run this script AFTER applying the _process_image_internal refactor, inside the
image-download-service Docker container (where PIL and pyvips are installed).

It calls ImageProcessor().process_image() with the same 5 deterministic inputs
as capture_process_image_fixture.py and dumps the returned dict to
tests/fixtures/sample_process_image_post.json.

Then diff both files:

    diff tests/fixtures/sample_process_image_pre.json \
         tests/fixtures/sample_process_image_post.json

No diff → refactor is safe and output-identical.

USAGE (inside container)
------------------------
    cd /app
    python tests/capture_process_image_post.py

OUTPUT
------
    tests/fixtures/sample_process_image_post.json
"""

import io
import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure the app/ directory is on the Python path (mirrors pytest.ini pythonpath=app)
APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PIL import Image
from core.image_processor import ImageProcessor
from core.downloader import _build_filename

# ---------------------------------------------------------------------------
# Image factory helpers — identical to capture_process_image_fixture.py
# ---------------------------------------------------------------------------

def _rgba_transparent_corner(size=(20, 20)) -> Image.Image:
    """20×20 red image with one fully transparent pixel at (0,0)."""
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
            parts = Path(value).parts
            relative = os.path.join(*parts[-5:]) if len(parts) >= 5 else os.path.basename(value)
            normalised[key] = relative.replace("\\", "/")
        else:
            normalised[key] = value
    return normalised


# ---------------------------------------------------------------------------
# Main capture — identical logic to pre-capture, only output filename differs
# ---------------------------------------------------------------------------

SAMPLES = [
    ("png_transparent",  make_png_bytes,       "test.com", "42001", "produit-test", ".png"),
    ("jpeg_opaque",      make_jpeg_bytes,       "test.com", "42001", "produit-test", ".jpg"),
    ("webp_transparent", make_webp_bytes,       "test.com", "42001", "produit-test", ".webp"),
    ("gif_transparent",  make_gif_bytes,        "test.com", "42001", "produit-test", ".gif"),
    ("png_opaque",       make_opaque_png_bytes, "test.com", "42001", "produit-test", ".png"),
]

STUB_URL = "https://stub.example.com/image"

# NOTE: output filename is _post.json (differs from the pre-capture script)
OUTPUT_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_process_image_post.json"


def main():
    processor = ImageProcessor()
    results = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        for label, factory, domain, product_id, product_name, ext in SAMPLES:
            print(f"[capture-post] Processing sample: {label} ...", end=" ")
            content = factory()
            filename = _build_filename(product_name, product_id, STUB_URL, ext)

            result = processor.process_image(
                content=content,
                domain=domain,
                product_id=product_id,
                product_name=product_name,
                base_storage_dir=tmp_dir,
                filename=filename,
            )

            results[label] = normalise_result(result)
            print(f"OK  width={results[label].get('width')}  height={results[label].get('height')}  format={results[label].get('format')}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"\n[capture-post] Written: {OUTPUT_PATH}")
    print("[capture-post] Now diff against the pre-capture:")
    print(f"    diff {OUTPUT_PATH.parent / 'sample_process_image_pre.json'} {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
