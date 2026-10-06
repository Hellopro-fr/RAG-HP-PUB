"""Place la racine du service sur sys.path pour que les tests importent
`infrastructure`, `application` et `scripts` comme en runtime (PYTHONPATH=/app)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
