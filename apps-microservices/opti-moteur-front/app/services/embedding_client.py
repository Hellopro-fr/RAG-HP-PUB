"""
Client pour api-embedding-service (CamemBERT-large 1024 dims).

Permet a /search/text d'embedder la query sans dependance sur le front PHP.

Config via env var : EMBEDDING_SERVICE_URL
  - En Docker prod : http://rag-hp-pub-api-embedding-service-1:8555
  - En standalone  : http://localhost:8555
"""
import logging
import os
from typing import List

import requests

logger = logging.getLogger(__name__)

EMBEDDING_SERVICE_URL = os.getenv(
    "EMBEDDING_SERVICE_URL",
    "http://rag-hp-pub-api-embedding-service-1:8555",
)
EMBEDDING_TIMEOUT = int(os.getenv("EMBEDDING_TIMEOUT", "10"))


def _extract_vector(resp) -> List[float]:
    """
    Tolere plusieurs formats de reponse :
      - [0.1, 0.2, ...]
      - {"embedding": [...]}
      - {"vector": [...]}
      - {"data": [...]}
      - {"embeddings": [[...]]}
    """
    if isinstance(resp, list):
        if resp and isinstance(resp[0], list):
            return resp[0]
        return resp
    if isinstance(resp, dict):
        for key in ("embedding", "vector", "data", "embeddings"):
            val = resp.get(key)
            if val is None:
                continue
            if isinstance(val, list) and val and isinstance(val[0], list):
                return val[0]
            return val
    raise ValueError(f"Format reponse embedding inconnu : {type(resp)}")


def embed_text(text: str, timeout: int = None) -> List[float]:
    """Appelle api-embedding-service pour obtenir le vecteur d'une query."""
    if not text or not text.strip():
        raise ValueError("Le texte a embedder ne peut pas etre vide")

    url = f"{EMBEDDING_SERVICE_URL.rstrip('/')}/embedding"
    try:
        r = requests.post(
            url,
            json={"text": text},
            timeout=timeout or EMBEDDING_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        logger.error("Embedding service unavailable at %s: %s", url, e)
        raise
    try:
        data = r.json()
    except ValueError:
        raise ValueError(f"Reponse embedding non-JSON : {r.text[:200]}")
    return _extract_vector(data)
