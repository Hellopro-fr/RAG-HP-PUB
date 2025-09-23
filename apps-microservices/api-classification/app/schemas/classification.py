from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
import json

class ProductInput(BaseModel):
    """Modèle pour un produit à classifier"""
    id_produit: str = Field(..., description="ID unique du produit")
    nom_produit: str = Field(..., description="Nom/titre du produit")
    description: str = Field(..., description="Description détaillée du produit")
    id_categorie_attendue: Optional[str] = Field(None, description="ID de catégorie attendue (optionnel)")

    class Config:
        json_schema_extra = {
            "example": {
                "id_produit": "12345",
                "nom_produit": "Perceuse électrique Bosch",
                "description": "Perceuse électrique professionnelle 750W avec mandrin automatique",
                "id_categorie_attendue": "cat_123"
            }
        }

class BatchProductsInput(BaseModel):
    """Modèle pour traiter plusieurs produits en lot"""
    produits: List[ProductInput] = Field(..., description="Liste des produits à classifier")
    
    class Config:
        json_schema_extra = {
            "example": {
                "produits": [
                    {
                        "id_produit": "12345",
                        "nom_produit": "Perceuse électrique Bosch",
                        "description": "Perceuse électrique professionnelle 750W",
                        "id_categorie_attendue": "cat_123"
                    },
                    {
                        "id_produit": "12346", 
                        "nom_produit": "Marteau-piqueur",
                        "description": "Marteau-piqueur pneumatique 25kg",
                        "id_categorie_attendue": None
                    }
                ]
            }
        }

class ClassificationResult(BaseModel):
    """Résultat de classification pour un produit"""
    id_produit: str = Field(..., description="ID du produit")
    status: Literal["SUCCESS", "ERROR"] = Field(..., description="Statut de la classification")
    id_categorie: Optional[str] = Field(None, description="ID de la catégorie assignée")
    nom_categorie: Optional[str] = Field(None, description="Nom de la catégorie assignée")
    score_llm: Optional[int] = Field(None, description="Score de confiance (0 ou 1)")
    processing_time: float = Field(..., description="Temps de traitement en secondes")
    llm_type: Optional[Literal["OpenAI", "DeepSeek", "Qwen"]] = Field(None, description="Type de LLM utilisé pour la classification")
    llm_response: Optional[List[Dict[str, Any]]] = Field(None, description="Réponse brute de DeepSeek (si applicable)")
    error: Optional[str] = Field(None, description="Message d'erreur si échec")

class BatchClassificationResponse(BaseModel):
    """Réponse pour un traitement en lot"""
    total_produits: int = Field(..., description="Nombre total de produits traités")
    success_count: int = Field(..., description="Nombre de succès")
    error_count: int = Field(..., description="Nombre d'erreurs")
    resultats: List[ClassificationResult] = Field(..., description="Résultats détaillés")
    llm_type: Optional[Literal["OpenAI", "DeepSeek", "Qwen"]] = Field(None, description="Type de LLM utilisé pour la classification")
    processing_time_total: float = Field(..., description="Temps total de traitement")

class ConfigurationRequest(BaseModel):
    """Configuration pour l'API de classification"""
    llm_choice: Literal["OpenAI", "DeepSeek", "Qwen"] = Field(default="DeepSeek", description="Choix du LLM")
    search_results_limit: int = Field(default=30, description="Nombre de résultats de recherche")
    categories_limit: int = Field(default=10, description="Nombre max de catégories à considérer")
    
class ApiStatus(BaseModel):
    """Statut de l'API"""
    status: str = Field(..., description="Statut général")
    llm_configured: bool = Field(..., description="LLM configuré")
    search_api_available: bool = Field(..., description="API de recherche disponible")
    current_config: Dict[str, Any] = Field(..., description="Configuration actuelle")