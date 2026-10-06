from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # gRPC Server (contrat identique au service historique)
    GRPC_PORT: int = 50057
    GRPC_MAX_WORKERS: int = 50

    # REST Server (FastAPI) — consommé par matching_prix.php / scripts externes
    REST_PORT: int = 8567

    # Prometheus Metrics
    PROMETHEUS_PORT: int = 8557

    # Source du référentiel (BO v2 PHP — CRUD côté PHP)
    # Endpoint : POST {BO_V2_URL} body {etape:"normalisation", field:"referentiel", action:"get", data:{}}
    # ⚠ DOIT être identique au learner (même backend) sinon l'apprentissage est invisible.
    BO_V2_URL: str = "https://api.hellopro.fr/v2/index.php"
    HP_TOKEN: str = ""
    BO_V2_TIMEOUT_SECONDS: float = 30.0

    # Rafraîchissement périodique du référentiel en mémoire (cache TTL).
    # Le learner déclenche en plus un /admin/reload immédiat après apprentissage.
    REFERENTIEL_TTL_SECONDS: int = 300

    # Jeton d'autorisation pour POST /admin/reload (vide = endpoint ouvert en interne).
    RELOAD_AUTH_TOKEN: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
