from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Input Queue (Retry DLQ from normalize-unite-processor)
    INPUT_EXCHANGE: str = "graph_rag_normalization_retry"
    INPUT_ROUTING_KEY: str = "graph_rag.normalization.retry"
    INPUT_QUEUE: str = "graph_rag_normalization_retry_queue"

    # Manual DLQ for permanently failed normalizations
    MANUAL_DLQ_EXCHANGE: str = "graph_rag_normalization_manual"
    MANUAL_DLQ_ROUTING_KEY: str = "graph_rag.normalization.manual"
    MANUAL_DLQ_QUEUE: str = "graph_rag_normalization_manual_dlq"

    # gRPC Services
    NORMALIZATION_SERVICE_URL: str = "localhost:50057"
    MILVUS_SERVICE_URL: str = "localhost:50056"
    GRAPH_DATABASE_SERVICE_URL: str = "localhost:50055"

    # HTTP Embedding Service (same as semantic-vigil-processor)
    EMBEDDING_API_URL: str = ""
    EMBEDDING_API_KEY: str = ""

    # Semantic Configuration
    SIMILARITY_THRESHOLD: float = 0.90

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8564

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
