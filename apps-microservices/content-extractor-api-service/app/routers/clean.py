import logging
import time

from fastapi import APIRouter, HTTPException

from app.schemas.clean import CleanRequest, CleanResponse
from app.core import extractor_service
from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/clean", response_model=CleanResponse)
async def clean_html(request: CleanRequest):
    """Remove boilerplate from HTML and return cleaned content."""
    from app.core.admission import admission
    from app.core.config import settings
    from app.core.metrics import SYNC_ADMISSION_REJECTED

    if not admission.try_acquire():
        SYNC_ADMISSION_REJECTED.inc()
        raise HTTPException(
            status_code=503,
            detail={"detail": "Service saturated", "error_code": "ADMISSION_REJECTED"},
            headers={"Retry-After": str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)},
        )
    start_time = time.monotonic()
    try:
        body = await extractor_service.run_clean(request.html, request.format)
    except Exception:
        logger.exception("Extraction failed")
        REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )
    finally:
        admission.release()
    duration = time.monotonic() - start_time
    logger.info("Cleaned HTML in %.3fs, format=%s, length=%d",
                duration, request.format.value, body["content_length"])
    REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="200").inc()
    REQUEST_DURATION.labels(method="POST", endpoint="/clean").observe(duration)
    return CleanResponse(**body)
