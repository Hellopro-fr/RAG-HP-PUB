"""Configuration d'agent-service (variables d'environnement ou .env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    PROJECT_NAME: str = "agent-service"
    PROJECT_VERSION: str = "0.1.0"

    # API v2 PHP : fiches et journal (le service n'accède jamais à MySQL)
    HELLOPRO_API_URL: str = "https://api.hellopro.fr/v2/index.php"
    HP_TOKEN: str = ""

    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # Gateway MCP HelloPro : appelée par les fournisseurs ; le service n'appelle que /token
    MCP_GATEWAY_URL: str = ""
    MCP_CLIENT_ID: str = ""
    MCP_CLIENT_SECRET: str = ""

    TIMEOUT_MODELE_S: int = 300
    TTL_CACHE_FICHE_S: int = 60
    MAX_TOKENS_DEFAUT: int = 4096


@lru_cache()
def get_settings() -> Settings:
    return Settings()
