from os import error
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Dict, Any

class RerankingRequest(BaseModel):
    documents: List[Dict[str, Any]]
    query: str