import logging
from typing import Dict, Any, List, Tuple

# Note: We do NOT import graph_database_client here anymore for direct execution.
# The consumer handles the execution via batching.


def prepare_product_cypher(
    product_data: Dict[str, Any],
) -> Tuple[str, Dict[str, Any], str]:
    """
    Prepares the Cypher query and parameters for a product.
    Does NOT execute the query.

    Returns:
        Tuple(cypher_query, parameters, graph_id)
    """
    id_produit = product_data.get("id_produit", "unknown")
    graph_id = f"id_produit_{id_produit}"

    # Prepare props: exclude 'caracteristics', 'dept', 'pays' and ensure 'id' is set
    props = product_data.copy()
    props["id"] = graph_id
    props.pop("caracteristics", None)
    props.pop("dept", None)  # Exclude nested dept objects
    props.pop("pays", None)  # Exclude nested pays objects

    # Prepare IDs for relationships
    id_fournisseur_raw = str(props.get("id_fournisseur", "unknown"))
    id_categorie_raw = str(props.get("id_categorie", "unknown"))

    fournisseur_id = f"id_fournisseur_{id_fournisseur_raw}"
    categorie_id = f"id_categorie_{id_categorie_raw}"

    # Optimized Cypher: Create Product, Fournisseur, Categorie and links in one go
    cypher = """
    MERGE (p:Produit {id: $props.id}) SET p += $props
    MERGE (f:Fournisseur {id: $fournisseur_id}) 
    ON CREATE SET f.id_fournisseur = $raw_fournisseur_id, f.nom = $fournisseur_nom
    MERGE (c:Categorie {id: $categorie_id}) 
    ON CREATE SET c.id_categorie = $raw_categorie_id, c.nom = $categorie_nom
    MERGE (p)-[:EST_PROPOSE_PAR]->(f)
    MERGE (p)-[:APPARTIENT_A]->(c)
    """

    params = {
        "props": props,
        "fournisseur_id": fournisseur_id,
        "raw_fournisseur_id": id_fournisseur_raw,
        "fournisseur_nom": product_data.get("fournisseur", ""),
        "categorie_id": categorie_id,
        "raw_categorie_id": id_categorie_raw,
        "categorie_nom": product_data.get("categorie", ""),
    }

    return cypher, params, graph_id


def create_output_message(
    product_data: Dict[str, Any],
    graph_id: str,
    node_created: bool,
    database: str = "neo4j",
    origin: str = "bo",
) -> Dict[str, Any]:
    """
    Builds the output message for the next processor (LLM Extractor).
    """
    text_for_extraction = _build_extraction_text(product_data)

    return {
        "data": {
            "id_produit": product_data.get("id_produit", ""),
            "graph_id": graph_id,
            "nom_produit": product_data.get("nom_produit", ""),
            "description": product_data.get("description", ""),
            "categorie": product_data.get("categorie", ""),
            "id_categorie": product_data.get("id_categorie", ""),
            "fournisseur": product_data.get("fournisseur", ""),
            "id_fournisseur": product_data.get("id_fournisseur", ""),
            "text_for_extraction": text_for_extraction,
            "source_type": "Produit",
        },
        "node_created": node_created,
        "database": database,
        "origin": origin,
    }


def _format_characteristics_to_text(characteristics: List[Dict[str, Any]]) -> str:
    """
    Formats a list of characteristic dictionaries into a natural language string.
    """
    text_parts = []
    for char in characteristics:
        nom = char.get("nom-caracteristique", char.get("nom", ""))
        valeur = char.get("valeur", char.get("new-value", ""))
        description = char.get("description", "")
        unite = char.get("unite", "")
        id_car = char.get("id_caracteristique")
        id_val = char.get("id_valeur")

        if not nom and not valeur:
            continue

        id_car_str = str(id_car).replace("'", "") if id_car else "N/A"
        id_val_str = str(id_val).replace("'", "") if id_val else "N/A"
        meta_tag = f"[META id_c='{id_car_str}' id_v='{id_val_str}']"

        val_str = str(valeur)
        if unite:
            val_str += f" {unite}"

        part = f"{nom}: {val_str}. {meta_tag}"
        if description:
            part += f" Description: {description}."
        text_parts.append(part)

    return "\n".join(text_parts)


def _build_extraction_text(product_data: Dict[str, Any]) -> str:
    """
    Build a text representation of the product for LLM extraction.
    """
    caracteristics = product_data.get("caracteristics", [])
    if isinstance(caracteristics, list) and len(caracteristics) > 0:
        chars_text = _format_characteristics_to_text(caracteristics)
        if chars_text.strip():
            return chars_text

    description = product_data.get("description", "")
    nom_produit = product_data.get("nom_produit", "")

    if description and description.strip():
        parts = []
        if nom_produit:
            parts.append(f"Produit: {nom_produit}")
        parts.append(f"Description: {description}")
        return "\n".join(parts)

    return ""
