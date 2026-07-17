"""Pure, synchronous extraction cores shared by the sync routers and the async
batch worker. No I/O, no async — callers offload these via asyncio.to_thread so
the event loop stays free. Behaviour is byte-for-byte identical to the former
inline router bodies (see app/routers/clean.py, app/routers/extract.py pre-refactor)."""
import logging

from boilerpy3 import extractors as BoilerpyExtractor
from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor

from app.schemas.clean import OutputFormat

logger = logging.getLogger(__name__)


def clean_core(html: str, fmt: OutputFormat) -> str:
    """Remove boilerplate. Marked HTML for fmt=HTML, plain text for fmt=TEXT."""
    if fmt == OutputFormat.HTML:
        return BoilerpyExtractor.KeepEverythingExtractor().get_marked_html(html)
    return BoilerpyExtractor.DefaultExtractor().get_content(html)


def header_footer_core(main_html: str, reference_htmls: list[str], debug: bool) -> dict:
    """Multi-strategy header/footer extraction. Returns the response BODY dict
    (ExtractResponse fields; plus the debug fields when debug=True)."""
    extractor = HeaderFooterExtractor(main_html)

    if debug:
        result = extractor.extract_all_debug(reference_htmls)
        header_method = result.get("header_method_used", "none")
        footer_method = result.get("footer_method_used", "none")
        return {
            "header": result.get("header_selected", ""),
            "footer": result.get("footer_selected", ""),
            "header_method": header_method,
            "footer_method": footer_method,
            "strategies": {
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
            "intersections_class": result.get("intersections_class", []),
            "intersections_structural": result.get("intersections_structural", []),
            "cleaned_htmls": {
                k: v for k, v in result.items() if k.startswith("cleaned_html_")
            },
            "gap_analysis": result.get("gap_analysis", []),
        }

    result = extractor.extract_with_fallback(reference_htmls)
    return {
        "header": result.get("header", ""),
        "footer": result.get("footer", ""),
        "header_method": result.get("header_method", "none"),
        "footer_method": result.get("footer_method", "none"),
    }
