"""
Graph Database Client for graph-rag-etl-processor.
Uses centralized gRPC client from common_utils.
"""

import asyncio
import logging
import concurrent.futures
from typing import List, Dict, Any

from common_utils.grpc_clients import graph_database_client as centralized_db_client

from app.config import settings


def _run_async(coro):
    """Run an async coroutine in a new event loop in a separate thread."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


class GraphDatabaseClient:
    """gRPC client for Graph Database Service using centralized client."""

    def __init__(self):
        logging.info(
            f"GraphDatabaseClient initialized for {settings.GRAPH_DATABASE_SERVICE_URL}"
        )

    async def execute_batch_async(self, statements: List[Dict[str, Any]]) -> bool:
        """
        Execute a batch of Cypher statements (async).
        statements: List of dicts with 'query' and 'parameters'.
        """
        try:
            success, error_message, results = await centralized_db_client.execute_batch_cypher(
                statements=statements,
                transactional=True
            )

            if not success:
                logging.error(f"Batch execution failed: {error_message}")
                for res in results:
                    if not res.success:
                        logging.error(
                            f"Statement {res.index} failed: {res.error_message}"
                        )
                return False

            return True

        except Exception as e:
            logging.error(f"RPC error (execute_batch): {e}")
            return False

    def execute_batch(self, statements: List[Dict[str, Any]]) -> bool:
        """
        Execute a batch of Cypher statements (sync wrapper).
        statements: List of dicts with 'query' and 'parameters'.
        """
        try:
            return _run_async(self.execute_batch_async(statements))
        except Exception as e:
            logging.error(f"Error in execute_batch: {e}")
            return False

    def close(self):
        """Cleanup (no persistent channel with async client)."""
        logging.info("GraphDatabaseClient closed.")


# Singleton instance
graph_db_client = GraphDatabaseClient()
