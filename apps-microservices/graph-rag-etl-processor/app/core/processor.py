import logging
import json
from typing import Dict, Any, List

from app.infrastructure.database_client import graph_db_client


def _cleanup_caracteristique_relations(product_id: str) -> bool:
    """
    Delete existing A_POUR_CARACTERISTIQUE relationships for a product.
    This ensures a clean slate before ingesting new nodes from LLM.
    """
    if not product_id:
        logging.warning("No product ID provided for cleanup, skipping.")
        return True

    cleanup_query = """
    MATCH (p:Produit {id: $product_id})-[r:A_POUR_CARACTERISTIQUE]->()
    DELETE r
    """
    logging.info(f"🧹 Cleaning up A_POUR_CARACTERISTIQUE relations for product: {product_id}")

    statements = [{"query": cleanup_query, "parameters": {"product_id": product_id}}]
    success = graph_db_client.execute_batch(statements)

    if success:
        logging.info(f"✅ Cleanup successful for product: {product_id}")
    else:
        logging.error(f"❌ Cleanup failed for product: {product_id}")

    return success


def _extract_product_id_from_nodes(nodes: List[Dict[str, Any]]) -> str:
    """
    Extract the product ID from the nodes list.
    Looks for Produit node type or id_produit in properties.
    """
    for node in nodes:
        label = node.get("type", "")
        properties = node.get("properties", {})
        node_id = node.get("id") or properties.get("id") or properties.get("id_produit")

        # Check if this is a Produit node
        if label == "Produit" and node_id:
            return node_id

        # Also check for id_produit in properties
        if "id_produit" in properties:
            return properties["id_produit"]

    return ""


def process_etl(
    data: Dict[str, Any], database: str = "neo4j", origin: str = "bo"
) -> bool:
    """
    Process final graph data and write to Neo4j.
    Generates Cypher MERGE statements for nodes and relationships.
    Cleans up existing A_POUR_CARACTERISTIQUE relations before ingesting new nodes.
    """
    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])

    # Extract product ID and cleanup existing relations
    product_id = _extract_product_id_from_nodes(nodes)
    if product_id:
        cleanup_success = _cleanup_caracteristique_relations(product_id)
        if not cleanup_success:
            logging.error(f"Failed to cleanup relations for product {product_id}, continuing with ingestion...")
            # Continue with ingestion even if cleanup fails
    graph_id = data.get("graph_id", "")

    logging.info(
        f"Starting ETL for graph_id: {graph_id} with {len(nodes)} nodes and {len(relationships)} relationships"
    )

    statements = []

    # 1. Prepare Node MERGE statements
    for node in nodes:
        logging.info(f"Processing node: {node}")
        label = node.get("type", "Thing")
        properties = node.get("properties", {})

        # Ensure we have an ID to merge on.
        # The LLM extractor places 'id' at the node root level, not inside properties.
        # Check node root first, then fall back to properties.
        node_id = node.get("id") or properties.get("id") or properties.get("id_produit")
        if not node_id:
            # Try to find a unique field based on label
            if label == "Product" and "id_produit" in properties:
                node_id = properties["id_produit"]
            elif "name" in properties:
                node_id = properties["name"]  # Fallback for simple entities
            else:
                logging.warning(f"Skipping node {label} without ID: {properties}")
                continue

        # Clean properties for Cypher (dates, list handling if needed)
        # Struct matches python simple types well.

        # Using MERGE on primary key (assuming 'id' or specific key)
        # Note: In a real system, we should know the primary key for each label.
        # For this implementation, we assume 'id' is the universal key if present,
        # otherwise we might just create if we can't identify uniqueness.
        # Let's assume we merge on 'id' if exists, otherwise assume distinct?
        # Actually, extracting entities usually provides a name/id.

        # Simplified approach: MERGE on `id` property.
        # Ensure id is in properties for the node to be stored correctly.
        if node_id:
            properties["id"] = node_id
            query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
            params = {"id": node_id, "props": properties}
        elif "name" in properties:
            query = f"MERGE (n:{label} {{name: $name}}) SET n += $props"
            params = {"name": properties["name"], "props": properties}
        else:
            # Create without merge if no key
            query = f"CREATE (n:{label}) SET n = $props"
            params = {"props": properties}

        statements.append({"query": query, "parameters": params})

    # 2. Prepare Relationship MERGE statements
    for rel in relationships:
        source_id = rel.get("source")
        target_id = rel.get("target")
        rel_type = rel.get("type")
        props = rel.get("properties", {})

        if not (source_id and target_id and rel_type):
            continue

        # We assume source/target IDs refer to the 'id' property or 'name' used above.
        # This requires consistency from the extraction phase.
        # Let's assume input IDs are valid.

        query = (
            f"MATCH (a), (b) "
            f"WHERE a.id = $source_id AND b.id = $target_id "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r += $props"
        )
        # Fallback if IDs are names (determined by extraction logic)
        # Ideally extraction sends consistent IDs.

        params = {"source_id": source_id, "target_id": target_id, "props": props}
        statements.append({"query": query, "parameters": params})

    if not statements:
        logging.warning("No statements generated for ETL.")
        return True

    # 3. Execute Batch
    # Split into smaller batches if necessary (not doing for now)
    success = graph_db_client.execute_batch(statements)

    if success:
        logging.info(f"ETL successful for {graph_id}")
    else:
        logging.error(f"ETL failed for {graph_id}")

    return success
