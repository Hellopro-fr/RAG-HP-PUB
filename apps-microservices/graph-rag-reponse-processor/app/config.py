from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Exchanges and Queues
    INPUT_EXCHANGE: str = "data_exchange_reponses"
    INPUT_ROUTING_KEY: str = "reponse.create"
    INPUT_QUEUE: str = "graph_rag_reponse_queue"

    # gRPC Services
    GRAPH_DATABASE_SERVICE_URL: str = "localhost:50055"

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8572

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
