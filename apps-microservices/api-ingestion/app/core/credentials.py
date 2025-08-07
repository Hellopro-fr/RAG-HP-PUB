import os
from dotenv import load_dotenv

from fastapi.security.oauth2 import OAuth2PasswordBearer
from pathlib import Path
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)


class Configuration:
    PROJECT_NAME: str = "API-HP-RAG"
    PROJECT_VERSION: str = "0.0.1"

    RABBITMQ_URL: str = f"{os.getenv("RABBITMQ_URL")}"

    DOCUMENT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


settings = Configuration()
