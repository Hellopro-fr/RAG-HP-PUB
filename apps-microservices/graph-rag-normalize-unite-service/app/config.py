from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # gRPC Server
    GRPC_PORT: int = 50057
    GRPC_MAX_WORKERS: int = 50

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8557

    # Live unit updates (empty RABBITMQ_URL = serve the frozen fallback tables only)
    RABBITMQ_URL: str = ""
    UNITS_EXCHANGE: str = "normalization.units"
    UNIT_REGISTRY_GRPC_ADDR: str = "unit-registry-service:50059"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
