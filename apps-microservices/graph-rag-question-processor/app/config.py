from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Exchanges and Queues
    INPUT_EXCHANGE: str = "data_exchange_questions"
    INPUT_ROUTING_KEY: str = "question.create"
    INPUT_QUEUE: str = "graph_rag_question_queue"

    # gRPC Services
    GRAPH_DATABASE_SERVICE_URL: str = "localhost:50055"

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8571

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
