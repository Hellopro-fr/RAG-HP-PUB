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
    ZILLIZ_URI_DEV: str
    ZILLIZ_URI: str
    ZILLIZ_PORT: str
    ZILLIZ_USER: str
    ZILLIZ_PASSWORD: str
    ZILLIZ_API_KEY: str
    RABBITMQ_URL: str
    KEY_WEBHOOK: str
    OPENAI_API_KEY: str
    OPENROUTER_API_KEY: str
    DEEPSEEK_API_KEY: str
    M_PARAMS: str
    EF_PARAMS: str
    
    ADRESSE_VM_API_RECHERCHE : str   = "http://34.34.166.5"
    PORT_API_RECHERCHE       : int   = 8500
    COLLECTION_PRODUIT_NAME  : str   = "produits_3"
    
    URL_QUERY_API_RECHERCHE  : str  = f"{ADRESSE_VM_API_RECHERCHE}:{PORT_API_RECHERCHE}/search-service/search"
    
    IS_BASE_FRS_EXISTE  : bool  = False
    
    class Config:
        env_file = ".env"

settings = Settings()
