from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASS: str
    MYSQL_DB: str

    HELLOPRO_AUTH_URL: HttpUrl
    HELLOPRO_AUTH_TIMEOUT_SECONDS: float = 5.0

    JWT_KEY_ENCRYPTION_KEY: str = Field(min_length=32)
    JWT_ISSUER: str = "https://account.hellopro.eu"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    AUTH_CODE_EXPIRE_SECONDS: int = 60

    GATEWAY_ADMIN_KEY: str

    LOG_LEVEL: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"mysql://{self.MYSQL_USER}:{self.MYSQL_PASS}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
