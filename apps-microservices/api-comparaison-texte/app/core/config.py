from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Métadonnées du service
    APP_NAME: str = "API Comparaison de Texte"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Logs : niveau, et nombre de caracteres du debut de chaque texte repris dans le resume (0 = aucun extrait)
    LOG_LEVEL: str = "INFO"
    LOG_PREVIEW_CHARS: int = 80

    # Seuil de similarité (reproduit processor.py CONDITION 2 : ratio < 0.85)
    SIMILARITY_THRESHOLD: float = 0.85

    # Taille max du batch
    BATCH_MAX_ITEMS: int = 500

    # Workers (parallélisme CPU ; GIL → ce sont les process, pas les threads)
    UVICORN_WORKERS: int = 2

    # Admission synchrone (0 = désactivé, admet toujours)
    SYNC_MAX_INFLIGHT: int = 0
    ADMISSION_RETRY_AFTER_S: int = 15


settings = Settings()
