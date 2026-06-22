from app.core.config import settings


def test_existing_defaults_unchanged():
    assert settings.SIMILARITY_THRESHOLD == 0.85
    assert settings.BATCH_MAX_ITEMS == 500
    assert settings.APP_NAME == "API Comparaison de Texte"


def test_new_defaults():
    assert settings.UVICORN_WORKERS == 2
    assert settings.SYNC_MAX_INFLIGHT == 0
    assert settings.ADMISSION_RETRY_AFTER_S == 15
