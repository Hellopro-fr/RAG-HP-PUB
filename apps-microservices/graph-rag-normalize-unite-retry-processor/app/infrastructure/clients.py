"""
Service clients for graph-rag-normalize-unite-retry-processor.
Uses centralized gRPC clients from common_utils and HTTP embedding.
"""

import asyncio
import logging
import concurrent.futures
from typing import List, Tuple

from common_utils.grpc_clients import graph_milvus_client

from app.config import settings

import httpx


def _run_async(coro):
    """Run an async coroutine in a new event loop in a separate thread."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


class EmbeddingClientHTTP:
    """HTTP client for Embedding Service (same as semantic-vigil-processor)."""

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text using HTTP."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.EMBEDDING_API_KEY}",
        }
        payload = {"text": text}

        try:
            # Synchronous call since processor.py calls it synchronously
            with httpx.Client() as client:
                response = client.post(
                    settings.EMBEDDING_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                if data and isinstance(data, list) and "embedding" in data[0]:
                    return data[0]["embedding"]
                else:
                    logging.error(f"Invalid embedding response format for text: {text}")
                    return []
        except httpx.HTTPStatusError as e:
            logging.error(
                f"Embedding API request failed: {e.response.status_code} - {e.response.text}"
            )
            return []
        except Exception as e:
            logging.error(f"Embedding API error: {e}")
            return []

    def close(self):
        pass


class MilvusClient:
    """gRPC client for Graph Milvus Service using centralized client."""

    def __init__(self):
        logging.info(f"MilvusClient initialized for {settings.MILVUS_SERVICE_URL}")

    def search_similar_label(
        self, embedding: List[float], threshold: float
    ) -> Tuple[str, float]:
        """Search for a similar label (sync wrapper). Returns (label, distance) or (None, 0.0)."""
        try:
            results = _run_async(
                graph_milvus_client.search_similar_labels(
                    embedding=embedding, top_k=1, threshold=threshold
                )
            )
            if results:
                best = results[0]
                return best.label, best.distance
            return None, 0.0
        except Exception as e:
            logging.error(f"Milvus SearchLabels RPC error: {e}")
            return None, 0.0

    def upsert_label(self, label: str, embedding: List[float]) -> bool:
        """Upsert a new canonical label (sync wrapper)."""
        try:
            success, _ = _run_async(
                graph_milvus_client.upsert_label(label=label, embedding=embedding)
            )
            return success
        except Exception as e:
            logging.error(f"Milvus UpsertLabel RPC error: {e}")
            return False

    def upsert_entity(self, id: str, entity_type: str, embedding: List[float]) -> bool:
        """Upsert a new canonical entity (sync wrapper)."""
        try:
            success, _ = _run_async(
                graph_milvus_client.upsert_entity(
                    id=id, entity_type=entity_type, embedding=embedding
                )
            )
            return success
        except Exception as e:
            logging.error(f"Milvus UpsertEntity RPC error: {e}")
            return False

    def check_entities_exist(self, ids: List[str]) -> List[str]:
        """Check which entities already exist (sync wrapper)."""
        try:
            return _run_async(graph_milvus_client.check_entities_exist(ids=ids))
        except Exception as e:
            logging.error(f"Milvus CheckEntitiesExist RPC error: {e}")
            return []

    def check_labels_exist(self, labels: List[str]) -> List[str]:
        """Check which labels already exist (sync wrapper)."""
        try:
            return _run_async(graph_milvus_client.check_labels_exist(labels=labels))
        except Exception as e:
            logging.error(f"Milvus CheckLabelsExist RPC error: {e}")
            return []

    def close(self):
        pass


# Singleton instances
embedding_client = EmbeddingClientHTTP()
milvus_client = MilvusClient()
