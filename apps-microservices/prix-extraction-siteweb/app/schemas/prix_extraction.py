from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class RequestProcessus(BaseModel):
    """Requête pour lancer le processus d'extraction de prix"""
    id_categorie: str = Field(..., description="ID de la catégorie")
    is_reset: bool = Field(default=False, description="Indique si on reset le processus")


class ChunkResult(BaseModel):
    """Résultat du traitement d'un chunk Milvus"""
    chunk_id: str = Field(..., description="ID du chunk dans Milvus")
    source: str = Field(default="siteweb", description="Source du chunk")
    content: str = Field(default="", description="Contenu du chunk")
    prix_data: Optional[Dict[str, Any]] = Field(None, description="Données de prix extraites par le LLM")
    llm_response: Optional[str] = Field(None, description="Réponse brute du LLM")
    status: str = Field(default="pending", description="Status: pending, success, error")
    error_message: Optional[str] = Field(None, description="Message d'erreur si status=error")


class PrixExtractionResult(BaseModel):
    """Résultat global de l'extraction de prix pour une catégorie"""
    id_categorie: str
    total_chunks: int = 0
    processed: int = 0
    success: int = 0
    errors: int = 0
    status: str = "completed"  # completed, error, stopped
    chunk_results: List[ChunkResult] = Field(default_factory=list, description="Liste des résultats individuels par chunk")
