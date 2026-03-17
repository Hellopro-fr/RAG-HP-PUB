from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union

class CaracteristiqueRequest(BaseModel):
    """Requête pour l'extraction des caractéristiques influençant le prix"""
    id_categorie: Union[str, int] = Field(..., description="ID de la catégorie à analyser")
    id_prompt: Optional[str] = Field(None, description="ID du prompt à utiliser (optionnel, utilise la config par défaut)")
    
    @field_validator('id_categorie')
    @classmethod
    def convert_to_str(cls, v):
        return str(v)

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


class QuestionnaireRequest(BaseModel):
    """Requête pour le questionnaire prix via RAG + LLM"""
    texte_recherche: str = Field(..., description="Texte libre utilisé pour la recherche RAG")
    id_categorie: Union[str, int] = Field(..., description="ID de la catégorie cible pour filtrer les résultats")
    nom_categorie: str = Field(..., description="Nom de la catégorie cible pour filtrer les résultats")
    
    @field_validator('id_categorie')
    @classmethod
    def convert_id_to_str(cls, v):
        return str(v)


class QuestionnaireResponse(BaseModel):
    """Réponse de l'endpoint /prix/questionnaire"""
    success: bool = Field(..., description="Indique si le traitement a réussi")
    reponse_llm: Optional[str] = Field(None, description="Réponse générée par le LLM basée sur les résultats RAG")
    chunks_count: int = Field(0, description="Nombre de chunks RAG utilisés")
    time_elapsed: Optional[float] = Field(None, description="Temps de traitement en secondes")
    message: str = Field("", description="Message informatif ou d'erreur")

