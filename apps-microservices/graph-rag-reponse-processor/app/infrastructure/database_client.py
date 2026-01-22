"""
Graph Database Client for graph-rag-reponse-processor.
Uses centralized gRPC client from common_utils.
"""

import asyncio
import logging
from typing import Dict, Any, List

from common_utils.grpc_clients import graph_database_client

from app.config import settings


class GraphDatabaseClient:
    """gRPC client for Graph Database Service using centralized client."""

    def __init__(self):
        logging.info(
            f"GraphDatabaseClient initialized for {settings.GRAPH_DATABASE_SERVICE_URL}"
        )

    async def execute_cypher_async(
        self, query: str, params: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query (async)."""
        try:
            success, results, _ = await graph_database_client.execute_cypher(
                query=query,
                parameters=params,
                read_only=True
            )
            return results if success else []
        except Exception as e:
            logging.error(f"gRPC Error: {e}")
            raise e

    def execute_cypher(
        self, query: str, params: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query (sync wrapper)."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.execute_cypher_async(query, params))

    def close(self):
        pass
