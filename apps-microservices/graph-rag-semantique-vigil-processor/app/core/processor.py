import logging
from typing import Dict, Any, List, Optional

from app.config import settings
from app.infrastructure.clients import embedding_client, milvus_client


def process_semantic_vigil(
    data: Dict[str, Any], database: str = "neo4j", origin: str = "bo"
) -> Dict[str, Any]:
    """
    Process extracted nodes for semantic deduplication.
    
    Logic:
    1. For nodes: Check if node ID exists in Milvus, merge if exists, create if not
    2. For labels: Check if label_id exists in Milvus, use canonical if exists, create if not
    """
    nodes = data.get("nodes", [])
    graph_id = data.get("graph_id", "")

    logging.info(f"Semantic Vigil check for graph_id: {graph_id}")

    processed_nodes = []
    for node in nodes:
        if node.get("type") == "CaracteristiqueTechnique":
            processed_node = _process_characteristic(node)
            processed_nodes.append(processed_node)
        else:
            processed_nodes.append(node)

    output_message = {
        "data": {
            **data,
            "nodes": processed_nodes,
        },
        "database": database,
        "origin": origin,
    }

    logging.info(f"Semantic Vigil complete for {graph_id}")
    return output_message


def _process_characteristic(node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve canonical label/id for a characteristic.
    
    1. Node Deduplication: Check by exact node ID match
    2. Label Deduplication: Check by exact label_id match
    """
    props = node.get("properties", {})
    
    # --- 1. Node Deduplication (by exact ID) ---
    node_id = node.get("id")
    if node_id:
        # Check if node ID already exists in Milvus (exact match)
        existing_ids = milvus_client.check_entities_exist([node_id])
        
        if node_id in existing_ids:
            # Node exists - mark for merge
            logging.info(f"Node ID '{node_id}' exists in Milvus - will merge")
            node["_action"] = "merge"
        else:
            # New node - create and upsert to Milvus
            logging.info(f"New node ID: '{node_id}' - will create")
            node["_action"] = "create"
            
            # Embed the node_id and upsert to Milvus entity collection
            node_embedding = embedding_client.get_embedding(node_id)
            if node_embedding:
                success = milvus_client.upsert_entity(
                    id=node_id, 
                    entity_type="CaracteristiqueTechnique", 
                    embedding=node_embedding
                )
                if success:
                    logging.info(f"Upserted node '{node_id}' to Milvus entity collection")
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
        return node

    # Check if this label_id already exists in Milvus label collection
    existing_labels = milvus_client.check_labels_exist([label_id])
    
    if label_id in existing_labels:
        # Label exists - use as canonical
        logging.info(f"Label ID '{label_id}' already exists - using as canonical")
        props["label_canonique"] = label_id
    else:
        # New label - embed and check for semantic similarity
        embedding = embedding_client.get_embedding(label_id)
        if not embedding:
            logging.warning(f"Could not get embedding for label_id: {label_id}")
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
