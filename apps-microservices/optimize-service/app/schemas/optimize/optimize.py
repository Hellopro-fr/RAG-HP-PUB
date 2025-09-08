from pydantic import BaseModel
from typing import List, Dict, Any

class OptimRequest(BaseModel):
    id_produit_scrapping: str
    nom_produit: str
    description_produit: str
    categorie_produit :str

class OptimResponse(BaseModel):
    data: List[Dict[str, Any]]

class BatchOptimRequest(BaseModel):
    """Schéma pour une demande d'optimisation par lots."""
    products: List[OptimRequest] = Field(
        ..., 
        description="Liste des produits à optimiser",
        min_items=1,
        max_items=5000  # Limite raisonnable pour éviter les timeouts
    )

class BatchMetadata(BaseModel):
    """Métadonnées pour le traitement par lots."""
    total_products: int
    successful_optimizations: int
    failed_optimizations: int
    processing_time_seconds: float
    batch_size: int

class BatchOptimResponse(BaseModel):
    """Schéma pour la réponse d'optimisation par lots."""
    data: List[Dict[str, Any]] = Field(
        ..., 
        description="Liste des résultats d'optimisation"
    )
    metadata: BatchMetadata = Field(
        ..., 
        description="Métadonnées sur le traitement"
    )