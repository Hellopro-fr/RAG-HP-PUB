"""
Graph Database Client for graph-rag-produit-processor.
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
    Maintains domain-specific methods for product ingestion.
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
                query=query,
                parameters=parameters,
                read_only=read_only
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
            return _run_async(
                self.execute_cypher_async(query, parameters, read_only)
            )
        except Exception as e:
            logging.error(f"Error executing Cypher: {e}")
            return False, [], 0

    def create_product_node(self, product_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Create or merge a Product node in Neo4j using user-specified logic.
        Excludes 'caracteristics' from properties.
        """
        graph_id = product_data.get(
            "graph_id", f"id_produit_{product_data.get('id_produit', 'unknown')}"
        )

        # Prepare props: exclude 'caracteristics' and ensure 'id' is set
        props = product_data.copy()
        props["id"] = graph_id
        props.pop("caracteristics", None)

        # Prepare IDs for relationships
        id_fournisseur_raw = str(props.get("id_fournisseur", "unknown"))
        id_categorie_raw = str(props.get("id_categorie", "unknown"))

        fournisseur_id = f"id_fournisseur_{id_fournisseur_raw}"
        categorie_id = f"id_categorie_{id_categorie_raw}"

        # User-specified Cypher
        cypher = """
        MERGE (p:Produit {id: $props.id}) SET p += $props
        MERGE (f:Fournisseur {id: $fournisseur_id}) ON CREATE SET f.fournisseur = $props.fournisseur
        MERGE (c:Categorie {id: $categorie_id}) ON CREATE SET c.categorie = $props.categorie
        MERGE (p)-[:EST_PROPOSE_PAR]->(f)
        MERGE (p)-[:APPARTIENT_A]->(c)
        """

        params = {
            "props": props,
            "fournisseur_id": fournisseur_id,
            "categorie_id": categorie_id,
        }

        success, _, _ = self.execute_cypher(cypher, params)
        return success, graph_id

    def _create_product_relationships(
        self, product_graph_id: str, product_data: Dict[str, Any]
    ):
        """Create relationships from Product to Fournisseur and Categorie."""

        # Link to Fournisseur
        if product_data.get("id_fournisseur"):
            fournisseur_id = f"id_fournisseur_{product_data['id_fournisseur']}"
            cypher = """
            MATCH (p:Produit {id: $product_id})
            MERGE (f:Fournisseur {id: $fournisseur_id})
            ON CREATE SET f.id_fournisseur = $raw_id, f.nom = $nom
            MERGE (p)-[:EST_PROPOSE_PAR]->(f)
            """
            params = {
                "product_id": product_graph_id,
                "fournisseur_id": fournisseur_id,
                "raw_id": product_data["id_fournisseur"],
                "nom": product_data.get("fournisseur", ""),
            }
            self.execute_cypher(cypher, params)

        # Link to Categorie
        if product_data.get("id_categorie"):
            categorie_id = f"id_categorie_{product_data['id_categorie']}"
            cypher = """
            MATCH (p:Produit {id: $product_id})
            MERGE (c:Categorie {id: $categorie_id})
            ON CREATE SET c.id_categorie = $raw_id, c.nom = $nom
            MERGE (p)-[:APPARTIENT_A]->(c)
            """
            params = {
                "product_id": product_graph_id,
                "categorie_id": categorie_id,
                "raw_id": product_data["id_categorie"],
                "nom": product_data.get("categorie", ""),
            }
            self.execute_cypher(cypher, params)

    def close(self):
        """Cleanup (no persistent channel with async client)."""
        logging.info("GraphDatabaseClient closed.")


# Singleton instance
graph_database_client = GraphDatabaseClient()
