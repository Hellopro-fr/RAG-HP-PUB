import pathlib
import sys

SERVICE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

import app  # noqa: E402

# The Docker image copies app/ to /app/website_processor_service; alias the
# package so production imports resolve when running tests from the repo.
sys.modules.setdefault("website_processor_service", app)
