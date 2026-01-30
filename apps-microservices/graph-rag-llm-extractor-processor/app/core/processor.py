import json
import re
import logging
from typing import Dict, Any, List, Optional

from app.core.prompts import PROMPT_MAP
from app.infrastructure.llm_client import llm_client
from common_utils.grpc_clients import spacy_client


async def _lemmatize_label(label: str) -> str:
    """
    Lemmatizes a label string using the centralized spaCy gRPC service.
    This normalizes labels to their base form for better deduplication.

    Example: "Hauteurs de levée maximales" -> "hauteur de lever maximal"
    """
    if not label:
        return label

    try:
        tokens = await spacy_client.lemmatize(label.lower())
        if tokens:
            return " ".join([token.lemma for token in tokens])
        return label.lower()
    except Exception as e:
        logging.warning(
            f"Lemmatization failed for '{label}': {e}. Using lowercase fallback."
        )
        return label.lower()


async def _lemmatize_node_labels(nodes: List[Dict]) -> List[Dict]:
    """
    Lemmatizes the 'label' property in all nodes and adds a 'label_lemma' property.
    This prepares labels for semantic deduplication in the vigil processor.
    """
    for node in nodes:
        props = node.get("properties", {})
        original_label = props.get("label", "")

        if original_label:
            # Add lemmatized version for deduplication
            lemma = await _lemmatize_label(original_label)
            props["label_lemma"] = lemma
            logging.info(f"Lemmatized label: '{original_label}' -> '{lemma}'")

    return nodes


def validate_nodes_have_source_id(nodes: List[Dict]) -> tuple[bool, List[str]]:
    """
    Validates that all nodes contain id_source_caracteristique in their properties.

    Returns:
        - (True, []) if all nodes have the property
        - (False, [list of node ids missing the property]) if any are missing
    """
    missing_nodes = []
    for node in nodes:
        props = node.get("properties", {})
        if "id_source_caracteristique" not in props or not props.get(
            "id_source_caracteristique"
        ):
            missing_nodes.append(node.get("id", "unknown"))

    return (len(missing_nodes) == 0, missing_nodes)


async def extract_entities_and_relationships(
    data: Dict[str, Any], database: str = "neo4j", origin: str = "bo"
) -> Dict[str, Any]:
    """
    Extract entities and relationships from text using LLM.

    Args:
        data: Input data containing text_for_extraction and metadata
        database: Target database
        origin: Data origin

    Returns:
        Output message with extracted nodes and relationships
    """
    source_type = data.get("source_type", "Produit")
    text = data.get("text_for_extraction", "")
    graph_id = data.get("graph_id", "")

    if not text:
        logging.warning(f"No text to extract for {graph_id}")
        return _build_output(data, [], [], database, origin)

    # Get appropriate prompt
    prompt_config = PROMPT_MAP.get(source_type, PROMPT_MAP["Produit"])
    prompt = prompt_config["prompt"]

    logging.info(f"Extracting entities from {source_type}: {graph_id}")

    # Call LLM
    llm_response = await llm_client.generate(prompt, text)

    if not llm_response:
        logging.error(f"LLM returned empty response for {graph_id}")
        return _build_output(data, [], [], database, origin)

    # Parse JSON from response
    nodes, relationships = _parse_llm_response(llm_response, graph_id)

    # Apply category prefix to node IDs and labels
    id_categorie = data.get("id_categorie", "")
    if id_categorie:
        nodes, relationships = _apply_category_prefix(
            nodes, relationships, id_categorie
        )

    # Lemmatize labels for semantic deduplication
    nodes = await _lemmatize_node_labels(nodes)

    # Replace source placeholder with actual graph_id
    relationships = _replace_source_placeholder(relationships, graph_id)

    # Validate that all nodes have id_source_caracteristique
    is_valid, missing_nodes = validate_nodes_have_source_id(nodes)
    if not is_valid:
        logging.warning(
            f"⚠️ Validation failed for {graph_id}: {len(missing_nodes)} nodes missing id_source_caracteristique: {missing_nodes}"
        )

    logging.info(
        f"Extracted {len(nodes)} nodes and {len(relationships)} relationships for {graph_id}"
    )

    return _build_output(
        data,
        nodes,
        relationships,
        database,
        origin,
        validation_failed=not is_valid,
        missing_nodes=missing_nodes,
    )


