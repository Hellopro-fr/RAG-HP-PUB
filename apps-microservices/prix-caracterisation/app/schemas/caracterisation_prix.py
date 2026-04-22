from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class RequestProcessus(BaseModel):
    """Requête pour lancer le processus de caractérisation prix"""
    id_categorie: str = Field(..., description="ID de la catégorie")
    is_reset: bool = Field(default=False, description="Indique si on reset le processus")
    source: Optional[str] = Field(default=None, description="Filtre optionnel par source (devis/message/produit/siteweb)")


class CaracterisationPrixResult(BaseModel):
    """Résultat global de la caractérisation prix pour une catégorie"""
    id_categorie: str
    nom_rubrique: str = ""
    total_prix: int = 0
    total_processed: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    by_source: Dict[str, int] = Field(default_factory=dict, description="Compteur par source (devis/message/produit/siteweb)")
    status: str = "completed"  # completed, completed_with_errors, error, stopped
