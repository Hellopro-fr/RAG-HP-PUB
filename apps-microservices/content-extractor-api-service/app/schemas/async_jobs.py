from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.clean import OutputFormat


class CleanItem(BaseModel):
    html: str = Field(..., min_length=1)
    format: OutputFormat = Field(default=OutputFormat.TEXT)


class HeaderFooterItem(BaseModel):
    main_html: str = Field(..., min_length=1)
    reference_htmls: list[str] = Field(..., min_length=2)
    debug: bool = Field(default=False)


class CleanAsyncRequest(BaseModel):
    items: list[CleanItem] = Field(..., min_length=1, max_length=100)
    max_concurrency: int = Field(default=4, ge=1, le=50)   # default == DEFAULT_MAX_CONCURRENCY
    force_refresh: bool = Field(default=False)
    client_job_id: Optional[str] = Field(default=None)


class HeaderFooterAsyncRequest(BaseModel):
    items: list[HeaderFooterItem] = Field(..., min_length=1, max_length=100)
    max_concurrency: int = Field(default=4, ge=1, le=50)
    force_refresh: bool = Field(default=False)
    client_job_id: Optional[str] = Field(default=None)


class AsyncSubmitResponse(BaseModel):
    job_id: str
    status: str
    total: int
    poll_after_seconds: int


class AsyncJobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: str                                  # pending|running|completed|failed|stale
    total: int
    done: int
    results: Optional[list[dict]] = None
    error: Optional[str] = None
    poll_after_seconds: int
