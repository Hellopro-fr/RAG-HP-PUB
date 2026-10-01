"""pytest conftest : force dummy env pour les tests offline."""
import os

# Doit etre set AVANT l'import de app.core.credentials
os.environ.setdefault("ZILLIZ_URI", "dummy")
os.environ.setdefault("ZILLIZ_USER", "dummy")
os.environ.setdefault("ZILLIZ_PASSWORD", "dummy")
os.environ.setdefault("TYPESENSE_API_KEY", "dummy")
