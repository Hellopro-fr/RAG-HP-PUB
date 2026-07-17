from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Métadonnées du service
    APP_NAME: str = "API Comparaison de Texte"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Seuil de similarité (reproduit processor.py CONDITION 2 : ratio < 0.85)
    SIMILARITY_THRESHOLD: float = 0.85

    # Taille max du batch
    BATCH_MAX_ITEMS: int = 500


settings = Settings()
