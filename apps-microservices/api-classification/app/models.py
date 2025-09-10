from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class LLMProvider(str, Enum):
    OPENAI = "OpenAI"
    DEEPSEEK = "DeepSeek"
    LOCAL = "Local"

class ProductInput(BaseModel):
    id_produit: str = Field(..., description="ID unique du produit")
    nom_produit: str = Field(..., description="Nom du produit")
    description: str = Field(..., description="Description du produit")
    id_categorie_attendue: Optional[str] = Field(None, description="Catégorie attendue pour validation")

class ClassificationRequest(BaseModel):
    produit: ProductInput
    enhance_content: bool = Field(True, description="Améliorer le contenu avant classification")
    llm_provider: LLMProvider = Field(LLMProvider.OPENAI, description="Fournisseur LLM à utiliser")
    n_similar: int = Field(50, ge=10, le=100, description="Nombre de produits similaires à récupérer")
    m_categories: int = Field(10, ge=3, le=20, description="Nombre de top catégories à considérer")
    k_products: int = Field(5, ge=0, le=15, description="Nombre d'exemples de produits à montrer au LLM")

class BatchClassificationRequest(BaseModel):
    produits: List[ProductInput]
    enhance_content: bool = Field(True, description="Améliorer le contenu avant classification")
    llm_provider: LLMProvider = Field(LLMProvider.OPENAI, description="Fournisseur LLM à utiliser")
    n_similar: int = Field(50, ge=10, le=100, description="Nombre de produits similaires à récupérer")
    m_categories: int = Field(10, ge=3, le=20, description="Nombre de top catégories à considérer")
    k_products: int = Field(5, ge=0, le=15, description="Nombre d'exemples de produits à montrer au LLM")

class PrecisionCheck(BaseModel):
    expected: str
    predicted: str
    is_correct: bool

class ClassificationResult(BaseModel):
    id_categorie_choisie: str
    nom_categorie: str
    score_llm: int
    status: str
    source_llm: str
    titre_original: str
    titre_utilise: str
    description_utilisee: str

class ContextInfo(BaseModel):
    categories_candidates: List[Dict[str, Any]]
    produits_similaires_montres: List[Dict[str, Any]]

class ClassificationResponse(BaseModel):
    id_produit: str
    status: str
    error: Optional[str] = None
    precision_check: Optional[PrecisionCheck] = None
    resultat_classification: Optional[ClassificationResult] = None
    contexte_fourni_au_llm: Optional[ContextInfo] = None
    processing_time_seconds: Optional[float] = None

class BatchSummary(BaseModel):
    total_products: int
    successful_classifications: int
    success_rate: float
    precision_rate: Optional[float] = None
    average_processing_time: float
    llm_used: str

class BatchClassificationResponse(BaseModel):
    summary: BatchSummary
    detailed_results: List[ClassificationResponse]

class HealthResponse(BaseModel):
    status: str
    version: str
    available_llms: List[str]
    milvus_connected: bool