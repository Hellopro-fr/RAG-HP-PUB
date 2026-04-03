import time
import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ComparisonRequest,
    ComparisonResponse,
    ComparisonResult,
    BatchComparisonRequest,
    BatchComparisonResponse,
    ContentType,
    Decision,
)
from app.core.text_comparator import compare_texts
from app.core.config import settings
from app.services.html_cleaner import extract_text_from_html

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/compare", response_model=ComparisonResponse)
async def compare_single(request: ComparisonRequest):
    """
    Compare un nouveau contenu avec un ancien texte de référence.
    Retourne le ratio de similarité et la décision UPDATE/SKIP.
    """
    new_text = (
        extract_text_from_html(request.new_content)
        if request.content_type == ContentType.HTML
        else request.new_content
    )

    result = compare_texts(request.old_text, new_text, request.threshold)

    return ComparisonResponse(
        result=ComparisonResult(url=request.url, **result)
    )


@router.post("/compare-batch", response_model=BatchComparisonResponse)
async def compare_batch(request: BatchComparisonRequest):
    """
    Compare un lot d'items (batch) : pour chaque item, calcule la similarité
    textuelle via difflib et détermine si une mise à jour est nécessaire.
    """
    if len(request.items) > settings.BATCH_MAX_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Le batch ne peut pas dépasser {settings.BATCH_MAX_ITEMS} items (reçu: {len(request.items)})"
        )

    start = time.perf_counter()
    results = []
    error_count = 0

    for item in request.items:
        try:
            new_text = (
                extract_text_from_html(item.new_content)
                if item.content_type == ContentType.HTML
                else item.new_content
            )
            comp = compare_texts(item.old_text, new_text, request.threshold)
            results.append(ComparisonResult(url=item.url, **comp))
        except Exception as e:
            logger.error("Erreur traitement item %s: %s", item.url, e)
            error_count += 1
            results.append(ComparisonResult(
                url=item.url,
                similarity_ratio=0.0,
                decision=Decision.UPDATE,
                reason="error",
                error=str(e),
            ))

    elapsed_ms = (time.perf_counter() - start) * 1000

    return BatchComparisonResponse(
        total=len(request.items),
        success_count=len(request.items) - error_count,
        error_count=error_count,
        results=results,
        processing_time_ms=round(elapsed_ms, 2),
    )


@router.get("/health")
async def health_check():
    """Vérification de l'état du service."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
