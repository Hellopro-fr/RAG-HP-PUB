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

    async def batch_get_nodes(
        self,
        label: str,
        raw_ids: List[int],
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves multiple nodes for a given label in a single Cypher query.

        Uses `WHERE n.id IN $ids` for a single index scan (no per-id round-trip).
        Projects only the requested `fields` at the database level via a
        Cypher list comprehension (no APOC needed) to keep response size small.

        Args:
            label (str): The node label (e.g., 'Produit').
            raw_ids (List[int]): Raw node IDs (without label prefix).
            fields (Optional[List[str]]): Property names to return per node.
                Defaults to ['id_produit', 'id'] when None.

        Returns:
            Dict[str, Any]: {"found": [{"id": raw_id, "node": {...}}], "missing": [raw_id, ...]}.
        """
        # Security check: Ensure label is alphanumeric to prevent Cypher injection
        if not label.isalnum():
            logging.warning(f"Invalid label format: {label}")
            raise ValueError("Invalid node label format. Must be alphanumeric.")

        if not raw_ids:
            return {"found": [], "missing": []}

        if fields is None:
            fields = ["id_produit", "id"]

        # Map full (prefixed) IDs back to the caller's raw IDs for the response
        full_ids: List[str] = [self._format_node_id(label, rid) for rid in raw_ids]
        id_to_raw: Dict[str, int] = dict(zip(full_ids, raw_ids))

        # Single index scan + DB-side projection. The list comprehension only
        # picks keys present in $fields; field names are passed as a parameter
        # (not interpolated) so this is safe from Cypher injection.
        query = f"""
        MATCH (n:{label})
        WHERE n.id IN $ids
        RETURN n.id AS id,
               [k IN keys(n) WHERE k IN $fields | [k, n[k]]] AS props
        """

        params = {"ids": full_ids, "fields": fields}

        try:
            logging.info(
                f"Batch fetching {len(full_ids)} nodes of label {label} "
                f"with fields={fields}"
            )
            results = await clients.execute_cypher(query, params, read_only=True)

            found_full_ids = {r.get("id") for r in results if r.get("id")}
            found = []
            for r in results:
                full_id = r.get("id")
                if full_id not in id_to_raw:
                    continue
                props_pairs = r.get("props") or []
                node_dict = {k: v for k, v in props_pairs}
                found.append({"id": id_to_raw[full_id], "node": node_dict})

            missing = [
                id_to_raw[fid] for fid in full_ids if fid not in found_full_ids
            ]
            return {"found": found, "missing": missing}

        except Exception as e:
            logging.error(
                f"Error batch fetching nodes for label {label}: {e}", exc_info=True
            )
            raise e

    async def batch_update_nodes(
        self, label: str, items: List[Any]
    ) -> Dict[str, Any]:
        """
        Updates multiple nodes for a given label in a single Cypher transaction.

        Uses UNWIND + indexed MATCH so the whole batch runs as one query in one
        transaction. Any Cypher-level failure rolls back the entire batch.

        Args:
            label (str): The node label (e.g., 'Produit').
            items (List[BatchUpdateItem]): Items with .id (raw) and .properties.

        Returns:
            Dict[str, Any]: {"found": [{"id": raw_id, "node": {...}}], "missing": [raw_id, ...]}.
        """
        # Security check: Ensure label is alphanumeric to prevent Cypher injection
        if not label.isalnum():
            logging.warning(f"Invalid label format: {label}")
            raise ValueError("Invalid node label format. Must be alphanumeric.")

        if not items:
            return {"found": [], "missing": []}

        updates: List[Dict[str, Any]] = []
        raw_by_full: Dict[str, str] = {}
        for it in items:
            full_id = self._format_node_id(label, it.id)
            updates.append({"id": full_id, "props": it.properties or {}})
            raw_by_full[full_id] = it.id

        query = f"""
        UNWIND $updates AS u
        MATCH (n:{label} {{id: u.id}})
        SET n += u.props
        RETURN n.id AS id, n
        """

        params = {"updates": updates}

        try:
            logging.info(
                f"Batch updating {len(updates)} nodes of label {label} "
                f"in a single Cypher transaction"
            )
            results = await clients.execute_cypher(query, params, read_only=False)

            found_full_ids = {r.get("id") for r in results if r.get("id")}
            found = [
                {"id": raw_by_full[r["id"]], "node": r.get("n")}
                for r in results
                if r.get("id") in raw_by_full
            ]
            missing = [
                raw_by_full[u["id"]]
                for u in updates
                if u["id"] not in found_full_ids
            ]
            return {"found": found, "missing": missing}

        except Exception as e:
            logging.error(
                f"Error batch updating nodes for label {label}: {e}", exc_info=True
            )
            raise e

    async def batch_upsert_nodes(
        self,
        label: str,
        raw_ids: List[int],
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply the SAME properties to many existing nodes in a single Cypher query.

        Semantics: match-only (no node creation). Equivalent to
        `UPDATE n SET props WHERE n.id IN ids` in SQL terms. IDs that don't
        match an existing node are returned in `missing`.

        Args:
            label (str): Node label (e.g., 'Produit').
            raw_ids (List[str]): Raw node IDs (without label prefix).
            properties (Dict[str, Any]): Properties merged into every matched node.

        Returns:
            Dict[str, Any]: {"found": [{"id": raw_id, "node": {...}}], "missing": [...]}.
        """
        # Security check: Ensure label is alphanumeric to prevent Cypher injection
        if not label.isalnum():
            logging.warning(f"Invalid label format: {label}")
            raise ValueError("Invalid node label format. Must be alphanumeric.")

        if not raw_ids:
            return {"found": [], "missing": []}

        if not properties:
            # No-op: nothing to set. Report every id as "missing" so the caller
            # can detect they sent an empty patch.
            logging.info(
                f"No properties supplied for batch_upsert_nodes({label}) — no-op"
            )
            return {"found": [], "missing": list(raw_ids)}

        full_ids: List[str] = [self._format_node_id(label, rid) for rid in raw_ids]
        id_to_raw: Dict[str, int] = dict(zip(full_ids, raw_ids))

        # Single index scan + single SET. Same $props applied to every match.
        query = f"""
        MATCH (n:{label})
        WHERE n.id IN $ids
        SET n += $props
        RETURN n.id AS id, n
        """

        params = {"ids": full_ids, "props": properties}

        try:
            logging.info(
                f"Batch upsert {len(full_ids)} nodes of label {label} "
                f"with {len(properties)} props (uniform)"
            )
            results = await clients.execute_cypher(query, params, read_only=False)

            found_full_ids = {r.get("id") for r in results if r.get("id")}
            found = [
                {"id": id_to_raw[r["id"]], "node": r.get("n")}
                for r in results
                if r.get("id") in id_to_raw
            ]
            missing = [
                id_to_raw[fid] for fid in full_ids if fid not in found_full_ids
            ]
            return {"found": found, "missing": missing}

        except Exception as e:
            logging.error(
                f"Error batch upserting nodes for label {label}: {e}",
                exc_info=True,
            )
            raise e

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
