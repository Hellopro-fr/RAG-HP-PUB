import os

class Configuration:
    PROJECT_NAME: str = "API-OPTIMIZE-HP-RAG"
    PROJECT_VERSION: str = "0.0.1"

    DOCUMENT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


settings = Configuration()