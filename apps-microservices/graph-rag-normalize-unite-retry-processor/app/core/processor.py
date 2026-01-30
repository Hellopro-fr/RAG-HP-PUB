"""
Processor for graph-rag-normalize-unite-retry-processor.
Handles:
1. Retry normalization via gRPC
2. Semantic vigil (Milvus deduplication)
3. Direct write to Neo4j with merge/create
"""

import logging
from typing import Dict, Any, List, Optional

from app.config import settings
from app.infrastructure.normalization_client import normalization_client
from app.infrastructure.clients import embedding_client, milvus_client
from app.infrastructure.database_client import graph_db_client


def process_retry_normalization(failed_node_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a failed normalization:
    1. Attempt normalization via gRPC service
    2. If success: apply semantic vigil (Milvus), then write to Neo4j
    3. If failure: return for manual DLQ routing (no retry loop)

    Args:
        failed_node_entry: Dict containing node, error, id_produit, graph_id, relationships

    Returns:
        Dict with 'success' boolean and 'error' if failed
    """
    node = failed_node_entry.get("node", {})
    error_info = failed_node_entry.get("error", {})
    id_produit = failed_node_entry.get("id_produit", "")
    graph_id = failed_node_entry.get("graph_id", "")
    relationships = failed_node_entry.get("relationships", [])

    node_id = node.get("id", "")
    props = node.get("properties", {})

    logging.info(f"Processing retry for node: {node_id} (product: {id_produit})")

    # Step 1: Attempt normalization
    type_donnee = props.get("type_donnee")
    normalized_props = None

    if type_donnee == "numeric":
        normalized_props = normalization_client.normalize_quantity(
            label=props.get("label"),
            unit=props.get("unite"),
            value=props.get("valeur"),
            data_type="numeric",
        )
    elif type_donnee == "numeric_range":
        normalized_props = normalization_client.normalize_range(
            label=props.get("label"),
            unit=props.get("unite"),
            min_val=props.get("valeur_min"),
            max_val=props.get("valeur_max"),
        )

    if not normalized_props:
        logging.warning(
            f"Normalization still failed for node {node_id} - sending to manual DLQ"
        )
        return {
            "success": False,
            "error": {
                "reason": "normalization_still_failed",
                "original_error": error_info,
                "node_id": node_id,
                "unit": props.get("unite"),
            },
            "failed_node_entry": failed_node_entry,
        }

    # Update node properties with normalized values
    node["properties"].update(normalized_props)
    logging.info(f"Normalization successful for node {node_id}")

    # Step 2: Apply Semantic Vigil (Milvus deduplication)
    processed_node = _apply_semantic_vigil(node)

    # Step 3: Write to Neo4j with relationships
    success = _write_to_neo4j(processed_node, id_produit, relationships)

    if not success:
        logging.error(f"Failed to write node {node_id} to Neo4j")
        return {
            "success": False,
            "error": {
                "reason": "neo4j_write_failed",
                "node_id": node_id,
            },
            "failed_node_entry": failed_node_entry,
        }

    logging.info(f"✅ Successfully processed retry node {node_id}")
    return {"success": True}


def _apply_semantic_vigil(node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply semantic vigil (Milvus deduplication) to a node.
    Logic from graph-rag-semantique-vigil-processor.
    """
    props = node.get("properties", {})

    # --- 1. Node Deduplication (by exact ID) ---
    node_id = node.get("id")
    if node_id:
        # Check if node ID already exists in Milvus (exact match)
        existing_ids = milvus_client.check_entities_exist([node_id])

        if node_id in existing_ids:
            logging.info(f"Node ID '{node_id}' exists in Milvus - will merge")
            node["_action"] = "merge"
        else:
            logging.info(f"New node ID: '{node_id}' - will create")
            node["_action"] = "create"

            # Embed the node_id and upsert to Milvus entity collection
            node_embedding = embedding_client.get_embedding(node_id)
            if node_embedding:
                success = milvus_client.upsert_entity(
                    id=node_id,
                    entity_type="CaracteristiqueTechnique",
                    embedding=node_embedding,
                )
                if success:
                    logging.info(
                        f"Upserted node '{node_id}' to Milvus entity collection"
                    )
                else:
                    logging.warning(f"Failed to upsert node '{node_id}' to Milvus")
            else:
                logging.warning(f"Could not get embedding for node_id: {node_id}")

    # --- 2. Label Deduplication (by label_id) ---
    label_id = props.get("label_id")

    if not label_id:
        # Fallback to label if label_id not present
        label_id = props.get("label")
        if label_id:
            props["label_id"] = label_id

    if not label_id:
        node["properties"] = props
        return node

    # Check if this label_id already exists in Milvus label collection
    existing_labels = milvus_client.check_labels_exist([label_id])

    if label_id in existing_labels:
        logging.info(f"Label ID '{label_id}' already exists - using as canonical")
        props["label_canonique"] = label_id
    else:
        # New label - embed and check for semantic similarity
        embedding = embedding_client.get_embedding(label_id)
        if not embedding:
            logging.warning(f"Could not get embedding for label_id: {label_id}")
            node["properties"] = props
            return node

        # Search for semantically similar existing labels
        found_label, distance = milvus_client.search_similar_label(
            embedding, threshold=settings.SIMILARITY_THRESHOLD
        )

        if found_label:
            logging.info(
                f"Label '{label_id}' matched to canonical '{found_label}' (score: {distance:.4f})"
            )
            props["label_canonique"] = found_label
        else:
            # No match - insert as new canonical label
            logging.info(f"New canonical label: '{label_id}'")
            success = milvus_client.upsert_label(label_id, embedding)
            if success:
                logging.info(f"Upserted label '{label_id}' to Milvus label collection")
            props["label_canonique"] = label_id

    node["properties"] = props
    return node


def _write_to_neo4j(
    node: Dict[str, Any], id_produit: str, relationships: List[Dict[str, Any]]
) -> bool:
    """
    Write node to Neo4j with merge or create, plus relationships.
    Logic from graph-rag-etl-processor.
    """
    statements = []

    label = node.get("type", "CaracteristiqueTechnique")
    properties = node.get("properties", {})
    node_id = node.get("id") or properties.get("id")
    action = node.get("_action", "merge")

    if not node_id:
        logging.warning(f"Skipping node without ID: {properties}")
        return False

    # Ensure id is in properties
    properties["id"] = node_id

    # Remove internal _action field from properties
    if "_action" in properties:
        del properties["_action"]

    # Prepare node MERGE/CREATE statement
    if action == "merge":
        query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
    else:
        query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"

    params = {"id": node_id, "props": properties}
    statements.append({"query": query, "parameters": params})

    # Prepare relationship statements
    for rel in relationships:
        source_id = rel.get("source")
        target_id = rel.get("target")
        rel_type = rel.get("type")
        rel_props = rel.get("properties", {})

        if not (source_id and target_id and rel_type):
            continue

        rel_query = (
            f"MATCH (a), (b) "
            f"WHERE a.id = $source_id AND b.id = $target_id "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r += $props"
        )

        rel_params = {
            "source_id": source_id,
            "target_id": target_id,
            "props": rel_props,
        }
        statements.append({"query": rel_query, "parameters": rel_params})

    # If we have produit relationship and it's not in the relationships list
    if id_produit and not any(
        r.get("type") == "A_POUR_CARACTERISTIQUE" for r in relationships
    ):
        produit_rel_query = (
            f"MATCH (p:Produit {{id: $produit_id}}), (c:{label} {{id: $node_id}}) "
            f"MERGE (p)-[r:A_POUR_CARACTERISTIQUE]->(c)"
        )
        statements.append(
            {
                "query": produit_rel_query,
                "parameters": {"produit_id": id_produit, "node_id": node_id},
            }
        )

    # Execute batch
    return graph_db_client.execute_batch(statements)
