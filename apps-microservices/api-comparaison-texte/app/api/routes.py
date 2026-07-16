import asyncio
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
from app.core.admission import admission
from app.core import metrics
from app.services.html_cleaner import extract_text_from_html

logger = logging.getLogger(__name__)

router = APIRouter()


def _compare_one(request: ComparisonRequest) -> ComparisonResult:
    """Pure synchronous single comparison (offloaded via asyncio.to_thread)."""
    new_text = (
        extract_text_from_html(request.new_content)
        if request.content_type == ContentType.HTML
        else request.new_content
    )
    comp = compare_texts(request.old_text, new_text, request.threshold)
    return ComparisonResult(url=request.url, **comp)


def _run_batch(items, threshold) -> tuple[list, int]:
    """Pure synchronous batch loop (offloaded as ONE unit via asyncio.to_thread).
    GIL: difflib is pure-Python; offloading the whole batch keeps the event loop
    responsive — it does not parallelise the items (use workers/replicas for that)."""
    results = []
    error_count = 0
    for item in items:
        try:
            new_text = (
                extract_text_from_html(item.new_content)
                if item.content_type == ContentType.HTML
                else item.new_content
            )
            comp = compare_texts(item.old_text, new_text, threshold)
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
    return results, error_count


def _admit_or_503() -> None:
    if not admission.try_acquire():
        metrics.SYNC_ADMISSION_REJECTED.inc()
        raise HTTPException(
            status_code=503,
            detail={"detail": "Service saturated", "error_code": "ADMISSION_REJECTED"},
            headers={"Retry-After": str(settings.ADMISSION_RETRY_AFTER_S)},
        )


@router.post("/compare", response_model=ComparisonResponse)
async def compare_single(request: ComparisonRequest):
    """Compare un nouveau contenu avec un ancien texte de référence."""
    _admit_or_503()
    start = time.perf_counter()
    try:
        result = await asyncio.to_thread(_compare_one, request)
    except Exception:
        logger.exception("Comparison failed")
        metrics.REQUEST_COUNT.labels(endpoint="/compare", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Comparison failed", "error_code": "INTERNAL_ERROR"},
        )
    finally:
        admission.release()
    metrics.REQUEST_DURATION.labels(endpoint="/compare").observe(time.perf_counter() - start)
    metrics.REQUEST_COUNT.labels(endpoint="/compare", status="200").inc()
    metrics.DECISION_COUNT.labels(decision=result.decision.value).inc()
    return ComparisonResponse(result=result)


@router.post("/compare-batch", response_model=BatchComparisonResponse)
async def compare_batch(request: BatchComparisonRequest):
    """Compare un lot d'items (batch)."""
    if len(request.items) > settings.BATCH_MAX_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Le batch ne peut pas dépasser {settings.BATCH_MAX_ITEMS} items (reçu: {len(request.items)})",
        )
    _admit_or_503()
    start = time.perf_counter()
    try:
        results, error_count = await asyncio.to_thread(_run_batch, request.items, request.threshold)
    except Exception:
        logger.exception("Batch comparison failed")
        metrics.REQUEST_COUNT.labels(endpoint="/compare-batch", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Batch comparison failed", "error_code": "INTERNAL_ERROR"},
        )
    finally:
        admission.release()

    elapsed_ms = (time.perf_counter() - start) * 1000
    metrics.REQUEST_DURATION.labels(endpoint="/compare-batch").observe(elapsed_ms / 1000)
    metrics.REQUEST_COUNT.labels(endpoint="/compare-batch", status="200").inc()
    metrics.BATCH_SIZE.observe(len(request.items))
    for r in results:
        metrics.DECISION_COUNT.labels(decision=r.decision.value).inc()

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
