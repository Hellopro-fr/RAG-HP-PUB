from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # gRPC Server
    GRPC_PORT: int = 50057
    GRPC_MAX_WORKERS: int = 50

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8557

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
