from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class RequestProcessus(BaseModel):
    """Requête pour lancer le processus d'extraction de prix"""
    id_categorie: str = Field(..., description="ID de la catégorie")
    is_reset: bool = Field(default=False, description="Indique si on reset le processus")


class ItemResult(BaseModel):
    """Result of processing a single data item"""
    item_id: str = Field(..., description="Chunk ID in Milvus or BO base ID")
    source: str = Field(default="devis", description="Source of the chunk")
    content: str = Field(default="", description="Full text content of the data")
    prix_data: Optional[Dict[str, Any]] = Field(None, description="Price data extracted by the LLM")
    status: str = Field(default="pending", description="Status: pending, success, error")
    error_message: Optional[str] = Field(None, description="Error message if status=error")


class PrixExtractionResult(BaseModel):
    """Résultat global de l'extraction de prix pour une catégorie"""
    id_categorie: str
    total_chunks: int = 0
    processed: int = 0
    success: int = 0
    errors: int = 0
    status: str = "completed"  # completed, error, stopped
    item_results: List[ItemResult] = Field(default_factory=list, description="Liste des résultats individuels par item")
