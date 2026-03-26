from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Configuration pour prix-traitement"""

    # Project
    PROJECT_NAME: str = "prix-traitement"
    PROJECT_VERSION: str = "0.0.1"

    # LLM - Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-3.1-flash-lite-preview"

    # API HelloPro
    HP_TOKEN: str

    # Prompt par défaut pour l'identification des caractéristiques
    PROMPT_ID_CARAC_PRIX: str = "113"

    # Prompt par défaut pour le questionnaire prix (RAG + LLM)
    PROMPT_ID_QUESTIONNAIRE: str = "114"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
