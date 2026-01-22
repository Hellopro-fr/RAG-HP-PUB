import json
import logging
from typing import Dict, Any, List

from app.infrastructure.graph_database_client import graph_database_client


def process_product_for_graph_rag(
    product_data: Dict[str, Any], database: str = "neo4j", origin: str = "bo"
) -> Dict[str, Any]:
    """
    Process product data for Graph RAG:
    1. Create/merge base Product node in Neo4j
    2. Create relationships to Fournisseur and Categorie
    3. Prepare message for LLM extraction processor

    Returns:
        Output message for the next processor in the pipeline
    """
    if not isinstance(product_data, dict):
        raise ValueError("Product data must be a dictionary")

    # print(f"Product data from message : {product_data}")
    id_produit = product_data.get("id_produit", "unknown")
    logging.info(f"Processing product {id_produit} for Graph RAG")

    # Step 1: Build graph ID
    graph_id = f"id_produit_{id_produit}"

    # Step 2: Create/merge product node in Neo4j via gRPC
    try:
        success, created_id = graph_database_client.create_product_node(
            {**product_data, "graph_id": graph_id}
        )

        if not success:
            logging.warning(
                f"Failed to create node for product {id_produit}, continuing anyway"
            )
    except Exception as e:
        logging.error(f"Error creating product node: {e}")
        success = False

    # Step 3: Prepare text for LLM extraction
    # Combine relevant fields for entity/relationship extraction
    text_for_extraction = _build_extraction_text(product_data)

    # Step 4: Build output message for next processor
    output_message = {
        "data": {
            "id_produit": id_produit,
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
        "node_created": success,
        "database": database,
        "origin": origin,
    }

    logging.info(f"Product {id_produit} processed. Node created: {success}")
    # print(f"Output message : {output_message}")
    return output_message


def _format_characteristics_to_text(characteristics: List[Dict[str, Any]]) -> str:
    """
    Formats a list of characteristic dictionaries into a natural language string
    suitable for LLM processing, injecting metadata tags for ID preservation.
    """
    text_parts = []
    for char in characteristics:
        # Handle variations in input keys based on user specification
        nom = char.get("nom-caracteristique", char.get("nom", ""))
        valeur = char.get("valeur", char.get("new-value", ""))
        description = char.get("description", "")
        unite = char.get("unite", "")

        # IDs to preserve
        id_car = char.get("id_caracteristique")
        id_val = char.get("id_valeur")

        # Skip empty entries
        if not nom and not valeur:
            continue

        # Prepare metadata tag strings, handling Potential None/Null values safely
        id_car_str = str(id_car).replace("'", "") if id_car else "N/A"
        id_val_str = str(id_val).replace("'", "") if id_val else "N/A"

        # Create the metadata injection tag
        # We use a specific [META ...] format that the prompt is trained to recognize
        meta_tag = f"[META id_c='{id_car_str}' id_v='{id_val_str}']"

        # Build the natural language sentence
        # Ex: "Type de structure: Colonnes mobiles. [META ...]"
        # Ex with unit: "Capacité: 7000 kg. [META ...]"

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
    Combines name, description, and other relevant fields.
    """
    # 1. Characteristics Priority
    caracteristics = product_data.get("caracteristics", [])
    if isinstance(caracteristics, list) and len(caracteristics) > 0:
        chars_text = _format_characteristics_to_text(caracteristics)
        if chars_text.strip():
            return chars_text

    # 2. Description Priority
    description = product_data.get("description", "")
    nom_produit = product_data.get("nom_produit", "")

    if description and description.strip():
        parts = []
        if nom_produit:
            parts.append(f"Produit: {nom_produit}")
        parts.append(f"Description: {description}")
        return "\n".join(parts)

    # 3. Fallback Priority
    return ""
