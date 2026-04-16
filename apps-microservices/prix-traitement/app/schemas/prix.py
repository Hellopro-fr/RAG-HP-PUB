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
    texte_prompt: Optional[str] = Field(None, description="Texte optionnel à injecter comme {requete_rag} dans le prompt LLM (remplace texte_recherche si non vide)")
    model: Optional[str] = Field(None, description="Modèle LLM à utiliser (remplace le modèle par défaut si fourni)")
    type_source: Optional[str] = Field(None, description="Type de source de base prix")
    
    @field_validator('id_categorie')
    @classmethod
    def convert_id_to_str(cls, v):
        return str(v)


class QuestionnaireResponse(BaseModel):
    """Réponse de l'endpoint /prix/questionnaire"""
    success: bool = Field(..., description="Indique si le traitement a réussi")
    reponse: Optional[Dict[str, Any]] = Field(None, description="Réponse json extracté générée par le LLM")
    api_response: Optional[Dict[str, Any]] = Field(None, description="Réponse brute de l'API")
    time_elapsed: Optional[float] = Field(None, description="Temps de traitement en secondes")
    message: str = Field("", description="Message informatif ou d'erreur")


class QuestionnaireV2Request(BaseModel):
    """Requête pour le questionnaire prix V2 via matching équivalences + LLM"""
    equivalences: List[Dict[str, Any]] = Field(..., description="Équivalences prix filtrées (textuelles) issues du questionnaire acheteur")
    id_categorie: Union[str, int] = Field(..., description="ID de la catégorie cible")
    nom_categorie: str = Field(..., description="Nom de la catégorie cible")
    texte_prompt: str = Field(..., description="Texte à injecter comme {requete_rag} dans le prompt LLM")
    model: Optional[str] = Field(None, description="Modèle LLM à utiliser (remplace le modèle par défaut si fourni)")

    @field_validator('id_categorie')
    @classmethod
    def convert_id_to_str_v2(cls, v):
        return str(v)


class QuestionnaireV2Response(BaseModel):
    """Réponse de l'endpoint /prix/questionnaire-v2"""
    success: bool = Field(..., description="Indique si le traitement a réussi")
    reponse: Optional[Dict[str, Any]] = Field(None, description="Réponse JSON structurée générée par le LLM")
    matching: Optional[Dict[str, Any]] = Field(None, description="Résultat brut du matching prix (nb_results, results)")
    api_response: Optional[Dict[str, Any]] = Field(None, description="Réponse brute de l'API LLM")
    time_elapsed: Optional[float] = Field(None, description="Temps de traitement en secondes")
    message: str = Field("", description="Message informatif ou d'erreur")


class CaracteristiqueLotRequest(BaseModel):
    """Requête pour le traitement batch des caractéristiques prix"""
    categories: List[CaracteristiqueRequest] = Field(..., description="Liste des catégories à traiter")


class CaracteristiqueLotItemResult(BaseModel):
    """Résultat du traitement d'une catégorie dans le lot"""
    id_categorie: str = Field(..., description="ID de la catégorie traitée")
    success: bool = Field(..., description="Indique si le traitement de cette catégorie a réussi")
    data: Optional[List[ReponseResult]] = Field(None, description="Résultats par réponse Q1")
    raw: Optional[List[Dict[str, Any]]] = Field(None, description="Données brutes des résultats")
    errors: List[str] = Field(default_factory=list, description="Erreurs rencontrées pour cette catégorie")
    skipped: List[Any] = Field(default_factory=list, description="Réponses ignorées (dicts ou strings)")
    time_elapsed: Optional[float] = Field(None, description="Temps de traitement pour cette catégorie")
    message: str = Field("", description="Message informatif ou d'erreur")


class CaracteristiqueLotResponse(BaseModel):
    """Réponse de l'endpoint /prix/caracteristique-lot"""
    success: bool = Field(..., description="Indique si le traitement global a réussi (toutes les catégories)")
    total: int = Field(0, description="Nombre total de catégories dans le lot")
    success_count: int = Field(0, description="Nombre de catégories traitées avec succès")
    error_count: int = Field(0, description="Nombre de catégories en erreur")
    results: List[CaracteristiqueLotItemResult] = Field(default_factory=list, description="Résultats par catégorie")
    time_elapsed: Optional[float] = Field(None, description="Temps de traitement total du lot")
    message: str = Field("", description="Message informatif global")

