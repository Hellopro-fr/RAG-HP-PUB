"""Shared test fixtures.

Since the migration to the shared common_utils Redis pool, main.py's lifespan
eagerly connects to Redis (init_redis_pool reads REDIS_URL from the process
env). Tests that run the lifespan (TestClient context managers) must never
touch a real Redis — strip the env var and the settings value so
init_redis_pool degrades to a no-op (redis_client stays None) and the
reconnect loop never dials out.
"""
import pytest

from app.core.config import settings

# langdetect est non déterministe sans seed — avec fastText absent du venv,
# le fallback langdetect+langid rend les verdicts NLP flaky sur les textes
# de test (échecs dépendant de l'ordre). Seed fixe = résultats reproductibles.
try:
    from langdetect import DetectorFactory
    DetectorFactory.seed = 0
except ImportError:
    pass


@pytest.fixture(autouse=True)
def _no_real_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(settings, "REDIS_URL", None, raising=False)
