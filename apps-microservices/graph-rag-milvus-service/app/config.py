from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Milvus Connection
    ZILLIZ_URI: str = "http://localhost:19530"
    ZILLIZ_TOKEN: str = ""

    # Collection Names
    MILVUS_ENTITY_COLLECTION: str = "graph_rag_entities"
    MILVUS_LABEL_COLLECTION: str = "graph_rag_labels"
    MILVUS_CHARACTERISTIC_COLLECTION: str = "graph_rag_characteristics"

    # Embedding Configuration
    EMBEDDING_DIMENSION: int = 1024

    # gRPC Server
    GRPC_PORT: int = 50056
    GRPC_MAX_WORKERS: int = 50

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8556

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
