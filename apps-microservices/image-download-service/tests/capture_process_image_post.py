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
