from typing import List, Dict, Any, Tuple, Optional

from infrastructure.neo4j_connector import neo4j_connector


class GraphDatabaseUseCase:
    """
    Application layer use case for graph database operations.
    Orchestrates Neo4j connector calls.
    """

    def __init__(self):
        self.connector = neo4j_connector

    def execute_cypher(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        read_only: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Execute a single Cypher query.

        Returns:
            Tuple of (results, records_affected)
        """
        return self.connector.execute_cypher(query, parameters, read_only)

    def execute_batch_cypher(
        self, statements: List[Tuple[str, Dict[str, Any]]], transactional: bool = True
    ) -> List[Tuple[bool, str, int]]:
        """
        Execute multiple Cypher statements in batch.

        Returns:
            List of (success, error_message, records_affected) for each statement
        """
        return self.connector.execute_batch_cypher(statements, transactional)

    def get_schema(
        self, include_properties: bool = True, include_indexes: bool = True
    ) -> Dict[str, Any]:
        """
        Get graph schema information.
        """
        return self.connector.get_schema_info(include_properties, include_indexes)

    def setup_schema(
        self, apply_constraints: bool = True, apply_indexes: bool = True
    ) -> Tuple[List[str], List[str]]:
        """
        Setup constraints and indexes.

        Returns:
            Tuple of (applied_constraints, applied_indexes)
        """
        return self.connector.setup_constraints()
