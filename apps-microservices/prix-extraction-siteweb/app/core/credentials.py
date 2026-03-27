from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Configuration pour prix-extraction-siteweb"""
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"
    MAX_CONCURRENCY: int = 10  # Nombre de messages traités en parallèle
    
    # Milvus RAG Search
    MILVUS_SOURCE: str = "siteweb_2"  # Collection source dans Milvus
    MILVUS_TOP_K: int = 30  # Nombre de résultats à récupérer
    
    # LLM Provider selection - "gemini" ou "deepseek"
    LLM_PROVIDER: str = "gemini"
    
    # LLM - Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-3.1-pro-preview"
    # GEMINI_MODEL_NAME: str = "gemini-3.1-flash-lite-preview"
    
    # LLM - DeepSeek
    DEEPSEEK_API_KEY: str = ""
    
    # Prompt statique - Briefing Prix - Prompt extraction prix SiteWeb
    PROMPT_ID: str = "117"
    
    # API HelloPro
    HP_TOKEN: str

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
