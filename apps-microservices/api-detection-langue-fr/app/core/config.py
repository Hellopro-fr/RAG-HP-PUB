import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Configuration de l'application"""
    
    # Server
    APP_NAME: str = "API Détection Langue Française"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # HTTP Client
    HTTP_TIMEOUT: int = 30  # secondes
    HTTP_MAX_RETRIES: int = 3
    HTTP_RETRY_DELAY: float = 1.0  # secondes
    
    # NLP Detection
    NLP_MIN_CONFIDENCE: float = 0.75  # Réduit de 0.85 pour accepter le FR avec termes techniques EN
    NLP_MIN_TEXT_LENGTH: int = 100  # Réduit de 200 pour accepter les pages minimalistes
    
    # Batch Processing
    BATCH_MAX_URLS: int = 100
    BATCH_DEFAULT_CONCURRENCY: int = 10
    BATCH_MAX_CONCURRENCY: int = 50
    
    # Proxy (optionnel)
    DEFAULT_PROXY_URL: Optional[str] = None
    
    # Pemavor API (fallback pour redirections)
    PEMAVOR_API_URL: Optional[str] = "https://europe-west1-pemavor-free-tools.cloudfunctions.net/HttpStatusCodeChecker"
    PEMAVOR_API_KEY: Optional[str] = None
    
    # User-Agent
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
