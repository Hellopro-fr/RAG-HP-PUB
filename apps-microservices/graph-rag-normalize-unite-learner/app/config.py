from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # RabbitMQ — manual DLQ (unités définitivement non normalisées par le retry-processor)
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672/"
    INPUT_EXCHANGE: str = "graph_rag_normalization_manual"
    INPUT_ROUTING_KEY: str = "graph_rag.normalization.manual"
    INPUT_QUEUE: str = "graph_rag_normalization_manual_dlq"

    # BO v2 (CRUD prompts + apprentissage + référentiel + llm_tracking)
    # ⚠ DOIT être identique au service dynamique (même backend) sinon apprentissage invisible.
    BO_V2_URL: str = "https://api.hellopro.fr/v2/index.php"
    HP_TOKEN: str = ""

    # Service de normalisation dynamique — Gate 1 fidèle via /admin/validate
    DYNAMIC_SERVICE_URL: str = "http://graph-rag-normalize-unite-service-dynamique:8567"
    DYNAMIC_TIMEOUT_SECONDS: float = 30.0

    # LLM DeepSeek
    DEEPSEEK_API_KEY: str = ""
    PROMPT_LEARNER_ID: str = ""        # prompt en BDD action_prompt_chatgpt
    ID_PROCESS: str = "38"

    # Batch manuel
    DEFAULT_LIMIT: int = 100           # nb de messages DLQ pris par run (paramétrable)
    MAX_LIMIT: int = 1000              # plafond dur (évite un drain massif + dépense LLM incontrôlée)
    MAX_PARALLEL: int = 5              # unités traitées en parallèle (1 seul réplica)

    # API REST (déclenchement manuel) + Prometheus
    REST_PORT: int = 8566
    PROMETHEUS_PORT: int = 8567

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
