from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum


class ExtractionStrategy(str, Enum):
    """Extraction strategy for Trafilatura-based extractors."""
    PRECISION = "precision"  # favor_precision=True - Less content, higher quality
    RECALL = "recall"        # favor_recall=True - More content, may include noise
    BALANCED = "balanced"    # Default behavior - Balance between precision and recall


class RequestData(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


class FullRequestData(BaseModel):
    data: Optional[RequestData] = None


class RequestModel(BaseModel):
    raw_html: Optional[str] = Field(
        None, description="Raw HTML content as a string.")
    json_data: Optional[FullRequestData] = Field(
        None, description="The full JSON object structure.")
    strategy: ExtractionStrategy = Field(
        ExtractionStrategy.BALANCED,
        description="Extraction strategy: precision (less noise), recall (more content), or balanced (default).")
    extract_metadata: bool = Field(
        False,
        description="Enable extraction of article metadata (author, date, title, etc.).")


class ResultItem(BaseModel):
    content: str
    char_count: int
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Extracted metadata when extract_metadata is enabled.")


ResponseModel = Dict[str, ResultItem]


class BoilerplateTestRequest(BaseModel):
    main_html: str = Field(..., description="The target HTML page to extract header/footer from.")
    reference_htmls: List[str] = Field(..., description="List of reference HTML pages from the same domain.")


class IntersectionDetail(BaseModel):
    signature: str
    text_main: str
    text_ref1: str
    text_ref2: str


class BoilerplateTestResponse(BaseModel):
    # Old Method Results
    header_old: str
    footer_old: str
    
    # Class Strategy Results
    header_class: str
    footer_class: str
    
    # Structural Strategy Results
    header_structural: str
    footer_structural: str
    
    # Visualizer Details
    intersections_class: List[IntersectionDetail]
    intersections_structural: List[IntersectionDetail]
    
    # Cleaned HTMLs
    cleaned_html_main: str
    cleaned_html_ref1: str
    cleaned_html_ref2: str
    
    # Final Decision (Production Simulation)
    header_selected: str
    header_method_used: str
    footer_selected: str
    footer_method_used: str