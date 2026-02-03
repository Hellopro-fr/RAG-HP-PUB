"""
Graph Database Client for graph-rag-fournisseur-processor.
Uses centralized gRPC client from common_utils.
"""

import asyncio
import logging
import concurrent.futures
from typing import Dict, Any, Tuple, List

from common_utils.grpc_clients import graph_database_client as centralized_db_client

from app.config import settings


def _run_async(coro):
    """Run an async coroutine in a new event loop in a separate thread."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


class GraphDatabaseClient:
    """
    Wrapper for graph-rag-database-connector-service using centralized client.
    Maintains domain-specific methods for fournisseur ingestion.
    """

    def __init__(self):
        logging.info(
            f"GraphDatabaseClient initialized for {settings.GRAPH_DATABASE_SERVICE_URL}"
        )

    async def execute_cypher_async(
        self, query: str, parameters: Dict[str, Any] = None, read_only: bool = False
    ) -> Tuple[bool, List[Dict], int]:
        """
        Execute a Cypher query (async).

        Returns:
            Tuple of (success, results, records_affected)
        """
        try:
            return await centralized_db_client.execute_cypher(
                query=query, parameters=parameters, read_only=read_only
            )
        except Exception as e:
            logging.error(f"gRPC error executing Cypher: {e}")
            return False, [], 0

    def execute_cypher(
        self, query: str, parameters: Dict[str, Any] = None, read_only: bool = False
    ) -> Tuple[bool, List[Dict], int]:
        """
        Execute a Cypher query (sync wrapper).
        Uses a thread pool to avoid 'event loop already running' issues.

        Returns:
            Tuple of (success, results, records_affected)
        """
        try:
            return _run_async(self.execute_cypher_async(query, parameters, read_only))
        except Exception as e:
            logging.error(f"Error executing Cypher: {e}")
            return False, [], 0

    def close(self):
        """Cleanup (no persistent channel with async client)."""
        logging.info("GraphDatabaseClient closed.")


# Singleton instance
graph_database_client = GraphDatabaseClient()
