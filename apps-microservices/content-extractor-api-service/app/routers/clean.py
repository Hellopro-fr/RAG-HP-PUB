import logging
import time

from fastapi import APIRouter, HTTPException
from boilerpy3 import extractors as BoilerpyExtractor

from app.schemas.clean import CleanRequest, CleanResponse, OutputFormat

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/clean", response_model=CleanResponse)
async def clean_html(request: CleanRequest):
    """Remove boilerplate from HTML and return cleaned content."""
    start_time = time.monotonic()

    try:
        if request.format == OutputFormat.HTML:
            extractor = BoilerpyExtractor.KeepEverythingExtractor()
            content = extractor.get_marked_html(request.html)
        else:
            extractor = BoilerpyExtractor.DefaultExtractor()
            content = extractor.get_content(request.html)
    except Exception:
        logger.exception("Extraction failed")
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )

    duration = time.monotonic() - start_time
    logger.info(
        "Cleaned HTML in %.3fs, format=%s, length=%d",
        duration,
        request.format.value,
        len(content),
    )

    return CleanResponse(
        content=content,
        format=request.format,
        content_length=len(content),
    )
