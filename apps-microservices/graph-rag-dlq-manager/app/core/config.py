from pydantic_settings import BaseSettings
from functools import lru_cache
from urllib.parse import urlparse


class Settings(BaseSettings):
    # RabbitMQ AMQP Connection
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # RabbitMQ Management API (will be derived from RABBITMQ_URL if not set)
    RABBITMQ_API_URL: str = ""
    RABBITMQ_API_USER: str = ""
    RABBITMQ_API_PASSWORD: str = ""
    RABBITMQ_VHOST: str = ""

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

    def get_api_url(self) -> str:
        """Derive Management API URL from RABBITMQ_URL if not explicitly set."""
        if self.RABBITMQ_API_URL:
            return self.RABBITMQ_API_URL
        parsed = urlparse(self.RABBITMQ_URL)
        # CloudAMQP uses HTTPS on the same host
        return f"https://{parsed.hostname}/api"

    def get_api_user(self) -> str:
        """Get API user from RABBITMQ_URL if not explicitly set."""
        if self.RABBITMQ_API_USER:
            return self.RABBITMQ_API_USER
        parsed = urlparse(self.RABBITMQ_URL)
        return parsed.username or ""

    def get_api_password(self) -> str:
        """Get API password from RABBITMQ_URL if not explicitly set."""
        if self.RABBITMQ_API_PASSWORD:
            return self.RABBITMQ_API_PASSWORD
        parsed = urlparse(self.RABBITMQ_URL)
        return parsed.password or ""

    def get_vhost(self) -> str:
        """Get vhost from RABBITMQ_URL if not explicitly set."""
        if self.RABBITMQ_VHOST:
            return self.RABBITMQ_VHOST
        parsed = urlparse(self.RABBITMQ_URL)
        # For CloudAMQP, vhost is the path (without leading /)
        vhost = parsed.path.lstrip("/")
        return vhost if vhost else "/"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
