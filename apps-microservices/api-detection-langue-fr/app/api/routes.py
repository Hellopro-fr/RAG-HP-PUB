import asyncio
import time
from typing import Optional
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    DetectionRequest,
    DetectionResponse,
    BatchDetectionRequest,
    BatchDetectionResponse,
    UrlCheckResponse,
    DetectionMode
)
from app.core.domain_fr import DomainFR
from app.services.redirect_tracker import fetch_html

router = APIRouter()


@router.post("/detect", response_model=DetectionResponse)
async def detect_french(request: DetectionRequest) -> DetectionResponse:
    """
    Détecte si un site est en français ou dispose d'une version française.
    
    **Modes:**
    - `simple`: Vérifie URL + attribut lang HTML uniquement (comportement TypeScript)
    - `complete`: + recherche de liens alternatifs hreflang, options, etc. (comportement PHP)
    
    **Paramètres optionnels:**
    - `html_content`: Si le HTML est déjà disponible, évite une requête HTTP
    - `proxy_url`: Proxy à utiliser pour les requêtes
    - `forced_method`: Force une méthode de détection spécifique
    - `use_nlp_detection`: Active/désactive la détection NLP par contenu textuel
    """
    try:
        # Récupérer le HTML si non fourni
        html_content = request.html_content
        if not html_content:
            html_content = await fetch_html(request.url, request.proxy_url)
            if not html_content:
                return DetectionResponse(
                    ok=False,
                    url=request.url,
                    method='fetch_failed',
                    error='Impossible de récupérer le contenu HTML'
                )
        
        # Créer le détecteur
        detector = DomainFR(
            homepage=request.url,
            forced_method=request.forced_method,
            use_nlp_detection=request.use_nlp_detection
        )
        
        # Lancer la détection
        result = await detector.check_page_if_french(html_content, request.mode)
        
        return result
        
    except Exception as e:
        return DetectionResponse(
            ok=False,
            url=request.url,
            method='error',
            error=str(e)
        )


@router.post("/detect-batch", response_model=BatchDetectionResponse)
async def detect_french_batch(request: BatchDetectionRequest) -> BatchDetectionResponse:
    """
    Traitement par lot : détecte plusieurs URLs en parallèle.
    
    **Paramètres:**
    - `urls`: Liste d'URLs à analyser (max 100 par requête)
    - `mode`: simple ou complete (appliqué à toutes les URLs)
    - `max_concurrency`: Nombre de requêtes parallèles (1-50, défaut: 10)
    
    **Retourne** les résultats dans le même ordre que les URLs fournies.
    """
    if not request.urls:
        raise HTTPException(status_code=400, detail="La liste d'URLs ne peut pas être vide")
    
    if len(request.urls) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 URLs par requête")
    
    start_time = time.time()
    
    # Sémaphore pour limiter la concurrence
    semaphore = asyncio.Semaphore(request.max_concurrency)
    
    async def process_single(url: str) -> DetectionResponse:
        async with semaphore:
            try:
                # Récupérer le HTML
                html_content = await fetch_html(url, request.proxy_url)
                if not html_content:
                    return DetectionResponse(
                        ok=False,
                        url=url,
                        method='fetch_failed',
                        error='Impossible de récupérer le contenu HTML'
                    )
                
                # Créer le détecteur
                detector = DomainFR(
                    homepage=url,
                    use_nlp_detection=request.use_nlp_detection
                )
                
                # Lancer la détection
                return await detector.check_page_if_french(html_content, request.mode)
                
            except Exception as e:
                return DetectionResponse(
                    ok=False,
                    url=url,
                    method='error',
                    error=str(e)
                )
    
    # Traiter toutes les URLs en parallèle
    results = await asyncio.gather(*[process_single(url) for url in request.urls])
    
    # Calculer les statistiques
    success_count = sum(1 for r in results if r.ok)
    error_count = sum(1 for r in results if r.method == 'error' or r.method == 'fetch_failed')
    failed_count = len(results) - success_count - error_count
    
    processing_time_ms = (time.time() - start_time) * 1000
    
    return BatchDetectionResponse(
        total=len(results),
        success_count=success_count,
        failed_count=failed_count,
        error_count=error_count,
        results=list(results),
        processing_time_ms=round(processing_time_ms, 2)
    )


@router.get("/check-url", response_model=UrlCheckResponse)
async def check_url_only(url: str, track_redirect: bool = False) -> UrlCheckResponse:
    """
    Vérifie rapidement si une URL indique une version française.
    
    Analyse uniquement l'URL (TLD, path, query params) sans récupérer le contenu HTML.
    
    **Critères vérifiés:**
    - TLD `.fr`
    - Sous-domaine `fr.`
    - Segment `/fr/` dans le path
    - Paramètre `lang=fr` dans la query string
    """
    result = await DomainFR.check_url(url, track_redirect=track_redirect)
    
    return UrlCheckResponse(
        ok=result.get('ok', False),
        method=result.get('method', 'unknown'),
        url=result.get('url'),
        original_url=result.get('original_url')
    )


@router.get("/health")
async def health_check() -> dict:
    """
    Endpoint de santé pour monitoring.
    
    Retourne le statut de l'API et des informations de version.
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "service": "detection-langue-api"
    }
