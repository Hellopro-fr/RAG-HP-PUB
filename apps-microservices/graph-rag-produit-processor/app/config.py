from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Exchanges and Queues
    INPUT_EXCHANGE: str = "graph-data_graph_exchange_produits"
    INPUT_ROUTING_KEY: str = "graph-new_data.product"
    INPUT_QUEUE: str = "graph_rag_product_processing_queue"

    OUTPUT_EXCHANGE: str = "graph_rag_product_extracted"
    OUTPUT_ROUTING_KEY: str = "graph_rag.product.extracted"

    # gRPC Services
    GRAPH_DATABASE_SERVICE_URL: str = "localhost:50055"

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8560

    # Retry Configuration
    MAX_RETRIES: int = 3
    RETRY_TTL_MS: int = 30000

    # Batching Configuration
    BATCH_SIZE: int = 10
    BATCH_TIMEOUT_SECONDS: float = 2.0

    # Concurrency Control
    MAX_CONCURRENCY: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
