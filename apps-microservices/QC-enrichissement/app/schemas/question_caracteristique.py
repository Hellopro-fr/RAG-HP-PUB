from pydantic import BaseModel, Field
from typing import  List, Optional, Dict, Any
from datetime import datetime

class ReponseQuestion(BaseModel):
    """Schéma pour une réponse à une question"""
    id_reponse: str = Field(..., description="ID unique de la réponse")
    reponse: str = Field(..., description="Intitulé de la réponse")

class BulleAide(BaseModel):
    """Bulle d'aide affichée à côté de la question (remplace l'ancienne justification texte)"""
    libelle: str = Field(default="", description="Titre court de la bulle d'aide")
    explication: List[str] = Field(default_factory=list, description="Liste de paragraphes d'explication")
    astuce: str = Field(default="", description="Astuce / recommandation courte")

class Question(BaseModel):
    """Schéma pour une question"""
    id_question: str = Field(..., description="ID unique de la question")
    intitule: str = Field(..., description="Intitulé de la question")
    choix: int = Field(default=1, description="Type choix de question: 1=single, 2=multiple")
    bulle_aide: BulleAide = Field(default_factory=BulleAide, description="Bulle d'aide structurée")
    reponses: List[ReponseQuestion] = Field(default_factory=list, description="Liste des réponses")

class RequestProcessus(BaseModel):
    """Requête pour lancer le processus de génération"""
    id_categorie: str = Field(..., description="ID de la catégorie")
    is_reset: bool = Field(default=False, description="Indique si on reset les questions")

class PromptConfig(BaseModel):
    """Configuration d'un prompt"""
    id_action_prompt_chatgpt: str
    contenu_prompt_apc: str
    temperature_apc: float

class ApiResponse(BaseModel):
    """Réponse standard de l'API"""
    success: bool
    message: str
    data: Optional[Any] = None

class QuestionGenerationResult(BaseModel):
    """Résultat de la génération de questions"""
    id_categorie: str
    nom_rubrique: str
    total_processed: int = 0
    status: str = "completed"  # completed, error, stopped

class ValeurCaracteristique(BaseModel):
    """Schéma pour une valeur de caractéristique"""
    id_valeur: str = Field(..., description="ID unique de la valeur")
    valeur: str = Field(..., description="Intitulé de la valeur")
    micro_explication: Optional[str] = Field(None, description="Micro explication de la valeur")
    autres_formulations: Optional[List[str]] = Field(None, description="Autres formulations de la valeur")

class Caracteristique(BaseModel):
    """Schéma pour une caractéristique"""
    id_caracteristique: str = Field(..., description="ID unique de la caractéristique")
    nom: str = Field(..., description="Nom de la caractéristique")
    description: Optional[str] = Field(None, description="Description de la caractéristique")
    unite: Optional[str] = Field(None, description="Unité de la caractéristique")
    type: Optional[str] = Field(None, description="Type de la caractéristique (Text, Numeric, etc.)")    
    exemple: Optional[str] = Field(None, description="Exemple de la caractéristique")
    valeurs: Optional[List[ValeurCaracteristique]] = Field(None, description="Liste des valeurs")


class CaracteristiqueGenerationResult(BaseModel):
    """Résultat de la génération de caractéristiques"""
    id_categorie: str
    nom_rubrique: str
    total_processed: int = 0
    status: str = "completed"  # completed, error, stopped

class EnrichissementGenerationResult(BaseModel):
    """Résultat de l'enrichissement des caractéristiques"""
    id_categorie: str
    nom_rubrique: str
    total_processed: int = 0
    status: str = "completed"  # completed, error, stopped

class EquivalenceGenerationResult(BaseModel):
    """Résultat de la génération des équivalences"""
    id_categorie: str
    nom_rubrique: str
    total_processed: int = 0
    status: str = "completed"  # completed, error, stopped

class CaracterisationProduitResult(BaseModel):
    """Résultat de la caractérisation des produits"""
    id_categorie: str
    nom_rubrique: str
    total_processed: int = 0
    status: str = "completed"  # completed, error, stopped