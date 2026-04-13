from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Content Extractor API"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8600
    LOG_LEVEL: str = "info"
    MAX_PAYLOAD_SIZE_MB: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
