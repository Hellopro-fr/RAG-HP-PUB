from enum import Enum

from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    TEXT = "text"
    HTML = "html"


class CleanRequest(BaseModel):
    html: str = Field(..., min_length=1, description="Raw HTML to clean")
    format: OutputFormat = Field(
        default=OutputFormat.TEXT,
        description="Output format: 'text' for plain text, 'html' for marked HTML",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "html": "<html><body><article>Main content</article><nav>Menu</nav></body></html>",
                    "format": "text",
                }
            ]
        }
    }


class CleanResponse(BaseModel):
    content: str = Field(..., description="Extracted content")
    format: OutputFormat = Field(..., description="Output format used")
    content_length: int = Field(..., description="Length of extracted content in characters")
