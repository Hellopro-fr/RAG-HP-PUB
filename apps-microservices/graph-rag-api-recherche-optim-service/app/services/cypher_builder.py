import logging
import json
import re
from typing import Dict, Any, List, Tuple, Optional

from app.infrastructure.clients import clients
from app.infrastructure.llm_service import llm_service
from app.services.rag_components import ENTITY_EXTRACTION_TEMPLATE
from app.config import settings


class CypherBuilderService:
    RELATIONSHIP_DIRECTIONS = {
        "Produit->Fournisseur": "-[:EST_PROPOSE_PAR]->",
        "Fournisseur->Produit": "<-[:EST_PROPOSE_PAR]-",
        "Produit->Categorie": "-[:APPARTIENT_A]->",
        "Categorie->Produit": "<-[:APPARTIENT_A]-",
        "Produit->CaracteristiqueTechnique": "-[:A_POUR_CARACTERISTIQUE]->",
        "Fournisseur->Categorie": "-[:A_POUR_CATEGORIE_PHARE]->",
        "Categorie->Fournisseur": "<-[:A_POUR_CATEGORIE_PHARE]-",
    }

    def __init__(self):
        self.schema_text = ""

    async def _refresh_schema(self):
        if not self.schema_text:
            self.schema_text = await clients.get_graph_schema()

    def get_search_subject(self, extracted_data: Dict[str, Any]) -> Optional[str]:
        """
        Extracts a clean search subject (e.g., 'chariot élévateur') from the LLM extracted JSON.
        """
        if not extracted_data or "entities" not in extracted_data:
            return None

        subjects = []
        for entity in extracted_data["entities"]:
            e_type = entity.get("type")
            if e_type in ["Produit", "Categorie"]:
                for f in entity.get("filters", []):
                    prop = f.get("property")
                    val = f.get("value")
                    if (
                        prop in ["nom_produit", "categorie", "description", "nom"]
                        and val
                    ):
                        subjects.append(str(val))

        if subjects:
            return " ".join(subjects)
        return None

    async def _perform_semantic_expansion(
        self, value: str, node_type: str
    ) -> List[str]:
        """
        Expands a textual value into a list of canonical entity IDs using semantic search via gRPC.
        """
        logging.info(f"Performing semantic expansion for value: '{value}'")
        try:
            vector = await clients.get_embedding(value)
            if not vector:
                return []

            similar_results = await clients.search_vectors(
                vector,
                node_type=node_type,
                top_k=settings.QUERY_SEMANTIC_TOP_K,
                threshold=settings.QUERY_SEMANTIC_THRESHOLD,
            )

            if not similar_results:
                return []

            ids = [result["id"] for result in similar_results]
            return ids
        except Exception as e:
            logging.error(f"Error during semantic expansion for '{value}': {e}")
            return []

    async def _generate_where_conditions(
        self, alias: str, entity_type: str, filters: List[Dict], param_start_index: int
    ) -> Tuple[List[str], Dict[str, Any], int]:
        """
        Generates Cypher WHERE clauses from a list of filters.
        """
        where_clauses = []
        params = {}
        param_counter = param_start_index

        for f in filters:
            prop = f.get("property")
            op = f.get("operator")
            val = f.get("value")
            label = f.get("label")

            if not all([prop, op, val is not None]):
                continue

            # 1. Semantic Characteristic Search
            if op == "CONTAINS" and entity_type == "CaracteristiqueTechnique" and label:
                search_text = f"{label} : {val}"
                vector = await clients.get_embedding(search_text)
                if vector:
                    char_results = await clients.search_similar_characteristics(
                        vector, top_k=5, threshold=settings.QUERY_SEMANTIC_THRESHOLD
                    )
                    char_ids = [res["id"] for res in char_results]
                    if char_ids:
                        param_name = f"semantic_char_ids_{param_counter}"
                        where_clauses.append(f"{alias}.id IN ${param_name}")
                        params[param_name] = char_ids
                        param_counter += 1
                        continue

                # Fallback to text search
                param_name = f"fallback_char_val_{param_counter}"
                where_clauses.append(
                    f"toLower(toString({alias}.nom)) CONTAINS toLower(${param_name})"
                )
                params[param_name] = str(val)
                param_counter += 1

            # 2. Semantic Entity Search
            elif op == "CONTAINS" and prop in [
                "nom",
                "valeur",
                "label",
                "nom_produit",
                "categorie",
                "fournisseur",
            ]:
                candidate_ids = await self._perform_semantic_expansion(
                    str(val), entity_type
                )
                if candidate_ids:
                    param_name = f"semantic_ids_{param_counter}"
                    where_clauses.append(f"{alias}.id IN ${param_name}")
                    params[param_name] = candidate_ids
                    param_counter += 1
                else:
                    param_name = f"fallback_val_{param_counter}"
                    where_clauses.append(
                        f"toLower(toString({alias}.{prop})) CONTAINS toLower(${param_name})"
                    )
                    params[param_name] = str(val)
                    param_counter += 1

            # 3. Numeric/Range Comparison with Normalization
            elif (
                op in ["=", ">", "<", ">=", "<="]
                and entity_type == "CaracteristiqueTechnique"
                and label
            ):
                # Call Normalization Service via gRPC
                normalized_result = await clients.normalize_quantity(
                    str(val), None, label
                )

                if normalized_result:
                    canonical_val = normalized_result["valeur_canonique"]
                    canonical_unit = normalized_result["unite_canonique"]

                    slugified_label = re.sub(r"[\s/:]+", "_", label.lower())
                    label_id_stub = f"label_{slugified_label}"

                    label_id_param = f"label_id_{param_counter}"
                    value_param = f"norm_val_{param_counter}"
                    unit_param = f"norm_unit_{param_counter}"

                    base_condition = f"{alias}.label_id CONTAINS ${label_id_param} AND {alias}.unite_canonique = ${unit_param}"

                    # Logic for Numeric vs Range nodes (same as V4 logic)
                    if op in [">", ">="]:
                        clause = f"""(
                            ({base_condition} AND {alias}.type_donnee = 'numeric' AND {alias}.valeur_canonique {op} ${value_param})
                            OR
                            ({base_condition} AND {alias}.type_donnee = 'numeric_range' AND ({alias}.valeur_max_canonique IS NULL OR {alias}.valeur_max_canonique {op} ${value_param}))
                        )"""
                    elif op in ["<", "<="]:
                        clause = f"""(
                            ({base_condition} AND {alias}.type_donnee = 'numeric' AND {alias}.valeur_canonique {op} ${value_param})
                            OR
                            ({base_condition} AND {alias}.type_donnee = 'numeric_range' AND {alias}.valeur_max_canonique {op} ${value_param})
                        )"""
                    else:  # =
                        clause = f"""(
                            ({base_condition} AND {alias}.type_donnee = 'numeric' AND {alias}.valeur_canonique = ${value_param})
                            OR
                            ({base_condition} AND {alias}.type_donnee = 'numeric_range' 
                                AND ({alias}.valeur_min_canonique IS NULL OR {alias}.valeur_min_canonique <= ${value_param})
                                AND ({alias}.valeur_max_canonique IS NULL OR {alias}.valeur_max_canonique >= ${value_param})
                            )
                        )"""

                    where_clauses.append(clause)
                    params[label_id_param] = label_id_stub
                    params[value_param] = canonical_val
                    params[unit_param] = canonical_unit
                    param_counter += 1
                else:
                    # Fallback
                    param_name = f"fallback_text_val_{param_counter}"
                    where_clauses.append(
                        f"toLower(toString({alias}.nom)) CONTAINS toLower(${param_name})"
                    )
                    params[param_name] = str(val)
                    param_counter += 1
            else:
                # Default text filter
                param_name = f"default_val_{param_counter}"
                where_clauses.append(
                    f"toLower(toString({alias}.{prop})) CONTAINS toLower(${param_name})"
                )
                params[param_name] = str(val)
                param_counter += 1

        return where_clauses, params, param_counter

    def _get_relationship_path(self, start_node: str, end_node: str) -> Optional[str]:
        return self.RELATIONSHIP_DIRECTIONS.get(f"{start_node}->{end_node}")

    async def build_cypher_from_entities(
        self,
        target_entity: str,
        entities: list,
        candidate_ids: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        if not target_entity:
            return "", {}

        primary_alias = "p"
        match_clause = f"MATCH ({primary_alias}:{target_entity})"
        where_clauses = []
        all_params = {}
        global_param_counter = 0

        # 1. Filters on the Target Entity itself
        if not candidate_ids:
            target_filters = [e for e in entities if e.get("type") == target_entity]
            if target_filters:
                for entity in target_filters:
                    clauses, params, global_param_counter = (
                        await self._generate_where_conditions(
                            primary_alias,
                            target_entity,
                            entity.get("filters", []),
                            global_param_counter,
                        )
                    )
                    where_clauses.extend(clauses)
                    all_params.update(params)
        else:
            where_clauses.append(f"{primary_alias}.id IN $candidate_ids")
            all_params["candidate_ids"] = candidate_ids

        # 2. Filters on Related Entities
        related_entities = [e for e in entities if e.get("type") != target_entity]
        for i, entity in enumerate(related_entities):
            sub_alias = f"sub{i}"
            sub_entity_type = entity.get("type")
            if not sub_entity_type:
                continue

            path = self._get_relationship_path(target_entity, sub_entity_type)
            if not path:
                # Try reverse path logic if needed, or skip
                continue

            sub_filters = entity.get("filters", [])
            if not sub_filters:
                continue

            sub_where_conditions, sub_params, global_param_counter = (
                await self._generate_where_conditions(
                    sub_alias, sub_entity_type, sub_filters, global_param_counter
                )
            )
            all_params.update(sub_params)

            if not sub_where_conditions:
                continue

            is_negated = any(f.get("negate", False) for f in sub_filters)
            subquery_match = (
                f"MATCH ({primary_alias}){path}({sub_alias}:{sub_entity_type})"
            )
            subquery_where_clause = " AND ".join(sub_where_conditions)

            clause = (
                f"NOT EXISTS {{ {subquery_match} WHERE {subquery_where_clause} }}"
                if is_negated
                else f"EXISTS {{ {subquery_match} WHERE {subquery_where_clause} }}"
            )
            where_clauses.append(clause)

        cypher = match_clause
        if where_clauses:
            cypher += "\nWHERE " + "\n  AND ".join(where_clauses)
        cypher += f"\nRETURN DISTINCT {primary_alias} {{.*}} AS result\nLIMIT 20"
        return cypher, all_params

    async def extract_entities_and_build_cypher(
        self, user_query: str, candidate_ids: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Dict, Dict]:
        await self._refresh_schema()

        # Call LLM to extract entities JSON
        extracted_json_str = await llm_service.invoke_chain(
            ENTITY_EXTRACTION_TEMPLATE,
            {"schema": self.schema_text, "question": user_query},
        )

        try:
            # Clean markdown
            if "```json" in extracted_json_str:
                extracted_json_str = extracted_json_str[
                    extracted_json_str.find("{") : extracted_json_str.rfind("}") + 1
                ]

            extracted_data = json.loads(extracted_json_str)
            target_entity = extracted_data.get("target_entity", "Produit")
            entities = extracted_data.get("entities", [])

            if not entities and not candidate_ids:
                return None, {}, {}

            generated_cypher, params = await self.build_cypher_from_entities(
                target_entity, entities, candidate_ids
            )
            return generated_cypher, extracted_data, params

        except (json.JSONDecodeError, KeyError) as e:
            logging.error(f"Failed to process LLM extraction output: {e}")
            return None, {}, {}


cypher_builder = CypherBuilderService()