def _parse_llm_response(response: str, graph_id: str) -> tuple:
    """Parse LLM response and extract nodes/relationships."""

    # 1. Clean DeepSeek/Chain-of-Thought tags
    # DeepSeek often outputs <think>...</think> before the JSON
    cleaned_response = re.sub(
        r"<think>.*?</think>", "", response, flags=re.DOTALL
    ).strip()

    try:
        json_str = ""

        # 2. Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 3. Fallback: Try to find the first '{' and last '}'
            # This handles cases where the LLM chats before/after the JSON without markdown
            start_idx = cleaned_response.find("{")
            end_idx = cleaned_response.rfind("}")

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = cleaned_response[start_idx : end_idx + 1]
            else:
                # 4. Last resort: use the cleaned string as is
                json_str = cleaned_response

        parsed = json.loads(json_str)
        nodes = parsed.get("nodes", [])
        relationships = parsed.get("relationships", [])

        return nodes, relationships

    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse LLM response for {graph_id}: {e}")
        # Log the raw response to help debugging
        logging.error(
            f"--- RAW RESPONSE START ---\n{response}\n--- RAW RESPONSE END ---"
        )
        logging.error(
            f"--- CLEANED JSON ATTEMPT ---\n{json_str if 'json_str' in locals() else 'N/A'}\n--- END ---"
        )
        return [], []


def _replace_source_placeholder(relationships: List[Dict], graph_id: str) -> List[Dict]:
    """Replace {source_placeholder} with actual graph_id in relationships."""
    for rel in relationships:
        if rel.get("source") == "{source_placeholder}":
            rel["source"] = graph_id
    return relationships


def _apply_category_prefix(
    nodes: List[Dict], relationships: List[Dict], id_categorie: str
) -> tuple:
    """
    Apply category prefix to node IDs and labels.

    Prefixes:
    - Node IDs: categorie_{id_categorie}_{original_id}
    - Node labels: categorie_{id_categorie}_{original_label}
    - Relationship targets: updated to match new node IDs
    """
    prefix = f"categorie_{id_categorie}_"
    id_mapping = {}  # Map old IDs to new IDs

    # Process nodes
    for node in nodes:
        old_id = node.get("id", "")
        if old_id:
            new_id = f"{prefix}{old_id}"
            id_mapping[old_id] = new_id
            node["id"] = new_id

        # Prefix the label property
        props = node.get("properties", {})

        # Ensure label_id exists (derived from label if needed)
        old_label_id = props.get("label_id", "")
        if old_label_id:
            props["label_id"] = f"{prefix}{old_label_id}"
        else:
            original_label = props.get("label", "")
            if original_label:
                props["label_id"] = f"{prefix}{original_label}"

    # Update relationship targets to match new node IDs
    for rel in relationships:
        old_target = rel.get("target", "")
        if old_target in id_mapping:
            rel["target"] = id_mapping[old_target]

    return nodes, relationships


def _build_output(
    data: Dict[str, Any],
    nodes: List[Dict],
    relationships: List[Dict],
    database: str,
    origin: str,
    validation_failed: bool = False,
    missing_nodes: List[str] = None,
) -> Dict[str, Any]:
    """Build output message for next processor."""
    return {
        "data": {
            "graph_id": data.get("graph_id", ""),
            "id_produit": data.get("id_produit", ""),
            "id_categorie": data.get("id_categorie", ""),
            "source_type": data.get("source_type", "Produit"),
            "nodes": nodes,
            "relationships": relationships,
        },
        "database": database,
        "origin": origin,
        "extraction_success": len(nodes) > 0,
        "validation_failed": validation_failed,
        "missing_nodes": missing_nodes or [],
    }
