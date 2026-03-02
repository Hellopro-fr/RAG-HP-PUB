from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Configuration pour QC-equivalence"""
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"
    MAX_CONCURRENCY: int = 10  # Nombre de messages traités en parallèle
    
    # Batching configuration
    BATCH_SIZE: int = 10  # Nombre maximum de messages par batch
    BATCH_TIMEOUT_SECONDS: float = 10.0  # Délai d'attente max pour collecter les messages
    
    # LLM - Gemini (utilisé par ce service)
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-3-pro-preview"
    
    # API HelloPro
    # HP_TOKEN: str = "rKbzpKYtGJplusPJp/H5wcKgvnue46fsfPOowErpbIBy3Px9QLFvwWXfSQpmURUISbkVJlaJS09MI4xf/ity9dvc5f92sLyZplusDcE4yjIfdxZoEoufujINhiajmxUNFPdSMjI3M" #dev
    HP_TOKEN: str = "GQr3DiVJGPIxO9o7mp5FNHXsk8Ak4fZ8x8X/732mVcUY9kyOhvo79EpFYM9GplusZO/54dvfTKZF5YNSpFNEGiRvyYZkKplusmftUpAJXoEXq45aVVSKxjpiiMzrrToEYplusziMjI3Megal" #prod

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
