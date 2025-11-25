from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
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
