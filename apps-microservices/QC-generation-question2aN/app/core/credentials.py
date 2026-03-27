from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Configuration pour QC-generation-question2aN"""
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"
    MAX_CONCURRENCY: int = 10  # Nombre de messages traités en parallèle
    
    # Batching configuration
    BATCH_SIZE: int = 10  # Nombre maximum de messages par batch
    BATCH_TIMEOUT_SECONDS: float = 10.0  # Délai d'attente max pour collecter les messages
    
    # LLM - Gemini (utilisé par ce service)
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-3.1-pro-preview"
    
    # API HelloPro
    HP_TOKEN: str

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
