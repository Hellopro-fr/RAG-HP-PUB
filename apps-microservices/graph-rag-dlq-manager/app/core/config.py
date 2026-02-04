from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # RabbitMQ AMQP Connection
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # DLQ Queues to monitor (comma-separated list)
    DLQ_QUEUES: str = (
        "graph_rag_normalization_manual_dlq,graph_rag_llm_extraction_queue_dlq"
    )

    # DLQ Configuration (queues to manage)
    MANUAL_DLQ_QUEUE: str = "graph_rag_normalization_manual_dlq"
    MANUAL_DLQ_EXCHANGE: str = "graph_rag_normalization_manual"
    MANUAL_DLQ_ROUTING_KEY: str = "graph_rag.normalization.manual"

    # Retry Queue (target for requeuing)
    RETRY_QUEUE: str = "graph_rag_normalization_retry_queue"
    RETRY_EXCHANGE: str = "graph_rag_normalization_retry"
    RETRY_ROUTING_KEY: str = "graph_rag.normalization.retry"

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8520

    class Config:
        env_file = ".env"
        case_sensitive = True

    def get_dlq_queue_list(self) -> List[str]:
        """Get list of DLQ queues to monitor."""
        return [q.strip() for q in self.DLQ_QUEUES.split(",") if q.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
