"""Startup smoke: each entry import must work in a fresh interpreter, whatever the import order."""
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", ["app.main", "application", "infrastructure"])
def test_module_imports_in_a_fresh_interpreter(module):
    result = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=SERVICE_DIR,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
