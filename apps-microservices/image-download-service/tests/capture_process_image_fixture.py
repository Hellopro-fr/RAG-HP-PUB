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

import json
import sys
import tempfile
from pathlib import Path

# Ensure the app/ directory is on the Python path (mirrors pytest.ini pythonpath=app)
APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from core.image_processor import ImageProcessor
from core.downloader import _build_filename

# I2: Shared image factories and normalisation — imported from _capture_helpers so
# both capture scripts stay in sync (prevents silent drift between pre/post captures).
from _capture_helpers import SAMPLES, normalise_result  # noqa: E402

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
