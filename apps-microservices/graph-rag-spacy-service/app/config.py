from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # API Config
    # Port 8569 reserved for this service metrics? or use standard range
    # Let's use 50058 for gRPC
    GRPC_PORT: int = 50058

    # NLP Model
    SPACY_MODEL: str = "fr_core_news_sm"

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8569

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
