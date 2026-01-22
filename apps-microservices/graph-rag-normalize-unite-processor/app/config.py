from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Exchanges and Queues
    INPUT_EXCHANGE: str = "graph_rag_normalization"
    INPUT_ROUTING_KEY: str = "graph_rag.normalization.pending"
    INPUT_QUEUE: str = "graph_rag_normalization_queue"

    OUTPUT_EXCHANGE: str = "graph_rag_semantic_check"
    OUTPUT_ROUTING_KEY: str = "graph_rag.semantic.check"

    # gRPC Services
    NORMALIZATION_SERVICE_URL: str = "localhost:50057"

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8562

    # Retry Configuration
    MAX_RETRIES: int = 3
    RETRY_TTL_MS: int = 30000

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
