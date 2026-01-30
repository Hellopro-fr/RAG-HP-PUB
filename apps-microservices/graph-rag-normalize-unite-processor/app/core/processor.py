import logging
from typing import Dict, Any, List

from app.infrastructure.normalization_client import normalization_client


def process_normalization(
    data: Dict[str, Any], database: str = "neo4j", origin: str = "bo"
) -> Dict[str, Any]:
    """
    Process extracted nodes for unit normalization.

    Returns a dict with:
    - output_message: Message with successfully normalized nodes for next pipeline stage
    - failed_nodes: List of nodes that failed normalization with error info
    - has_failures: Boolean indicating if any nodes failed
    """
    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])
    graph_id = data.get("graph_id", "")
    id_produit = data.get("id_produit", "")

    logging.info(f"Normalizing nodes for graph_id: {graph_id}")

    normalized_nodes = []
    failed_nodes = []

    for node in nodes:
        if node.get("type") == "CaracteristiqueTechnique":
            props = node.get("properties", {})
            type_donnee = props.get("type_donnee")
            normalization_success = True
            error_info = None

            # Normalize if it's numeric or numeric_range
            if type_donnee == "numeric":
                normalized_props = normalization_client.normalize_quantity(
                    label=props.get("label"),
                    unit=props.get("unite"),
                    value=props.get("valeur"),
                    data_type="numeric",
                )
                if normalized_props:
                    node["properties"].update(normalized_props)
                else:
                    normalization_success = False
                    error_info = {
                        "reason": "normalization_failed",
                        "type": "numeric",
                        "unit": props.get("unite"),
                        "value": props.get("valeur"),
                    }

            elif type_donnee == "numeric_range":
                normalized_props = normalization_client.normalize_range(
                    label=props.get("label"),
                    unit=props.get("unite"),
                    min_val=props.get("valeur_min"),
                    max_val=props.get("valeur_max"),
                )
                if normalized_props:
                    node["properties"].update(normalized_props)
                else:
                    normalization_success = False
                    error_info = {
                        "reason": "normalization_failed",
                        "type": "numeric_range",
                        "unit": props.get("unite"),
                        "min_val": props.get("valeur_min"),
                        "max_val": props.get("valeur_max"),
                    }

            # Track success or failure
            if normalization_success:
                normalized_nodes.append(node)
            else:
                logging.warning(
                    f"Normalization failed for node {node.get('id')}: {error_info}"
                )
                failed_nodes.append(
                    {
                        "node": node,
                        "error": error_info,
                        "id_produit": id_produit,
                        "graph_id": graph_id,
                    }
                )
        else:
            # Non-CaracteristiqueTechnique nodes pass through
            normalized_nodes.append(node)

    # Find relationships for failed nodes
    failed_node_ids = {fn["node"].get("id") for fn in failed_nodes}
    failed_relationships = []
    success_relationships = []

    for rel in relationships:
        source_id = rel.get("source")
        target_id = rel.get("target")
        # If either source or target is a failed node, include relationship with failed node
        if source_id in failed_node_ids or target_id in failed_node_ids:
            failed_relationships.append(rel)
        else:
            success_relationships.append(rel)

    # Attach relationships to failed nodes for context
    for failed_node_entry in failed_nodes:
        node_id = failed_node_entry["node"].get("id")
        failed_node_entry["relationships"] = [
            rel
            for rel in failed_relationships
            if rel.get("source") == node_id or rel.get("target") == node_id
        ]

    output_message = {
        "data": {
            **data,
            "nodes": normalized_nodes,
            "relationships": success_relationships,
        },
        "database": database,
        "origin": origin,
    }

    logging.info(
        f"Normalization complete for {graph_id}: "
        f"{len(normalized_nodes)} success, {len(failed_nodes)} failed"
    )

    return {
        "output_message": output_message,
        "failed_nodes": failed_nodes,
        "has_failures": len(failed_nodes) > 0,
    }
