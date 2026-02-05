from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"

    # Exchanges and Queues
    INPUT_EXCHANGE: str = "graph_rag_product_extracted"
    INPUT_ROUTING_KEY: str = "graph_rag.product.extracted"
    INPUT_QUEUE: str = "graph_rag_llm_extraction_queue"

    OUTPUT_EXCHANGE: str = "graph_rag_normalization"
    OUTPUT_ROUTING_KEY: str = "graph_rag.normalization.pending"

    # LLM Configuration
    LLM_PROVIDER: str = "deepseek"  # openai, gemini, anthropic
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"

    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 8192

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8561

    # Retry Configuration
    MAX_RETRIES: int = 3
    RETRY_TTL_MS: int = 30000

    # Concurrency Control
    # Controls how many LLM requests can run in parallel per container
    MAX_CONCURRENCY: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
