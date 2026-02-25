from enum import Enum
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional


class DetectionMode(str, Enum):
    """Mode de détection de la langue française"""
    SIMPLE = "simple"      # Comportement TypeScript (URL + HTML lang uniquement)
    COMPLETE = "complete"  # Comportement PHP (+ recherche liens alternatifs)


class DetectionRequest(BaseModel):
    """Requête de détection pour une URL unique"""
    url: str = Field(..., description="URL du site à analyser")
    mode: DetectionMode = Field(
        default=DetectionMode.COMPLETE,
        description="Mode de détection: simple ou complete"
    )
    html_content: Optional[str] = Field(
        default=None,
        description="Contenu HTML déjà récupéré (optionnel)"
    )
    proxy_url: Optional[str] = Field(
        default=None,
        description="URL du proxy à utiliser"
    )
    forced_method: Optional[str] = Field(
        default=None,
        description="Forcer une méthode de détection spécifique"
    )
    use_nlp_detection: bool = Field(
        default=True,
        description="Activer la détection NLP par contenu textuel"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://www.example.com",
                    "mode": "complete",
                    "use_nlp_detection": True
                }
            ]
        }
    }


class DetectionResponse(BaseModel):
    """Réponse de détection pour une URL"""
    ok: bool = Field(..., description="True si français détecté")
    url: str = Field(..., description="URL analysée ou URL française trouvée")
    method: str = Field(..., description="Méthode de détection utilisée")
    confidence: Optional[float] = Field(
        default=None,
        description="Score de confiance NLP (0-1)"
    )
    alternative_urls: list[str] = Field(
        default=[],
        description="URLs françaises alternatives trouvées"
    )
    error: Optional[str] = Field(
        default=None,
        description="Message d'erreur si échec"
    )


class BatchItem(BaseModel):
    """Élément unique d'une requête par lot"""
    url: str = Field(..., description="URL du site à analyser")
    html_content: Optional[str] = Field(
        default=None,
        description="Contenu HTML optionnel déjà récupéré"
    )


class BatchDetectionRequest(BaseModel):
    """Requête de détection pour plusieurs URLs"""
    urls: list[str] | None = Field(
        default=None,
        max_length=100,
        description="[DEPRECATED] Liste d'URLs simples à analyser"
    )
    items: list[BatchItem] | None = Field(
        default=None,
        max_length=100,
        description="Liste d'items contenant l'URL et le HTML optionnel"
    )
    mode: DetectionMode = Field(
        default=DetectionMode.COMPLETE,
        description="Mode de détection appliqué à toutes les URLs"
    )
    proxy_url: Optional[str] = Field(
        default=None,
        description="URL du proxy à utiliser"
    )
    use_nlp_detection: bool = Field(
        default=True,
        description="Activer la détection NLP"
    )
    max_concurrency: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Nombre de requêtes parallèles max"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "items": [
                        {
                            "url": "https://www.lemonde.fr",
                            "html_content": "<html lang='fr'>...</html>"
                        },
                        {
                            "url": "https://www.bbc.co.uk"
                        }
                    ],
                    "mode": "simple",
                    "max_concurrency": 5
                }
            ]
        }
    }


class BatchDetectionResponse(BaseModel):
    """Réponse de détection pour plusieurs URLs"""
    total: int = Field(..., description="Nombre total d'URLs traitées")
    success_count: int = Field(..., description="Nombre de sites FR détectés")
    failed_count: int = Field(..., description="Nombre de sites non-FR")
    error_count: int = Field(..., description="Nombre d'erreurs")
    results: list[DetectionResponse] = Field(..., description="Résultats par URL")
    processing_time_ms: float = Field(..., description="Temps de traitement total en ms")


class UrlCheckResponse(BaseModel):
    """Réponse de vérification rapide d'URL"""
    ok: bool
    method: str
    url: Optional[str] = None
    original_url: Optional[str] = None
