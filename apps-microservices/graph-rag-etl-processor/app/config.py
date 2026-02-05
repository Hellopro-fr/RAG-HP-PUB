from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Exchanges and Queues
    INPUT_EXCHANGE: str = "graph_rag_final_etl"
    INPUT_ROUTING_KEY: str = "graph_rag.etl.ready"
    INPUT_QUEUE: str = "graph_rag_etl_queue"

    # gRPC Services
    GRAPH_DATABASE_SERVICE_URL: str = "localhost:50055"

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8564

    # Retry Configuration
    MAX_RETRIES: int = 3
    RETRY_TTL_MS: int = 30000

    # Batching Configuration
    BATCH_SIZE: int = 5
    BATCH_TIMEOUT_SECONDS: float = 2.0

    # Concurrency Control (number of parallel batch workers)
    MAX_CONCURRENCY: int = 3

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
