"""Pytest conftest for tools/ tests.

Adds the tools/ directory to sys.path so tests can import modules like
`import gcs_archive_audit` directly (same pattern as running the scripts
with `python tools/gcs_archive_audit.py`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
