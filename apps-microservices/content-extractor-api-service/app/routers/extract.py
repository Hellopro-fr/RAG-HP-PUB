import logging
import time

from fastapi import APIRouter, HTTPException
from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor

from app.schemas.extract import ExtractRequest, ExtractResponse, ExtractDebugResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extract")


@router.post("/header-footer", response_model=ExtractResponse | ExtractDebugResponse)
async def extract_header_footer(request: ExtractRequest):
    """Extract header and footer from HTML using multi-strategy comparison."""
    start_time = time.monotonic()

    try:
        extractor = HeaderFooterExtractor(request.main_html)

        if request.debug:
            result = extractor.extract_all_debug(request.reference_htmls)
            duration = time.monotonic() - start_time

            header_method = result.get("header_method_used", "none")
            footer_method = result.get("footer_method_used", "none")

            logger.info(
                "Extracted header/footer (debug) in %.3fs, header_method=%s, footer_method=%s",
                duration, header_method, footer_method,
            )

            return ExtractDebugResponse(
                header=result.get("header_selected", ""),
                footer=result.get("footer_selected", ""),
                header_method=header_method,
                footer_method=footer_method,
                strategies={
                    "original": {
                        "header": result.get("header_old", ""),
                        "footer": result.get("footer_old", ""),
                    },
                    "class_intersection": {
                        "header": result.get("header_class", ""),
                        "footer": result.get("footer_class", ""),
                    },
                    "structural_intersection": {
                        "header": result.get("header_structural", ""),
                        "footer": result.get("footer_structural", ""),
                    },
                },
                intersections_class=result.get("intersections_class", []),
                intersections_structural=result.get("intersections_structural", []),
                cleaned_htmls={
                    k: v for k, v in result.items()
                    if k.startswith("cleaned_html_")
                },
                gap_analysis=result.get("gap_analysis", []),
            )
        else:
            result = extractor.extract_with_fallback(request.reference_htmls)
            duration = time.monotonic() - start_time

            logger.info(
                "Extracted header/footer in %.3fs, header_method=%s, footer_method=%s",
                duration, result.get("header_method", "none"), result.get("footer_method", "none"),
            )

            return ExtractResponse(
                header=result.get("header", ""),
                footer=result.get("footer", ""),
                header_method=result.get("header_method", "none"),
                footer_method=result.get("footer_method", "none"),
            )
    except Exception:
        logger.exception("Header/footer extraction failed")
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )
