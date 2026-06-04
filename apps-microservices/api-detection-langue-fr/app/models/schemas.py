from dataclasses import dataclass
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional


class DetectionMode(str, Enum):
    """Mode de détection de la langue française"""
    SIMPLE = "simple"        # Comportement TypeScript (URL + HTML lang uniquement)
    COMPLETE = "complete"    # Comportement PHP (+ recherche liens alternatifs)
    FIRST_MATCH = "first_match"  # Batch groupé : arrêt au premier FR par groupe


class DetectionRequest(BaseModel):
    """Requête de détection pour une URL unique"""
    url: str = Field(..., description="URL du site à analyser")
    mode: DetectionMode = Field(
        default=DetectionMode.COMPLETE,
        description="Mode de détection: simple (URL + HTML lang), complete (+ NLP + alternatives), first_match (batch uniquement)"
    )
    html_content: Optional[str] = Field(
        default=None,
        description="Contenu HTML déjà récupéré (skip fetch + skip cache)"
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
    force_refresh: bool = Field(
        default=False,
        description="Ignorer le cache et forcer une nouvelle détection"
    )
    include_full_content: bool = Field(
        default=False,
        description="(Debug uniquement) Inclure le contenu HTML complet et le texte nettoye complet dans la reponse debug"
    )
    homepage_fallback: bool = Field(
        default=True,
        description="Si la page demandée est invalide (404, soft-404, redirect-to-home), tenter une fois la page d'accueil du domaine. Désactiver pour avoir une réponse strictement URL-level."
    )
    validate_alternatives: bool = Field(
        default=True,
        description="Valider les URLs alternatives via HTTP/navigateur (httpx + fallback navigateur + confirmation NLP). false = parsing seul, aucune requête réseau sur les alternatives (réduit la charge navigateur/OOM). Les alternatives hreflang restent validated=true (déclaration de confiance)."
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


class AlternativeUrl(BaseModel):
    """URL alternative française détectée avec métadonnées de découverte"""
    url: str = Field(..., description="URL de la version française")
    method: str = Field(
        ...,
        description="Méthode de découverte (hreflang, data_lang, data_gt_lang, link_pattern, option_tag)"
    )
    reliability: str = Field(
        ...,
        description="Niveau de fiabilité: high (hreflang), medium (data-lang, validated links), low (non-validated)"
    )
    validated: bool = Field(
        ...,
        description="True si l'URL a été validée via HTTP (200 + text/html)"
    )
    region_priority: int = Field(
        default=1,
        description="Priorite region francaise: 0=France (fr-FR, /fr/fr), 1=Francais generique (/fr), 2=Autre region (fr-CA, fr-BE, /dz/fr)"
    )


class DetectionResponse(BaseModel):
    """Réponse de détection pour une URL"""
    ok: bool = Field(..., description="True si français détecté")
    url: str = Field(..., description="URL analysée ou URL française trouvée")
    method: str = Field(..., description="Méthode de détection utilisée")
    confidence: Optional[float] = Field(
        default=None,
        description="Score de confiance NLP (0-1)"
    )
    alternative_urls: list[AlternativeUrl] = Field(
        default=[],
        description="URLs françaises alternatives trouvées, triées par fiabilité"
    )
    error: Optional[str] = Field(
        default=None,
        description="Message d'erreur si échec"
    )
    group: Optional[str] = Field(
        default=None,
        description="Clé du groupe (first_match mode uniquement)"
    )
    analyzed_url: Optional[str] = Field(
        default=None,
        description="URL réellement analysée si différente de l'URL demandée (cas: repli homepage, ou cache HIT cross-URL via la clé domain). None = analyse directe de l'URL demandée."
    )


class BatchItem(BaseModel):
    """Élément unique d'une requête par lot"""
    url: str = Field(..., description="URL du site à analyser")
    html_content: Optional[str] = Field(
        default=None,
        description="Contenu HTML optionnel déjà récupéré"
    )
    group: Optional[str] = Field(
        default=None,
        description="Clé de groupe pour le mode first_match (ex: 'supplier_42')"
    )


class BatchDetectionRequest(BaseModel):
    """Requête de détection pour plusieurs URLs"""
    items: list[BatchItem] = Field(
        ...,
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
    force_refresh: bool = Field(
        default=False,
        description="Ignorer le cache et forcer une nouvelle détection pour toutes les URLs"
    )
    max_concurrency: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Nombre de requêtes parallèles max"
    )
    homepage_fallback: bool = Field(
        default=True,
        description="Tenter un repli vers la page d'accueil si la page demandée est invalide (pour chaque item du lot)."
    )
    validate_alternatives: bool = Field(
        default=True,
        description="Valider les URLs alternatives via HTTP/navigateur (appliqué à chaque item). false = parsing seul, aucune requête réseau sur les alternatives."
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


# ============================================================================
# Debug models
# ============================================================================

class DebugFetchInfo(BaseModel):
    """Informations sur le contenu recupere"""
    fetched_by: str = Field(..., description="'api' si recupere par Playwright, 'provided' si fourni dans la requete")
    raw_html_length: int = Field(..., description="Longueur du HTML brut en caracteres")
    raw_html_preview: str = Field(..., description="Premiers 500 caracteres du HTML brut")
    raw_html_full: Optional[str] = Field(default=None, description="Contenu HTML complet (uniquement si include_full_content=true)")
    redirected_from: Optional[str] = Field(default=None, description="URL d'origine avant redirection (null si pas de redirection)")
    challenge_detected: Optional[str] = Field(default=None, description="Service de protection anti-bot detecte (Cloudflare, DataDome, etc.) ou null si contenu reel")

class DebugCleaningInfo(BaseModel):
    """Informations sur le nettoyage du contenu"""
    cleaned_text_length: int = Field(..., description="Longueur du texte nettoye en caracteres")
    cleaned_text_preview: str = Field(..., description="Premiers 500 caracteres du texte nettoye")
    cleaned_text_full: Optional[str] = Field(default=None, description="Texte nettoye complet (uniquement si include_full_content=true)")

class DebugUrlCheckInfo(BaseModel):
    """Resultat du check URL (TLD, path, query)"""
    ok: bool
    method: str
    is_strong_url: bool = Field(..., description="True si TLD .fr")

class DebugHtmlTagsInfo(BaseModel):
    """Resultat de la detection par balises HTML"""
    detected: bool
    is_french: bool
    method: Optional[str] = None
    value: Optional[str] = None

class DebugNlpInfo(BaseModel):
    """Resultat de la detection NLP"""
    available: bool
    lang: Optional[str] = None
    confidence: Optional[float] = None
    method: Optional[str] = None
    details: Optional[dict] = None
    confirms_french: bool = False
    soft_french: bool = False
    contradicts_french: bool = False
    strongly_contradicts: bool = False

class DebugAlternativesInfo(BaseModel):
    """Informations sur les URLs alternatives detectees"""
    candidates_found: int
    candidates: list[AlternativeUrl] = []

class DebugInfo(BaseModel):
    """Informations de debug completes du pipeline de detection"""
    fetch: DebugFetchInfo
    cleaning: DebugCleaningInfo
    url_check: DebugUrlCheckInfo
    html_tags: DebugHtmlTagsInfo
    nlp: DebugNlpInfo
    alternatives: DebugAlternativesInfo
    decision: str = Field(..., description="Cas de decision applique (ex: 'Case 1: nlp_confirmed')")

class DebugDetectionResponse(BaseModel):
    """Reponse de detection avec informations de debug"""
    result: DetectionResponse
    debug: DebugInfo


# ============================================================================
# Async batch job models
# ============================================================================

@dataclass
class BatchOpts:
    """Per-call batch options, decoupled from the request model so the batch
    core can be driven by both the sync route and the async worker."""
    proxy_url: Optional[str] = None
    use_nlp_detection: bool = True
    force_refresh: bool = False
    max_concurrency: int = 10
    homepage_fallback: bool = True
    validate_alternatives: bool = True


@dataclass
class BatchCounts:
    """Authoritative tallies returned by the batch core (success/failed/error)."""
    success_count: int
    failed_count: int
    error_count: int


class AsyncBatchSubmitRequest(BaseModel):
    """Submit body for POST /detect-batch-async. Mirrors BatchDetectionRequest
    plus an optional client idempotency key. Items must contain no duplicate URLs."""
    items: list[BatchItem] = Field(..., max_length=100)
    mode: DetectionMode = Field(default=DetectionMode.COMPLETE)
    proxy_url: Optional[str] = Field(default=None)
    use_nlp_detection: bool = Field(default=True)
    force_refresh: bool = Field(default=False)
    max_concurrency: int = Field(default=10, ge=1, le=50)
    homepage_fallback: bool = Field(default=True)
    validate_alternatives: bool = Field(default=True)
    client_job_id: Optional[str] = Field(
        default=None,
        description="Caller idempotency key. A re-submit with the same key returns the existing job."
    )


class AsyncBatchSubmitResponse(BaseModel):
    job_id: str
    status: str
    total: int
    poll_after_seconds: int


class AsyncBatchStatusResponse(BaseModel):
    job_id: str
    status: str                                   # pending|running|completed|failed|stale
    total: int
    done: int
    success_count: int
    failed_count: int
    error_count: int
    results: Optional[list[DetectionResponse]] = None
    processing_time_ms: Optional[float] = None
    error: Optional[str] = None
    poll_after_seconds: int
