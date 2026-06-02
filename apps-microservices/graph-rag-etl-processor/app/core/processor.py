import logging
from typing import Dict, Any, List


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


def prepare_etl_statements(
    data: Dict[str, Any], database: str = "neo4j", origin: str = "bo"
) -> List[Dict[str, Any]]:
    """
    Prepare a list of Cypher statements for the ETL process.
    Does NOT execute them.

    Includes:
    1. Cleanup statements (DELETE existing relations)
    2. Node MERGE statements
    3. Relationship MERGE statements
    """
    nodes = data.get("nodes", [])
    relationships = data.get("relationships", [])
    graph_id = data.get("graph_id", "")

    all_statements = []

    # 1. Cleanup Logic
    # Extract product ID to clean up existing A_POUR_CARACTERISTIQUE relations
    product_id = _extract_product_id_from_nodes(nodes)

    # Fallback: the LLM extractor never includes the Produit node in `nodes`
    # (it extracts only CaracteristiqueTechnique), so the lookup above returns "".
    # For product extractions, the product's graph id is carried in data["graph_id"]
    # (e.g. "id_produit_496191"), which matches the Produit node's `id` property.
    if not product_id and data.get("source_type") == "Produit":
        product_id = data.get("graph_id", "")

    if product_id:
        cleanup_query = """
        MATCH (p:Produit {id: $product_id})-[r:A_POUR_CARACTERISTIQUE]->()
        DELETE r
        """
        all_statements.append(
            {"query": cleanup_query, "parameters": {"product_id": product_id}}
        )

    logging.debug(
        f"Preparing ETL for graph_id: {graph_id} with {len(nodes)} nodes and {len(relationships)} relationships"
    )

    # 2. Prepare Node MERGE statements
    for node in nodes:
        label = node.get("type", "Thing")
        properties = node.get("properties", {})

        # Ensure we have an ID to merge on.
        node_id = node.get("id") or properties.get("id") or properties.get("id_produit")

        if not node_id:
            # Try to find a unique field based on label
            if label == "Product" and "id_produit" in properties:
                node_id = properties["id_produit"]
            elif "name" in properties:
                node_id = properties["name"]
            else:
                logging.warning(f"Skipping node {label} without ID: {properties}")
                continue

        # Construct MERGE query
        if node_id:
            properties["id"] = node_id
            query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
            params = {"id": node_id, "props": properties}
        elif "name" in properties:
            query = f"MERGE (n:{label} {{name: $name}}) SET n += $props"
            params = {"name": properties["name"], "props": properties}
        else:
            # Fallback (should rarely happen given check above)
            query = f"CREATE (n:{label}) SET n = $props"
            params = {"props": properties}

        all_statements.append({"query": query, "parameters": params})

    # 3. Prepare Relationship MERGE statements
    for rel in relationships:
        source_id = rel.get("source")
        target_id = rel.get("target")
        rel_type = rel.get("type")
        props = rel.get("properties", {})

        if not (source_id and target_id and rel_type):
            continue

        # We assume source/target IDs refer to the 'id' property.
        query = (
            f"MATCH (a), (b) "
            f"WHERE a.id = $source_id AND b.id = $target_id "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r += $props"
        )

        params = {"source_id": source_id, "target_id": target_id, "props": props}
        all_statements.append({"query": query, "parameters": params})

    return all_statements
