from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Exchanges and Queues
    # Assuming input comes from the same exchange as products (data_exchange_produits?) or a dedicated one.
    # In api-ingestion (implied), it likely publishes to specific exchanges per collection.
    # Let's assume standardized exchange/queue names.
    INPUT_EXCHANGE: str = "data_exchange_categories"
    INPUT_ROUTING_KEY: str = "new_data.categories"
    INPUT_QUEUE: str = "graph_rag_categorie_queue"

    # gRPC Services
    GRAPH_DATABASE_SERVICE_URL: str = "localhost:50055"

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8570

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
