import logging
from typing import Optional, List, Dict, Any, Tuple

from langchain_community.graphs import Neo4jGraph
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.config import settings


class Neo4jConnector:
    """
    Singleton connector for Neo4j database operations.
    Provides both LangChain Neo4jGraph for schema introspection and
    native driver for raw Cypher execution.
    Includes connection health checks and auto-reconnect for cloud deployments.
    """

    _instance = None
    _graph: Optional[Neo4jGraph] = None
    _driver = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Neo4jConnector, cls).__new__(cls)
            # Suppress Neo4j driver warnings (like UnknownRelationshipTypeWarning)
            logging.getLogger("neo4j").setLevel(logging.ERROR)
        return cls._instance

    def _reset_connections(self):
        """Reset all cached connections to force reconnection."""
        logging.info("Resetting Neo4j connections...")
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None
        self._graph = None

    def _verify_driver_connection(self) -> bool:
        """Verify the driver connection is healthy."""
        if self._driver is None:
            return False
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            logging.warning(f"Driver connection verification failed: {e}")
            return False

    def get_graph(self) -> Neo4jGraph:
        """Get LangChain Neo4jGraph instance for schema operations."""
        if self._graph is None:
            self._graph = Neo4jGraph(
                url=settings.NEO4J_URI,
                username=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
                database=settings.NEO4J_DATABASE,
            )
        return self._graph

    def get_driver(self):
        """Get native Neo4j driver for direct operations with connection verification."""
        # If driver exists, verify it's still healthy
        if self._driver is not None:
            if not self._verify_driver_connection():
                logging.warning("Neo4j driver connection stale, reconnecting...")
                self._reset_connections()

        if self._driver is None:
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                max_connection_lifetime=300,  # 5 minutes max connection lifetime
                connection_acquisition_timeout=30,  # 30 seconds to acquire connection
                connection_timeout=30,  # 30 seconds connection timeout
            )
        return self._driver

    def execute_cypher(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        read_only: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Execute a single Cypher query and return results.
        Includes retry logic for connection issues.

        Returns:
            Tuple of (results_list, records_affected)
        """
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                graph = self.get_graph()
                if parameters.top_k:
                    parameters.top_k = int(parameters.top_k)
                results = graph.query(query, params=parameters or {})
                records_affected = len(results) if results else 0
                return results, records_affected
            except (ServiceUnavailable, OSError) as e:
                last_error = e
                logging.warning(f"Neo4j connection error (attempt {attempt + 1}): {e}")
                self._reset_connections()
            except Exception as e:
                logging.error(f"Cypher execution error: {e}")
                raise

        # If we get here, all retries failed
        logging.error(
            f"Cypher execution failed after {max_retries} attempts: {last_error}"
        )
        raise last_error

    def execute_batch_cypher(
        self, statements: List[Tuple[str, Dict[str, Any]]], transactional: bool = True
    ) -> List[Tuple[bool, str, int]]:
        """
        Execute multiple Cypher statements in batch.
        Includes retry logic for connection issues.

        Args:
            statements: List of (query, parameters) tuples
            transactional: If True, rollback all on any failure

        Returns:
            List of (success, error_message, records_affected) for each statement
        """
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                return self._execute_batch_internal(statements, transactional)
            except (ServiceUnavailable, OSError) as e:
                last_error = e
                logging.warning(
                    f"Neo4j connection error in batch (attempt {attempt + 1}): {e}"
                )
                self._reset_connections()
            except Exception as e:
                logging.error(f"Batch execution error: {e}")
                raise

        # If we get here, all retries failed
        logging.error(
            f"Batch execution failed after {max_retries} attempts: {last_error}"
        )
        return [(False, str(last_error), 0) for _ in statements]

    def _execute_batch_internal(
        self, statements: List[Tuple[str, Dict[str, Any]]], transactional: bool
    ) -> List[Tuple[bool, str, int]]:
        """Internal batch execution logic."""
        driver = self.get_driver()
        results = []

        with driver.session(database=settings.NEO4J_DATABASE) as session:
            if transactional:
                # Run all in a single transaction
                try:
                    with session.begin_transaction() as tx:
                        for query, params in statements:
                            try:
                                result = tx.run(query, params or {})
                                summary = result.consume()
                                affected = (
                                    summary.counters.nodes_created
                                    + summary.counters.nodes_deleted
                                    + summary.counters.relationships_created
                                    + summary.counters.relationships_deleted
                                    + summary.counters.properties_set
                                )
                                results.append((True, "", affected))
                            except Neo4jError as e:
                                # Rollback entire transaction
                                tx.rollback()
                                # Mark this and remaining as failed
                                results.append((False, str(e), 0))
                                for _ in range(len(statements) - len(results)):
                                    results.append(
                                        (False, "Rolled back due to previous error", 0)
                                    )
                                return results
                        tx.commit()
                except Exception as e:
                    logging.error(f"Batch transaction error: {e}")
                    if len(results) < len(statements):
                        for _ in range(len(statements) - len(results)):
                            results.append((False, str(e), 0))
                    raise  # Re-raise for retry logic
            else:
                # Run each statement independently
                for query, params in statements:
                    try:
                        result = session.run(query, params or {})
                        summary = result.consume()
                        affected = (
                            summary.counters.nodes_created
                            + summary.counters.nodes_deleted
                            + summary.counters.relationships_created
                            + summary.counters.relationships_deleted
                            + summary.counters.properties_set
                        )
                        results.append((True, "", affected))
                    except Neo4jError as e:
                        results.append((False, str(e), 0))

        return results

    def get_schema_info(
        self, include_properties: bool = True, include_indexes: bool = True
    ) -> Dict[str, Any]:
        """
        Get graph schema information.

        Returns:
            Dictionary with node_labels, relationship_types, and schema_text
        """
        graph = self.get_graph()

        # Refresh schema to get latest
        graph.refresh_schema()

        schema_info = {
            "node_labels": [],
            "relationship_types": [],
            "schema_text": graph.schema,
        }

        # Get node labels with properties
        if include_properties:
            node_query = """
            CALL db.schema.nodeTypeProperties() 
            YIELD nodeType, nodeLabels, propertyName, propertyTypes
            RETURN nodeLabels, propertyName, propertyTypes
            """
            try:
                node_results = graph.query(node_query)
                labels_dict = {}
                for row in node_results:
                    label = row.get("nodeLabels", ["Unknown"])[0]
                    prop_name = row.get("propertyName")
                    prop_types = row.get("propertyTypes", ["Unknown"])

                    if label not in labels_dict:
                        labels_dict[label] = {"name": label, "properties": []}

                    if prop_name:
                        labels_dict[label]["properties"].append(
                            {
                                "name": prop_name,
                                "data_type": prop_types[0] if prop_types else "Unknown",
                                "indexed": False,
                                "unique": False,
                            }
                        )

                schema_info["node_labels"] = list(labels_dict.values())
            except Exception as e:
                logging.warning(f"Could not get node properties: {e}")

        # Get relationship types
        rel_query = """
        CALL db.schema.relTypeProperties()
        YIELD relType, propertyName, propertyTypes
        RETURN relType, propertyName, propertyTypes
        """
        try:
            rel_results = graph.query(rel_query)
            rels_dict = {}
            for row in rel_results:
                rel_type = (
                    row.get("relType", "UNKNOWN").replace(":`", "").replace("`", "")
                )
                prop_name = row.get("propertyName")
                prop_types = row.get("propertyTypes", [])

                if rel_type not in rels_dict:
                    rels_dict[rel_type] = {
                        "name": rel_type,
                        "source_label": "",
                        "target_label": "",
                        "properties": [],
                    }

                if prop_name:
                    rels_dict[rel_type]["properties"].append(
                        {
                            "name": prop_name,
                            "data_type": prop_types[0] if prop_types else "Unknown",
                            "indexed": False,
                            "unique": False,
                        }
                    )

            schema_info["relationship_types"] = list(rels_dict.values())
        except Exception as e:
            logging.warning(f"Could not get relationship properties: {e}")

        # Get index information
        if include_indexes:
            try:
                index_query = "SHOW INDEXES"
                index_results = graph.query(index_query)
                index_map = {}
                for row in index_results:
                    labels = row.get("labelsOrTypes", [])
                    props = row.get("properties", [])
                    is_unique = row.get("uniqueness", "NONUNIQUE") == "UNIQUE"

                    for label in labels:
                        if label not in index_map:
                            index_map[label] = {}
                        for prop in props:
                            index_map[label][prop] = {
                                "indexed": True,
                                "unique": is_unique,
                            }

                # Update node labels with index info
                for node_label in schema_info["node_labels"]:
                    label_name = node_label["name"]
                    if label_name in index_map:
                        for prop in node_label["properties"]:
                            if prop["name"] in index_map[label_name]:
                                prop["indexed"] = index_map[label_name][prop["name"]][
                                    "indexed"
                                ]
                                prop["unique"] = index_map[label_name][prop["name"]][
                                    "unique"
                                ]
            except Exception as e:
                logging.warning(f"Could not get index info: {e}")

        return schema_info

    def setup_constraints(self) -> Tuple[List[str], List[str]]:
        """
        Apply unique constraints and indexes to the graph.

        Returns:
            Tuple of (applied_constraints, applied_indexes)
        """
        graph = self.get_graph()
        applied_constraints = []
        applied_indexes = []

        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Fournisseur) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Produit) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Categorie) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Question) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Reponse) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Devis) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:PageWeb) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Acheteur) REQUIRE n.id IS UNIQUE",
        ]

        indexes = [
            # Anchor & Filtering
            "CREATE INDEX reponse_id_index IF NOT EXISTS FOR (n:Reponse) ON (n.id_reponse)",
            "CREATE INDEX produit_categorie_index IF NOT EXISTS FOR (n:Produit) ON (n.id_categorie)",
            "CREATE INDEX produit_id_produit_index IF NOT EXISTS FOR (n:Produit) ON (n.id_produit)",
            # Characteristic Matching
            "CREATE INDEX char_source_id_index IF NOT EXISTS FOR (n:CaracteristiqueTechnique) ON (n.id_source_caracteristique)",
            "CREATE INDEX char_source_valeur_index IF NOT EXISTS FOR (n:CaracteristiqueTechnique) ON (n.id_source_valeur)",
            "CREATE INDEX char_valeur_index IF NOT EXISTS FOR (n:CaracteristiqueTechnique) ON (n.valeur)",
            "CREATE INDEX char_type_donnee_index IF NOT EXISTS FOR (n:CaracteristiqueTechnique) ON (n.type_donnee)",
            # Characteristic Scoring (Numeric/Canonical)
            "CREATE INDEX char_unite_canonique_index IF NOT EXISTS FOR (n:CaracteristiqueTechnique) ON (n.unite_canonique)",
            "CREATE INDEX char_valeur_canonique_index IF NOT EXISTS FOR (n:CaracteristiqueTechnique) ON (n.valeur_canonique)",
            "CREATE INDEX char_valeur_min_canonique_index IF NOT EXISTS FOR (n:CaracteristiqueTechnique) ON (n.valeur_min_canonique)",
            "CREATE INDEX char_valeur_max_canonique_index IF NOT EXISTS FOR (n:CaracteristiqueTechnique) ON (n.valeur_max_canonique)",
        ]

        logging.info("Applying Neo4j Unique Constraints...")
        for query in constraints:
            try:
                graph.query(query)
                applied_constraints.append(query)
            except Exception as e:
                logging.warning(f"Failed to apply constraint: {query}. Error: {e}")

        logging.info("Applying Neo4j Indexes...")
        for query in indexes:
            try:
                graph.query(query)
                applied_indexes.append(query)
            except Exception as e:
                logging.warning(f"Failed to apply index: {query}. Error: {e}")

        logging.info(
            f"Applied {len(applied_constraints)} constraints and {len(applied_indexes)} indexes."
        )
        return applied_constraints, applied_indexes

    def close(self):
        """Close all connections."""
        if self._driver:
            self._driver.close()
            self._driver = None
        if self._graph:
            self._graph = None


# Singleton instance
neo4j_connector = Neo4jConnector()
