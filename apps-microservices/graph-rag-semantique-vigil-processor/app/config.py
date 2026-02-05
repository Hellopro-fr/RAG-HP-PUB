from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Exchanges and Queues
    INPUT_EXCHANGE: str = "graph_rag_semantic_check"
    INPUT_ROUTING_KEY: str = "graph_rag.semantic.check"
    INPUT_QUEUE: str = "graph_rag_semantic_vigil_queue"

    OUTPUT_EXCHANGE: str = "graph_rag_final_etl"
    OUTPUT_ROUTING_KEY: str = "graph_rag.etl.ready"

    # gRPC Services
    EMBEDDING_SERVICE_URL: str = "localhost:50051"
    MILVUS_SERVICE_URL: str = "localhost:50056"

    # HTTP Embedding Service (Temporary)
    EMBEDDING_API_URL: str = ""
    EMBEDDING_API_KEY: str = ""

    # Semantic Configuration
    SIMILARITY_THRESHOLD: float = 0.90

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8563

    # Retry Configuration
    MAX_RETRIES: int = 3
    RETRY_TTL_MS: int = 30000

    # Batching Configuration
    BATCH_SIZE: int = 10
    BATCH_TIMEOUT_SECONDS: float = 2.0

    # Concurrency Control
    MAX_CONCURRENCY: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
