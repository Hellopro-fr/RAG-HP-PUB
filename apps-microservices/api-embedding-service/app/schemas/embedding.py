from os import error
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Dict, Any

class EmbeddingRequest(BaseModel):
    prompt: str = Field(..., description="Le texte à encoder en vecteur d'embedding.")