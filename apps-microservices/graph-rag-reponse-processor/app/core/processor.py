import logging
import re
from typing import Dict, Any, Optional, List, Union
from app.infrastructure.database_client import GraphDatabaseClient
from pydantic import BaseModel, Field, field_validator


class BaseNormalizer(BaseModel):
    @field_validator("*", mode="before")
    def normalize_whitespace(cls, v):
        if isinstance(v, str):
            return re.sub(r"\s+", " ", v).strip()
        return v


class ReponsePayload(BaseNormalizer):
    reponse: str = Field(..., description="Libellé de la réponse")
    id_reponse: str = Field(..., description="ID numérique de la réponse")
    id_question: str = Field(..., description="ID de la question parente")
    # caracteristics list is handled loosely as it varies

    def get_graph_id(self) -> str:
        return f"id_reponse_{self.id_reponse}"


class ReponseProcessor:
    def __init__(self):
        self.db_client = GraphDatabaseClient()

    def process_message(self, message_data: Dict[str, Any]):
        try:
            logging.info(f"Processing reponse message: {message_data}")
            payload = message_data.get("payload", {})
            caracteristics = message_data.get("caracteristics", [])

            if not payload:
                return

            r = ReponsePayload.model_validate(payload)
            props_with_id = r.model_dump()
            props_with_id["id"] = r.get_graph_id()

            # 1. Create Reponse and link to Question
            cypher_create = """
            MERGE (r:Reponse {id: $props.id}) SET r += $props
            MERGE (q:Question {id: $question_id})
            MERGE (q)-[:PROPOSE]->(r)
            """
            self.db_client.execute_cypher(
                cypher_create,
                {"props": props_with_id, "question_id": f"id_question_{r.id_question}"},
            )

            # 2. Handle Characteristics Linkage
            if caracteristics and isinstance(caracteristics, list):
                # We expect list of characteristic IDs here based on logic read from 02.txt
                # Or list of dicts? Logic in 02.txt line 5198: [str(cid) for cid in r.caracteristics]
                # Wait, 02.txt logic injected caracteristics list into payload["caracteristics"].
                # Assuming the input message follows the same structure.

                # In 02.txt: `char_ids = [str(cid) for cid in r.caracteristics]` - implies list of IDs usually.
                # But `_format_characteristics_to_text` used dicts.
                # However, for `reponses`, the logic specifically links `CaracteristiqueTechnique` using `id_source_caracteristique IN $char_ids`.
                # This implies we are linking pre-existing characteristics by ID.
                # Let's assume input is list of IDs (ints or strings).

                char_ids = [str(c) for c in caracteristics]

                if char_ids:
                    # Clear old relationships first (idempotency)
                    cypher_clear = """
                    MATCH (r:Reponse {id: $reponse_id})
                    OPTIONAL MATCH (:CaracteristiqueTechnique)-[rel:EQUIVAUT_A]->(r)
                    DELETE rel
                    """
                    self.db_client.execute_cypher(
                        cypher_clear, {"reponse_id": r.get_graph_id()}
                    )

                    # Create new relationships
                    cypher_link = """
                    MATCH (r:Reponse {id: $reponse_id})
                    MATCH (c:CaracteristiqueTechnique)
                    WHERE c.id_source_caracteristique IN $char_ids
                    MERGE (c)-[:EQUIVAUT_A]->(r)
                    """
                    self.db_client.execute_cypher(
                        cypher_link,
                        {"reponse_id": r.get_graph_id(), "char_ids": char_ids},
                    )

            logging.info(f"Successfully processed reponse {r.get_graph_id()}")

        except Exception as e:
            logging.error(f"Failed to process reponse: {e}", exc_info=True)
            raise e

    def close(self):
        self.db_client.close()
