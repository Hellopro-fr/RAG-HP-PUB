from dataclasses import dataclass
import os
from typing import Dict, Type
from dotenv import load_dotenv
from pathlib import Path

# Load default .env
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# Load extra .env if exists
extra_env_path = Path('.') / '.env.url'
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

    # CLEANER: Service = Service(
    #     url=os.getenv("CLEANER", "http://localhost:8001"), 
    #     api_path="/cleaner-service"
    # )
    # SCRAPING: Service = Service(
    #     url=os.getenv("SCRAPING", "http://localhost:8002"), 
    #     api_path="/scraping-service"
    # )
    # EMBEDDING: Service = Service(
    #     url=os.getenv("EMBEDDING", "http://localhost:8003"), 
    #     api_path="/embedding-service"
    # )

    DOCUMENT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

    # Dynamically add services based on environment keys
    EXTRA_SERVICES: Dict[str, Service] = {}

    for key, value in os.environ.items():
        # convention: SERVICE_<NAME>=http://url  --> api_path="/<name>-service"
        if key.startswith("SERVICE_"):
            service_name = key[len("SERVICE_"):].lower()
            EXTRA_SERVICES[service_name] = Service(
                url=value,
                api_path=f"/{service_name}-service"
            )

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
