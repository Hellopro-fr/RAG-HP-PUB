from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class CaracteristiqueRequest(BaseModel):
    """Requête pour l'extraction des caractéristiques influençant le prix"""
    id_categorie: str = Field(..., description="ID de la catégorie à analyser")
    id_prompt: Optional[str] = Field(None, description="ID du prompt à utiliser (optionnel, utilise la config par défaut)")


class ReponseResult(BaseModel):
    """Résultat du traitement d'une réponse Q1"""
    id_reponse: Any = Field(None, description="ID de la réponse Q1")
    reponse: str = Field("", description="Texte de la réponse Q1")
    sous_type: str = Field("", description="Sous-type identifié par le LLM")
    caracteristiques_prix: Optional[List[Any]] = Field(None, description="Caractéristiques prix identifiées par le LLM")
    ids_saved: List[str] = Field(default_factory=list, description="IDs des caractéristiques sauvegardées en base")


class CaracteristiqueResponse(BaseModel):
    """Réponse de l'endpoint /prix/caracteristique"""
    success: bool = Field(..., description="Indique si le traitement a réussi")
    data: Optional[List[ReponseResult]] = Field(None, description="Résultats par réponse Q1")
    raw: Optional[List[Dict[str, Any]]] = Field(None, description="Données brutes des résultats")
    errors: List[str] = Field(default_factory=list, description="Liste des erreurs rencontrées")
    skipped: List[str] = Field(default_factory=list, description="Réponses ignorées (déjà traitées)")
    time_elapsed: Optional[float] = Field(None, description="Temps de traitement en secondes")
    message: str = Field("", description="Message informatif ou d'erreur")
