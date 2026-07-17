"""
Settings du microservice opti-moteur-front.
Conventions alignees avec les autres services RAG-HP-PUB (ZILLIZ_*, .env file).
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Milvus (credentials communs au repo) ---
    ZILLIZ_URI: str
    ZILLIZ_PORT: str = "19530"
    ZILLIZ_USER: str
    ZILLIZ_PASSWORD: str
    MILVUS_COLLECTION: str = "produits_3"

    # --- Typesense ---
    TYPESENSE_HOST: str = "localhost"
    TYPESENSE_PORT: str = "8108"
    TYPESENSE_PROTOCOL: str = "http"
    TYPESENSE_API_KEY: str = "hp_poc_2026"
    TYPESENSE_COLLECTION: str = "produits_prod"
    TYPESENSE_CONNECTION_TIMEOUT: int = 60

    # --- OpenSearch (optionnel, pour benchmark) ---
    OPENSEARCH_URL: str = "http://localhost:9200"
    OPENSEARCH_INDEX: str = "produits_hellopro_cam"

    # --- Embedding ---
    EMBEDDING_DIMENSION: int = 1024

    # --- Recherche : parametres HNSW ---
    HNSW_EF_SEARCH: int = 128

    # --- Re-rank Python : poids ---
    RERANK_W_VECTOR: float = 0.55
    RERANK_W_BM25: float = 0.10
    RERANK_W_NAME: float = 0.25
    RERANK_W_CAT: float = 0.10

    # --- Detection categorie ---
    # Threshold bas (0.30) car la validation est deja stricte via le
    # prefix-match sur les tokens (is_prefix_match dans utils/text.py).
    # Confidence < 0.30 = query vraiment ambigue, on laisse filter_by=null.
    CAT_FILTER_THRESHOLD: float = 0.30
    CAT_FILTER_TOP_N: int = 3
    CAT_PREFIX_LOOKAHEAD: int = 2

    # --- Search ---
    CANDIDATES_TOP_K: int = 50
    DEFAULT_TOP_K: int = 10

    # --- Service ---
    SERVICE_PORT: int = 8570

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
