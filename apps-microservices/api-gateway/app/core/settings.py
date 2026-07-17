from dataclasses import dataclass
import os
from typing import Dict, Type
from dotenv import load_dotenv
from pathlib import Path

# Load default .env
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)

# Load extra .env if exists
extra_env_path = Path(".") / ".env.url"
if extra_env_path.exists():
    load_dotenv(dotenv_path=extra_env_path, override=True)


@dataclass(frozen=True)
class Service:
    """Represents a microservice with its URL and the API path to access it."""

    url: str
    api_path: str


class Configuration:
    PROJECT_NAME: str = "API-HP-RAG"
    PROJECT_VERSION: str = "0.0.1"

    # ─── Auth configuration ────────────────────────────────────────────────
    JWT_SECRET: str = os.getenv("JWT_SECRET", "changeme-jwt-secret")
    JWT_ALGO: str = os.getenv("JWT_ALGO", "HS256")
    JWT_AUDIENCE: str = os.getenv("JWT_AUDIENCE", "hellopro")

    # ─── Token security configuration ────────────────────────────────────
    GATEWAY_ADMIN_KEY: str = os.getenv("GATEWAY_ADMIN_KEY", "changeme-admin-key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    )

    # ─── MySQL (Gateway DB) configuration ─────────────────────────────────
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "gateway-mysql")
    MYSQL_PORT: str = os.getenv("MYSQL_PORT", "3306")
    MYSQL_USER: str = os.getenv("MYSQL_USER", "gateway_user")
    MYSQL_PASS: str = os.getenv("MYSQL_PASS", "gateway_pass")
    MYSQL_DB: str = os.getenv("MYSQL_DB", "gateway_db")

    DOCUMENT_ROOT: str = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )

    # Dynamically add services based on environment keys
    EXTRA_SERVICES: Dict[str, Service] = {}

    for key, value in os.environ.items():
        # convention: SERVICE_<NAME>=http://url  --> api_path="/<name>-service"
        if key.startswith("SERVICE_"):
            service_name = key[len("SERVICE_") :].lower()
            EXTRA_SERVICES[service_name] = Service(
                url=value, api_path=f"/{service_name}-service"
            )

    # ─── Excluded routes (bypass token verification) ──────────────────────
    # Convention: EXCLUDED_ROUTES_<SERVICE>=path1,path2,...
    # Example:    EXCLUDED_ROUTES_DLQ=dlq/queues,dlq/health
    # Paths are relative (no leading slash).
    EXCLUDED_ROUTES: Dict[str, list] = {}
    EXCLUDED_ROUTES_LIST: Dict[str, list] = {
        "graphdlq-service": ["/dlq/queues"],
    }

    for svc_name, route_exclude in EXCLUDED_ROUTES_LIST.items():
        EXCLUDED_ROUTES[svc_name] = [
            p.strip().strip("/") for p in route_exclude if p.strip()
        ]

    # ─── Per-service downstream timeouts ───────────────────────────────────
    # Keys are service names (the <name>-service in /<name>-service path prefixes).
    # Services NOT listed here use timeout=None (current behavior preserved).
    # Add a service here only after understanding its request-duration profile.
    DOWNSTREAM_TIMEOUTS_S: Dict[str, float] = {
        "api-detection-langue-fr-service": 180.0,
    }


def _create_service_map(config_class: Type[Configuration]) -> Dict[str, str]:
    """
    Inspects the Configuration class and automatically builds the SERVICE_MAP.
    It finds all attributes of type 'Service' and maps their api_path to their url.
    """
    service_map = {}
    # Built-in services
    for attr_name, attr_value in vars(config_class).items():
        if isinstance(attr_value, Service):
            service_map[attr_value.api_path] = attr_value.url
    # Dynamically added services
    for service in config_class.EXTRA_SERVICES.values():
        service_map[service.api_path] = service.url
    return service_map


SERVICE_MAP = _create_service_map(Configuration)
settings = Configuration()
