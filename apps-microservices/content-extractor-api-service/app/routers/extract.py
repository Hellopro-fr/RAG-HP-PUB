import logging
import time

from fastapi import APIRouter, HTTPException

from app.schemas.extract import ExtractRequest, ExtractResponse, ExtractDebugResponse
from app.core import extractor_service
from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extract")


@router.post("/header-footer", response_model=ExtractResponse | ExtractDebugResponse)
async def extract_header_footer(request: ExtractRequest):
    """Extract header and footer from HTML using multi-strategy comparison."""
    start_time = time.monotonic()
    try:
        body = await extractor_service.run_header_footer(
            request.main_html, request.reference_htmls, request.debug
        )
    except Exception:
        logger.exception("Header/footer extraction failed")
        REQUEST_COUNT.labels(method="POST", endpoint="/extract/header-footer", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )
    duration = time.monotonic() - start_time
    REQUEST_COUNT.labels(method="POST", endpoint="/extract/header-footer", status="200").inc()
    REQUEST_DURATION.labels(method="POST", endpoint="/extract/header-footer").observe(duration)
    return ExtractDebugResponse(**body) if request.debug else ExtractResponse(**body)
