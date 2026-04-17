"""Pytest configuration and fixtures."""
import sys
from pathlib import Path

# Add the monorepo's root and libs to Python path
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root / "libs"))
sys.path.insert(0, str(repo_root))
