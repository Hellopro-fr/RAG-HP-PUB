import logging
from typing import Dict, Any, List

from app.infrastructure.normalization_client import normalization_client


def process_normalization(
    data: Dict[str, Any], database: str = "neo4j", origin: str = "bo"
) -> Dict[str, Any]:
    """
    Process extracted nodes for unit normalization.
    """
    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])
    graph_id = data.get("graph_id", "")

    logging.info(f"Normalizing nodes for graph_id: {graph_id}")

    normalized_nodes = []
    for node in nodes:
        if node.get("type") == "CaracteristiqueTechnique":
            props = node.get("properties", {})
            type_donnee = props.get("type_donnee")

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

            elif type_donnee == "numeric_range":
                normalized_props = normalization_client.normalize_range(
                    label=props.get("label"),
                    unit=props.get("unite"),
                    min_val=props.get("valeur_min"),
                    max_val=props.get("valeur_max"),
                )
                if normalized_props:
                    node["properties"].update(normalized_props)

        normalized_nodes.append(node)

    output_message = {
        "data": {
            **data,
            "nodes": normalized_nodes,
        },
        "database": database,
        "origin": origin,
    }

    logging.info(f"Normalization complete for {graph_id}")
    return output_message
