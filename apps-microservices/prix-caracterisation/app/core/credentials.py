from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Configuration pour prix-caracterisation (LLM DeepSeek)"""

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"
    MAX_CONCURRENCY: int = 5  # Catégories traitées simultanément par réplica

    # LLM - DeepSeek
    DEEPSEEK_API_KEY: str = ""

    # Prompts (action_prompt_chatgpt) — MÊMES prompts que QC-caracterisation
    # On réutilise 100 (caractérisation) et 103 (repasse) inchangés.
    # Les infos prix Milvus (valeur_prix, caracteristique, prix_original, ...)
    # sont injectées dans {DESCRIPTIF_CATEGORIE} au moment de l'appel LLM.
    PROMPT_CARACTERISATION_ID: str = "100"
    PROMPT_REPASSE_ID: str = "103"

    # API HelloPro (backend BO v2)
    HP_TOKEN: str

    # Milvus : accès direct via pymilvus (via common_utils.database.config.Configuration
    # qui lit ZILLIZ_URI / ZILLIZ_PORT / ZILLIZ_USER / ZILLIZ_PASSWORD dans l'environnement).
    # Pas d'URL HTTP : on tape Milvus directement.
    MILVUS_PAGE_SIZE: int = 1000

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
