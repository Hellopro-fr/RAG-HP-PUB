import os
from pydantic_settings import BaseSettings
# from typing import Dict, List

class Settings(BaseSettings):
    # PROJECT_NAME: str = "API-HP-RAG"
    # PROJECT_VERSION: str = "0.0.1"

    QDRANT_URL: str = ""
    QDRANT_HOST_URL: str
    QDRANT_PORT: str
    QDRANT_API_KEY: str
    ZILLIZ_URI: str
    ZILLIZ_PORT: str
    ZILLIZ_API_KEY: str
    RABBITMQ_URL: str
    KEY_WEBHOOK: str
    # OPENAI_API_KEY: str
    # OPENROUTER_API_KEY: str
    # DEEPSEEK_API_KEY: str
    M_PARAMS: str
    EF_PARAMS: str
    
    SEUIL_SCORE_DOUBLON: float = 0.75
    ADRESSE_VM         : str   = "http://34.90.162.9"
    PORT_API_RECHERCHE : int   = 8510
    
    class Config:
        env_file = ".env"

settings = Settings()
