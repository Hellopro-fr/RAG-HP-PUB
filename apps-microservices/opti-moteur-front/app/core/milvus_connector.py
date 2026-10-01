"""
Connecteur Milvus pour l'ingestion (singleton thread-safe).
Inspire de l'implementation du service graph-rag-milvus.
"""
import logging
import asyncio
from typing import Dict, List, Any, Optional

from pymilvus import connections, Collection, utility

from app.core.credentials import settings

logger = logging.getLogger(__name__)


class MilvusConnector:
    """Singleton singleton pour acceder aux collections Milvus (RAG prod)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connected = False
            cls._instance._collections: Dict[str, Collection] = {}
        return cls._instance

    def connect(self):
        if self._connected:
            return
        try:
            logger.info(
                "Connexion a Milvus %s:%s (user=%s)",
                settings.ZILLIZ_URI, settings.ZILLIZ_PORT, settings.ZILLIZ_USER,
            )
            connections.connect(
                "default",
                host=settings.ZILLIZ_URI,
                port=settings.ZILLIZ_PORT,
                user=settings.ZILLIZ_USER,
                password=settings.ZILLIZ_PASSWORD,
            )
            self._connected = True
            logger.info("Milvus connecte.")
        except Exception as e:
            logger.critical("Erreur connexion Milvus: %s", e, exc_info=True)
            raise

    def disconnect(self):
        if self._connected:
            try:
                connections.disconnect("default")
            except Exception:
                pass
            self._connected = False

    def get_collection(self, name: str) -> Collection:
        """Retourne une Collection loaded (memorise)."""
        self.connect()
        if name not in self._collections:
            if not utility.has_collection(name):
                raise ValueError(f"Collection Milvus '{name}' introuvable")
            col = Collection(name)
            col.load()
            self._collections[name] = col
            logger.info("Collection Milvus '%s' loaded (%s entities)", name, col.num_entities)
        return self._collections[name]

    # ========== Operations async (wrap blocking pymilvus via to_thread) ==========
    async def query(
        self,
        collection_name: str,
        expr: str,
        output_fields: List[str],
        limit: int = 16384,
    ) -> List[Dict[str, Any]]:
        """Query sync encapsule en thread pour ne pas bloquer l'event loop."""
        col = self.get_collection(collection_name)
        return await asyncio.to_thread(
            col.query,
            expr=expr,
            output_fields=output_fields,
            limit=limit,
        )

    async def search(
        self,
        collection_name: str,
        vector: List[float],
        anns_field: str = "embedding",
        top_k: int = 10,
        metric_type: str = "IP",
        ef: Optional[int] = None,
        expr: Optional[str] = None,
        output_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        col = self.get_collection(collection_name)
        params = {"metric_type": metric_type, "params": {"ef": ef or settings.HNSW_EF_SEARCH}}
        results = await asyncio.to_thread(
            col.search,
            data=[vector],
            anns_field=anns_field,
            param=params,
            limit=top_k,
            expr=expr,
            output_fields=output_fields or [],
        )
        return [
            {
                "distance": hit.distance,
                **{f: hit.entity.get(f) for f in (output_fields or [])},
            }
            for hit in results[0]
        ]


# Singleton
milvus = MilvusConnector()
