from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration du service QC-fabricant-reference (etape PSI 16)."""

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"
    MAX_CONCURRENCY: int = 4  # messages (categories) traites en parallele

    # Decoupage du travail
    BATCH_PRODUITS: int = 10      # produits par appel LLM (prompt ~2 900 tokens amortis)
    APPELS_PARALLELES: int = 4    # appels LLM simultanes par categorie
    MAX_ECHECS_BATCH: int = 5     # echecs consecutifs avant abandon du run

    # LLM - DeepSeek
    DEEPSEEK_API_KEY: str
    DEEPSEEK_MODEL_NAME: str = "deepseek-v4-flash"
    DEEPSEEK_API_URL: str = "https://api.deepseek.com"

    # API HelloPro
    HP_API_URL: str = "https://api.hellopro.fr/v2/index.php"
    HP_TOKEN: str
    HP_TIMEOUT_SECONDS: int = 300

    # Prompt d'extraction marque / reference (table action_prompt_chatgpt)
    PROMPT_EXTRACTION_ID: str = "133"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
