from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    GRPC_PORT: int = 50059
    GRPC_MAX_WORKERS: int = 10
    HTTP_PORT: int = 8571

    MYSQL_HOST: str = "mysql"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "normalization_user"
    MYSQL_PASSWORD: str = Field(min_length=1)
    MYSQL_DB: str = "normalization_db"

    RABBITMQ_URL: str = Field(min_length=1)
    UNITS_EXCHANGE: str = "normalization.units"
    UNITS_ADMIN_KEY: str = Field(min_length=16)
    RELAY_POLL_SECONDS: float = 1.0

    @property
    def database_url(self) -> URL:
        return URL.create("mysql+pymysql", username=self.MYSQL_USER, password=self.MYSQL_PASSWORD,
                          host=self.MYSQL_HOST, port=self.MYSQL_PORT, database=self.MYSQL_DB,
                          query={"charset": "utf8mb4"})
