from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# --- Enums ---

class Decision(str, Enum):
    UPDATE = "UPDATE"
    SKIP = "SKIP"


class ContentType(str, Enum):
    TEXT = "text"
    HTML = "html"


# --- Request Models ---

class ComparisonItem(BaseModel):
    """Un item de comparaison dans un batch."""
    url: str = Field(..., description="URL du produit/page")
    new_content: str = Field(..., description="Nouveau contenu (texte brut ou HTML)")
    old_text: str = Field(..., description="Ancien texte de référence stocké en base")
    content_type: ContentType = Field(
        default=ContentType.TEXT,
        description="Type du nouveau contenu : 'text' (défaut) ou 'html' (sera nettoyé)"
    )


class ComparisonRequest(BaseModel):
    """Requête de comparaison unitaire."""
    url: str = Field(..., description="URL du produit/page")
    new_content: str = Field(..., description="Nouveau contenu (texte brut ou HTML)")
    old_text: str = Field(..., description="Ancien texte de référence stocké en base")
    content_type: ContentType = Field(
        default=ContentType.TEXT,
        description="Type du nouveau contenu : 'text' ou 'html'"
    )
    threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Seuil de similarité custom (défaut: SIMILARITY_THRESHOLD du .env)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://www.domaine.com/produit-1",
                    "new_content": "Le nouveau texte descriptif extrait de la page...",
                    "old_text": "Le texte tel qu'il est actuellement stocké en base...",
                    "content_type": "text",
                    "threshold": None
                }
            ]
        }
    }


class BatchComparisonRequest(BaseModel):
    """Requête de comparaison batch."""
    items: list[ComparisonItem] = Field(
        ...,
        min_length=1,
        description="Liste des items à comparer"
    )
    threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Seuil de similarité custom appliqué à tout le batch"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "items": [
                        {
                            "url": "https://www.domaine.com/produit-1",
                            "new_content": "Nouveau texte produit 1...",
                            "old_text": "Ancien texte produit 1...",
                            "content_type": "text"
                        },
                        {
                            "url": "https://www.domaine.com/produit-2",
                            "new_content": "<html><body>Contenu HTML</body></html>",
                            "old_text": "Ancien texte produit 2...",
                            "content_type": "html"
                        }
                    ],
                    "threshold": 0.85
                }
            ]
        }
    }


# --- Response Models ---

class ComparisonResult(BaseModel):
    """Résultat de comparaison pour un item."""
    url: str
    similarity_ratio: float = Field(..., description="Ratio de similarité entre 0 et 1")
    decision: Decision = Field(..., description="UPDATE si ratio < seuil, SKIP sinon")
    reason: str = Field(..., description="Explication de la décision")
    error: Optional[str] = Field(default=None, description="Message d'erreur si échec")


class ComparisonResponse(BaseModel):
    """Réponse de comparaison unitaire."""
    status: str = "success"
    result: ComparisonResult


class BatchComparisonResponse(BaseModel):
    """Réponse de comparaison batch."""
    status: str = "success"
    total: int = Field(..., description="Nombre total d'items traités")
    success_count: int = Field(..., description="Nombre d'items traités avec succès")
    error_count: int = Field(..., description="Nombre d'items en erreur")
    results: list[ComparisonResult]
    processing_time_ms: float = Field(..., description="Temps de traitement en millisecondes")
