from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # API Config
    API_PORT: int = 8000
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Neo4j Direct Connection (for execute_cypher_direct)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    NEO4J_DATABASE: str = "neo4j"

    # gRPC Services
    EMBEDDING_SERVICE_URL: str = "localhost:50052"
    MILVUS_SERVICE_URL: str = "localhost:50056"
    GRAPH_DATABASE_SERVICE_URL: str = "localhost:50055"
    NORMALIZATION_SERVICE_URL: str = "localhost:50057"
    SPACY_SERVICE_URL: str = "localhost:50058"
    LLM_SERVICE_URL: str = "localhost:50051"
    RERANKING_SERVICE_URL: str = "localhost:50053"

    # LLM Config
    LLM_PROVIDER: str = "gemini"  # 'openai', 'gemini', 'anthropic'
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_MODEL_NAME: str = "gemini-1.5-pro"

    # RAG Config
    SIMILARITY_THRESHOLD: float = 0.75
    TOP_K_RETRIEVAL: int = 10

    # HelloPro API
    HELLOPRO_API_BEARER_TOKEN: str = ""

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8565

    # Debug
    DEBUG_SCORING: bool = True  # TEMP: active les logs detailles de scoring V2 (a remettre a False apres diagnostic)

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
