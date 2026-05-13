"""
capture_process_image_fixture.py — Pre-refactor regression capture script (T3 Chantier D).

PURPOSE
-------
Run this script BEFORE applying the _process_image_internal refactor, inside the
image-download-service Docker container (where PIL and pyvips are installed).

It calls ImageProcessor().process_image() with 5 deterministic image inputs and
dumps the returned dict — minus volatile absolute filesystem paths — to
tests/fixtures/sample_process_image_pre.json.

After the refactor, run capture_process_image_post.py and diff the two JSON files:

    diff tests/fixtures/sample_process_image_pre.json \
         tests/fixtures/sample_process_image_post.json

No diff → refactor is safe and output-identical.

USAGE (inside container)
------------------------
    cd /app
    python tests/capture_process_image_fixture.py

OUTPUT
------
    tests/fixtures/sample_process_image_pre.json
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
# Image factory helpers — identical to conftest.py factories so results are
# deterministic and reproducible without real image files on disk.
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
            # Keep only the last two components: parent-dir-name/filename
            # e.g. /nfs/images/test.com/produit-2/1/0/0/foo.jpg
            #   → produit-2/.../foo.jpg  (last path segment of parent + filename)
            parts = Path(value).parts
            # Reconstruct as: .../{produit-2 or produit-3}/{rep1}/{rep2}/{rep3}/{filename}
            # We take the last 5 components to capture the sharding structure
            relative = os.path.join(*parts[-5:]) if len(parts) >= 5 else os.path.basename(value)
            normalised[key] = relative.replace("\\", "/")
        else:
            normalised[key] = value
    return normalised


# ---------------------------------------------------------------------------
# Main capture
# ---------------------------------------------------------------------------

SAMPLES = [
    ("png_transparent",  make_png_bytes,       "test.com", "42001", "produit-test", ".png"),
    ("jpeg_opaque",      make_jpeg_bytes,       "test.com", "42001", "produit-test", ".jpg"),
    ("webp_transparent", make_webp_bytes,       "test.com", "42001", "produit-test", ".webp"),
    ("gif_transparent",  make_gif_bytes,        "test.com", "42001", "produit-test", ".gif"),
    ("png_opaque",       make_opaque_png_bytes, "test.com", "42001", "produit-test", ".png"),
]

STUB_URL = "https://stub.example.com/image"

OUTPUT_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_process_image_pre.json"


def main():
    processor = ImageProcessor()
    results = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        for label, factory, domain, product_id, product_name, ext in SAMPLES:
            print(f"[capture] Processing sample: {label} ...", end=" ")
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
    print(f"\n[capture] Written: {OUTPUT_PATH}")
    print("[capture] Run capture_process_image_post.py after the refactor, then diff the two files.")


if __name__ == "__main__":
    main()
