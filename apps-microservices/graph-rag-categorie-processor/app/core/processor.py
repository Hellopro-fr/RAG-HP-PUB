import logging
import re
from typing import Dict, Any
from app.infrastructure.database_client import GraphDatabaseClient
from pydantic import BaseModel, Field, field_validator


class BaseNormalizer(BaseModel):
    @field_validator("*", mode="before")
    def normalize_whitespace(cls, v):
        if isinstance(v, str):
            return re.sub(r"\s+", " ", v).strip()
        return v


class CategoriePayload(BaseNormalizer):
    categorie: str = Field(..., description="Nom de la catégorie")
    id_categorie: str = Field(..., description="ID numérique original de la source")
    description: str = Field(
        None, description="Paragraphe décrivant le périmètre de la catégorie"
    )

    def get_graph_id(self) -> str:
        return f"id_categorie_{self.id_categorie}"


class CategorieProcessor:
    def __init__(self):
        self.db_client = GraphDatabaseClient()

    async def process_message(self, message_data: Dict[str, Any]):
        try:
            logging.info(f"Processing category message: {message_data}")

            # Extract payload
            payload = message_data.get("data", {})
            if not payload:
                logging.warning("No payload in message")
                return

            # Validate
            c = CategoriePayload.model_validate(payload)
            props_with_id = c.model_dump()
            props_with_id["id"] = c.get_graph_id()

            # Cypher logic from 02.txt
            cypher = "MERGE (c:Categorie {id: $props.id}) SET c += $props"

            await self.db_client.execute_cypher_async(cypher, {"props": props_with_id})
            logging.info(f"Successfully processed category {c.get_graph_id()}")

        except Exception as e:
            logging.error(f"Failed to process category: {e}", exc_info=True)
            raise e

    def close(self):
        self.db_client.close()
