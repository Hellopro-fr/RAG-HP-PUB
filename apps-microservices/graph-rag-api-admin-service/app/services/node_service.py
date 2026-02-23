import logging
from typing import Dict, Any, Optional, List
from app.infrastructure.clients import clients


class NodeService:
    def _format_node_id(self, label: str, node_id: str) -> str:
        """
        Formats the node ID based on the label.
        """
        match label:
            case "Produit":
                return f"id_produit_{node_id}"
            case "Fournisseur":
                return f"id_fournisseur_{node_id}"
            case "Categorie":
                return f"id_categorie_{node_id}"
            case _:
                raise ValueError(
                    f"Invalid node label: {label}. Allowed: Produit, Fournisseur, Categorie"
                )

    async def update_node(
        self, label: str, node_id: str, properties: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Updates a specific node in the graph database.

        Args:
            label (str): The label of the node (e.g., 'Produit', 'Fournisseur').
            node_id (str): The ID of the node to update. Assumes the node has an 'id' property.
            properties (Dict[str, Any]): Dictionary of properties to update.

        Returns:
            Optional[Dict[str, Any]]: The updated node properties if successful, None otherwise.
        """
        # Security check: Ensure label is alphanumeric to prevent Cypher injection
        if not label.isalnum():
            logging.warning(f"Invalid label format: {label}")
            raise ValueError("Invalid node label format. Must be alphanumeric.")

        if not properties:
            logging.info(f"No properties to update for node {label} {node_id}")
            return None

        # Format the node ID based on label-specific prefixes
        node_id = self._format_node_id(label, node_id)

        # Construct Cypher query
        # We use f-string for label because labels cannot be parameterized in Cypher
        # We use existing 'id' constraint field for lookup
        query = f"""
        MATCH (n:{label} {{id: $id}})
        SET n += $props
        RETURN n
        """

        params = {"id": node_id, "props": properties}

        try:
            logging.info(
                f"Updating node {label} {node_id} with properties: {properties.keys()}"
            )

            # Use read_only=False to allow write operations
            results = await clients.execute_cypher(query, params, read_only=False)

            if results:
                # results is a list of dicts. Each dict contains key "n".
                # The value of "n" is the node object/dict.
                updated_node = results[0].get("n")
                return updated_node

            logging.info(f"Node {label} with id {node_id} not found or update failed.")
            return None

        except Exception as e:
            logging.error(f"Error updating node {label} {node_id}: {e}", exc_info=True)
            raise e

    async def get_node_schema(self, label: str) -> List[Dict[str, Any]]:
        """
        Retrieves the schema (property names and types) for a given node label.

        Args:
            label (str): The node label (e.g., 'Produit').

        Returns:
            List[Dict[str, Any]]: A list of property definitions.
        """
        # Security check: Ensure label is alphanumeric to prevent Cypher injection
        if not label.isalnum():
            logging.warning(f"Invalid label format: {label}")
            raise ValueError("Invalid node label format. Must be alphanumeric.")

        # Cypher query using db.schema.nodeTypeProperties()
        # Note: The 'nodeType' returned by this procedure is a string formatted like ":Label"
        # We need to construct the expected nodeType string.
        formatted_node_type = f":`{label}`"

        query = """
        CALL db.schema.nodeTypeProperties()
        YIELD nodeType, propertyName, propertyTypes, mandatory
        WHERE nodeType = $nodeType
        RETURN propertyName, propertyTypes, mandatory
        """

        params = {"nodeType": formatted_node_type}

        try:
            logging.info(f"Fetching schema for label: {label}")
            # Use read_only=True for schema retrieval
            results = await clients.execute_cypher(query, params, read_only=True)

            schema = []
            if results:
                for record in results:
                    # Assumes results are list of dict-like objects
                    item = {
                        "property": record.get("propertyName"),
                        "type": record.get("propertyTypes"),
                        "mandatory": record.get("mandatory"),
                    }
                    schema.append(item)

            return schema

        except Exception as e:
            logging.error(f"Error fetching schema for {label}: {e}", exc_info=True)
            # Return empty list or re-raise depending on desired behavior.
            # Returning empty list implies no schema found or error.
            return []

    async def get_node(self, label: str, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a specific node from the graph database.

        Args:
            label (str): The label of the node (e.g., 'Produit').
            node_id (str): The ID of the node.

        Returns:
            Optional[Dict[str, Any]]: The node properties if found, None otherwise.
        """
        # Security check: Ensure label is alphanumeric to prevent Cypher injection
        if not label.isalnum():
            logging.warning(f"Invalid label format: {label}")
            raise ValueError("Invalid node label format. Must be alphanumeric.")

        formatted_id = self._format_node_id(label, node_id)

        query = f"""
        MATCH (n:{label} {{id: $id}})
        RETURN n
        """

        params = {"id": formatted_id}

        try:
            # Use read_only=True for retrieval
            results = await clients.execute_cypher(query, params, read_only=True)

            if results:
                # results is a list of dicts. Each dict contains key "n".
                # The value of "n" is the node object/dict.
                return results[0].get("n")

            return None

        except Exception as e:
            logging.error(f"Error fetching node {label} {node_id}: {e}", exc_info=True)
            raise e


node_service = NodeService()
