from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Configuration pour prix-extraction-devis"""

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"
    MAX_CONCURRENCY: int = 10  # Nombre de messages traités en parallèle

    # LLM Provider selection - "gemini" ou "deepseek"
    LLM_PROVIDER: str = "gemini"

    # LLM - Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-3.1-pro-preview"

    # LLM - DeepSeek
    DEEPSEEK_API_KEY: str = ""

    # Prompt statique - Devis
    PROMPT_ID: str = "119"

    MILVUS_SOURCE: str = "pjechanges"  # Collection source dans Milvus
    MILVUS_PAGE_TYPE: str = "devis"
    MILVUS_TYPE: int = 1 # type de recherche vectorielle
    MILVUS_ACTION: int = 2 # utilisation LLM
    MILVUS_TOP_K: int = 1000

    # API HelloPro
    HP_TOKEN: str

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
