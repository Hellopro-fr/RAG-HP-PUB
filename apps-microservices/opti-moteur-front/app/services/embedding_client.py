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
EMBEDDING_TIMEOUT = int(os.getenv("EMBEDDING_TIMEOUT", "30"))  # 10 -> 30 (service lent ~13s/req)

# Identifiant du caller envoye au service embedding pour priorisation.
# Sur GKE : defini via env var SERVICE_NAME dans le deployment.
# Le service embedding utilise cette info pour prioriser nos requetes
# (configurable cote serveur dans sa liste de "services prioritaires").
SERVICE_NAME = os.getenv("SERVICE_NAME", "opti-moteur-front")


def _extract_vector(resp) -> List[float]:
    """
    Tolere plusieurs formats de reponse :
      - [0.1, 0.2, ...]                            (list de floats)
      - [[0.1, 0.2, ...]]                          (list de list)
      - [{"embedding": [...], "text": ..., ...}]   (list de dict chunks, format api-embedding-service HelloPro)
      - {"embedding": [...]}
      - {"vector": [...]}
      - {"data": [...]}
      - {"embeddings": [[...]]}
    """
    if isinstance(resp, list):
        if not resp:
            raise ValueError("Reponse embedding : liste vide")
        first = resp[0]
        # list de list -> prendre le premier sous-vecteur
        if isinstance(first, list):
            return first
        # list de dict (format api-embedding-service : [{"embedding": [...], "text": ..., "chunk_id": ...}])
        if isinstance(first, dict):
            for key in ("embedding", "vector"):
                val = first.get(key)
                if isinstance(val, list):
                    if val and isinstance(val[0], list):
                        return val[0]
                    return val
            raise ValueError(f"Reponse embedding : dict sans cle embedding/vector. Cles={list(first.keys())}")
        # list de floats
        return resp
    if isinstance(resp, dict):
        for key in ("embedding", "vector", "data", "embeddings"):
            val = resp.get(key)
            if val is None:
                continue
            if isinstance(val, list) and val and isinstance(val[0], list):
                return val[0]
            if isinstance(val, list) and val and isinstance(val[0], dict):
                # {"data": [{"embedding": [...]}]}
                for k in ("embedding", "vector"):
                    v = val[0].get(k)
                    if isinstance(v, list):
                        return v
            return val
    raise ValueError(f"Format reponse embedding inconnu : {type(resp)}")


EMBEDDING_MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "1"))


def embed_text(text: str, timeout: int = None) -> List[float]:
    """
    Appelle api-embedding-service pour obtenir le vecteur d'une query.
    Avec retry automatique sur erreur reseau / timeout (default 1 retry).
    """
    if not text or not text.strip():
        raise ValueError("Le texte a embedder ne peut pas etre vide")

    url = f"{EMBEDDING_SERVICE_URL.rstrip('/')}/embedding"
    # On envoie SERVICE_NAME aux 3 emplacements possibles (header HTTP +
    # body JSON) pour que le serveur le retrouve quel que soit le format
    # qu'il attend. Format definitif a confirmer avec le collegue embedding.
    headers = {
        "Content-Type": "application/json",
        "X-Service-Name": SERVICE_NAME,
    }
    body = {
        "text": text,
        "source_service": SERVICE_NAME,
        "service_name": SERVICE_NAME,
    }

    last_error = None
    for attempt in range(EMBEDDING_MAX_RETRIES + 1):
        try:
            r = requests.post(
                url,
                json=body,
                headers=headers,
                timeout=timeout or EMBEDDING_TIMEOUT,
            )
            r.raise_for_status()
            break  # Succes : sortir de la boucle retry
        except requests.RequestException as e:
            last_error = e
            if attempt < EMBEDDING_MAX_RETRIES:
                logger.warning(
                    "Embedding attempt %d/%d failed for query=%r: %s. Retrying...",
                    attempt + 1, EMBEDDING_MAX_RETRIES + 1, text[:60], e,
                )
                # Petit backoff pour laisser le service respirer
                import time
                time.sleep(0.5)
            else:
                logger.error(
                    "Embedding service unavailable at %s after %d attempts: %s",
                    url, EMBEDDING_MAX_RETRIES + 1, e,
                )
                raise
    try:
        data = r.json()
    except ValueError:
        raise ValueError(f"Reponse embedding non-JSON : {r.text[:200]}")
    return _extract_vector(data)
