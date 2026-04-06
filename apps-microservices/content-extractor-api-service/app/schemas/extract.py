from typing import Any

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    main_html: str = Field(..., min_length=1, description="Main page HTML")
    reference_htmls: list[str] = Field(
        ...,
        min_length=2,
        description="Reference page HTMLs from the same domain (minimum 2)",
    )
    debug: bool = Field(
        default=False,
        description="Include detailed strategy results, gap analysis, and cleaned HTMLs",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "main_html": "<html><body><header>Nav</header><main>Content</main><footer>Footer</footer></body></html>",
                    "reference_htmls": [
                        "<html><body><header>Nav</header><main>Other</main><footer>Footer</footer></body></html>",
                        "<html><body><header>Nav</header><main>Third</main><footer>Footer</footer></body></html>",
                    ],
                    "debug": False,
                }
            ]
        }
    }


class ExtractResponse(BaseModel):
    header: str = Field(..., description="Extracted header text")
    footer: str = Field(..., description="Extracted footer text")
    header_method: str = Field(..., description="Strategy that produced the header")
    footer_method: str = Field(..., description="Strategy that produced the footer")


class ExtractDebugResponse(ExtractResponse):
    strategies: dict[str, dict[str, str]] = Field(
        ...,
        description="Results from all 3 strategies: original, class_intersection, structural_intersection",
    )
    intersections_class: list[dict[str, Any]] = Field(
        ..., description="Matched elements via class intersection"
    )
    intersections_structural: list[dict[str, Any]] = Field(
        ..., description="Matched elements via structural intersection"
    )
    cleaned_htmls: dict[str, str] = Field(
        ..., description="boilerpy3-cleaned HTML per input page"
    )
    gap_analysis: list[dict[str, Any]] = Field(
        ..., description="DOM gap scoring details"
    )
