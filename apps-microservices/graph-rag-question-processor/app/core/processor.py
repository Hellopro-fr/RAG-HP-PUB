import logging
import re
from typing import Dict, Any, Optional
from app.infrastructure.database_client import GraphDatabaseClient
from pydantic import BaseModel, Field, field_validator


class BaseNormalizer(BaseModel):
    @field_validator("*", mode="before")
    def normalize_whitespace(cls, v):
        if isinstance(v, str):
            return re.sub(r"\s+", " ", v).strip()
        return v


class QuestionPayload(BaseNormalizer):
    question: str = Field(..., description="Libellé de la question")
    id_question: str = Field(..., description="ID numérique de la question")
    id_categorie: str = Field(..., description="ID de la catégorie associée")
    ordre: int = Field(..., description="Ordre de la question dans le questionnaire")
    type_question: Optional[str] = Field(None, description="Type (unique, multiple...)")
    id_prev_question: Optional[str] = Field(
        None, description="ID de la question précédente"
    )

    def get_graph_id(self) -> str:
        return f"id_question_{self.id_question}"


class QuestionProcessor:
    def __init__(self):
        self.db_client = GraphDatabaseClient()

    def process_message(self, message_data: Dict[str, Any]):
        try:
            logging.info(f"Processing question message: {message_data}")
            payload = message_data.get("payload", {})
            if not payload:
                return

            q = QuestionPayload.model_validate(payload)
            props_with_id = q.model_dump()
            props_with_id["id"] = q.get_graph_id()

            # 1. Create Question Node
            cypher_create = "MERGE (q:Question {id: $props.id}) SET q += $props"
            self.db_client.execute_cypher(cypher_create, {"props": props_with_id})

            # 2. Link to Categorie (if order 1)
            if q.ordre == 1:
                cypher_link_cat = """
                MATCH (q:Question {id: $question_id})
                MERGE (c:Categorie {id: $categorie_id})
                MERGE (c)-[:A_POUR_QUESTION]->(q)
                """
                self.db_client.execute_cypher(
                    cypher_link_cat,
                    {
                        "question_id": q.get_graph_id(),
                        "categorie_id": f"id_categorie_{q.id_categorie}",
                    },
                )

            # 3. Handle Previous Question Link
            if q.id_prev_question:
                prev_id = f"id_question_{q.id_prev_question}"

                # Logic: Link Prev->Curr (SUIT)
                # If Prev.ordre == 1, also link Prev's Responses -> Curr (MENE_A)
                # Note: 'prev.ordre = 1' check in cypher requires prev node to exist and have property
                cypher_link_prev = """
                MATCH (curr:Question {id: $curr_id})
                MERGE (prev:Question {id: $prev_id})
                MERGE (prev)-[:SUIT]->(curr)
                WITH prev, curr
                WHERE prev.ordre = 1
                MATCH (prev)-[:PROPOSE]->(r:Reponse)
                MERGE (r)-[:MENE_A]->(curr)
                """
                self.db_client.execute_cypher(
                    cypher_link_prev, {"curr_id": q.get_graph_id(), "prev_id": prev_id}
                )

            logging.info(f"Successfully processed question {q.get_graph_id()}")

        except Exception as e:
            logging.error(f"Failed to process question: {e}", exc_info=True)
            raise e

    def close(self):
        self.db_client.close()
