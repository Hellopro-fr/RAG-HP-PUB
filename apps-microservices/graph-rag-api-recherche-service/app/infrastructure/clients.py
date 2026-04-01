"""
Service clients for graph-rag-api-recherche-service.
Uses centralized gRPC clients from common_utils.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

from common_utils.grpc_clients import embedding_client
from common_utils.grpc_clients import graph_milvus_client
from common_utils.grpc_clients import graph_database_client
from common_utils.grpc_clients import graph_normalization_client
from common_utils.grpc_clients import spacy_client
from common_utils.grpc_clients import reranking_client

from app.config import settings


class ServiceClients:
    """
    Wrapper providing a unified async interface for centralized gRPC clients.
    """

    def __init__(self):
        logging.info("ServiceClients initialized using centralized gRPC clients.")

    # --- Embedding ---
    async def get_embedding(self, text: str) -> List[float]:
        try:
            return await embedding_client.get_embedding(text)
        except Exception as e:
            logging.error(f"Embedding Error: {e}")
            return []

    # --- Milvus ---
    async def search_vectors(
        self,
        embedding: List[float],
        node_type: str = "Produit",
        top_k: int = 5,
        threshold: float = 0.75,
    ) -> List[Dict[str, Any]]:
        try:
            results = await graph_milvus_client.search_similar_entities(
                embedding=embedding,
                entity_type=node_type,
                top_k=top_k,
                threshold=threshold,
            )
            return [{"id": r.id, "score": r.distance} for r in results]
        except Exception as e:
            logging.error(f"Milvus Search Error: {e}")
            return []

    async def search_similar_characteristics(
        self, embedding: List[float], top_k: int = 5, threshold: float = 0.85
    ) -> List[Dict[str, Any]]:
        try:
            results = await graph_milvus_client.search_similar_characteristics(
                embedding=embedding, top_k=top_k, threshold=threshold
            )
            return [{"id": r.id, "score": r.distance} for r in results]
        except Exception as e:
            logging.error(f"Milvus Characteristic Search Error: {e}")
            return []

    # --- Graph Database (Neo4j) ---
    async def execute_cypher(
        self, query: str, params: Dict[str, Any] = None, read_only: bool = True
    ) -> List[Dict[str, Any]]:
        try:
            success, results, _ = await graph_database_client.execute_cypher(
                query=query, parameters=params, read_only=read_only
            )
            return results if success else []
        except Exception as e:
            logging.error(f"Graph DB Error: {e}")
            return []

    async def execute_cypher_direct(
        self, query: str, params: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute Cypher query directly using Neo4jGraph connection (like old implementation).
        Bypasses gRPC to avoid protobuf serialization issues.
        """
        try:
            from langchain_community.graphs import Neo4jGraph

            # Lazy initialization of direct Neo4j connection
            if not hasattr(self, "_neo4j_graph") or self._neo4j_graph is None:
                self._neo4j_graph = Neo4jGraph(
                    url=settings.NEO4J_URI,
                    username=settings.NEO4J_USER,
                    password=settings.NEO4J_PASSWORD,
                    database=settings.NEO4J_DATABASE,
                )
                logging.info("Direct Neo4jGraph connection established.")

            # Execute query in a thread to avoid blocking
            results = await asyncio.to_thread(
                self._neo4j_graph.query, query, params or {}
            )
            return results if results else []
        except Exception as e:
            logging.error(f"Direct Graph DB Error: {e}", exc_info=True)
            return []

    async def execute_cypher_async(
        self, query: str, params: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute Cypher query using the native neo4j async driver.
        Fully async — no thread pool, no LangChain overhead.
        """
        from neo4j import AsyncGraphDatabase

        # Lazy initialization of async driver
        if not hasattr(self, "_neo4j_async_driver") or self._neo4j_async_driver is None:
            self._neo4j_async_driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                max_connection_pool_size=50,
                connection_acquisition_timeout=30,
            )
            logging.info("Native async Neo4j driver initialized.")

        try:
            async with self._neo4j_async_driver.session(
                database=settings.NEO4J_DATABASE
            ) as session:
                result = await session.run(query, params or {})
                records = await result.data()
                return records if records else []
        except Exception as e:
            logging.error(f"Async Neo4j Error: {e}", exc_info=True)
            return []

    async def execute_cypher_stream(self, query: str, params: Dict[str, Any] = None):
        """
        Execute Cypher query and yield records one by one as they arrive from Neo4j.
        Allows caller to process/score products while Neo4j is still sending results.
        """
        from neo4j import AsyncGraphDatabase

        if not hasattr(self, "_neo4j_async_driver") or self._neo4j_async_driver is None:
            self._neo4j_async_driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                max_connection_pool_size=50,
                connection_acquisition_timeout=30,
            )
            logging.info("Native async Neo4j driver initialized (stream).")

        async with self._neo4j_async_driver.session(
            database=settings.NEO4J_DATABASE
        ) as session:
            result = await session.run(query, params or {})
            async for record in result:
                yield record.data()

    async def get_graph_schema(self) -> str:
        try:
            schema = await graph_database_client.get_graph_schema(
                include_properties=True
            )
            return schema.schema_text
        except Exception as e:
            logging.error(f"Graph Schema Error: {e}")
            return ""

    # --- Normalization ---
    async def normalize_quantity(
        self, value: Any, unit: Optional[str], label: str
    ) -> Dict[str, Any]:
        try:
            res = await graph_normalization_client.normalize_quantity(
                label=label, unit=unit, value=str(value)
            )
            if res.success:
                return {
                    "valeur_canonique": res.canonical_value,
                    "unite_canonique": res.canonical_unit,
                }
            return {}
        except Exception as e:
            logging.error(f"Normalization Error: {e}")
            return {}

    async def normalize_range(
        self, min_val: float, max_val: float, unit: Optional[str], label: str
    ) -> Dict[str, Any]:
        try:
            res = await graph_normalization_client.normalize_range(
                label=label, unit=unit, min_value=min_val, max_value=max_val
            )
            if res.success:
                return {
                    "valeur_min_canonique": res.canonical_min,
                    "valeur_max_canonique": res.canonical_max,
                    "unite_canonique": res.canonical_unit,
                }
            return {}
        except Exception as e:
            logging.error(f"Range Normalization Error: {e}")
            return {}

    # --- Reranking ---
    async def rerank_documents(
        self, query: str, documents: List[str]
    ) -> List[Dict[str, Any]]:
        try:
            return await reranking_client.rerank_documents_with_scores(query, documents)
        except Exception as e:
            logging.error(f"Reranking Error: {e}")
            return []

    # --- Spacy ---
    async def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        try:
            entities = await spacy_client.extract_entities(text)
            return [{"text": e.text, "label": e.label} for e in entities]
        except Exception as e:
            logging.error(f"Spacy Extraction Error: {e}")
            return []

    def close(self):
        logging.info("ServiceClients closed.")


# Singleton instance
clients = ServiceClients()
