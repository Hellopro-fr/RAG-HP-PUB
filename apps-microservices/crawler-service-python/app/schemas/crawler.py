from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

class IncludeInArchive(str, Enum):
    """Enumeration of components that can be included in the results archive."""
    DATASET = "dataset"
    DATASET_NFR = "dataset_nfr"
    DATASET_ERROR = "dataset_error"
    REQUEST_QUEUES = "request_queues"
    REQUEST_URLS = "request_urls"
    MISCELLANEOUS = "miscellaneous"

class CapacityResponse(BaseModel):
    running_jobs: int
    max_global_jobs: int
    is_full: bool

class ReindexResponse(BaseModel):
    """Summary of the re-indexing operation."""
    scanned_directories: int
    reindexed_jobs: int
    already_indexed: int
    errors: int

class CrawlRequest(BaseModel):
    id: str = Field(..., description="An identifier for the crawl job, e.g., from a database.", example="domaine_123")
    domain: str = Field(..., description="The domain name being crawled.", example="example.com")
    start_url: HttpUrl = Field(..., description="The initial URL to start crawling from.", example="https://example.com")
    callback_url: HttpUrl = Field(..., description="URL to be called when the crawl finishes successfully.", example="https://api.example.com/crawl_finished_hook")
    failure_callback_url: Optional[HttpUrl] = Field(None, description="URL to be called if the crawl job fails.", example="https://api.example.com/crawl_failed_hook")

    # Optional parameters mirroring the old shell script (with legacy aliases)
    type_crawling: Optional[str] = Field(None, example="default", alias="typecrawling")
    method: Optional[str] = Field(None, description="Optional method flag.", example="test")
    drop_data: Optional[bool] = Field(False, description="Drop existing data.", alias="dropdata")
    skip_question_mark: Optional[bool] = Field(False, description="Filter URLs with '?'", alias="skipquestionmark")
    skip_diez: Optional[bool] = Field(False, description="Filter URLs with '#'", alias="skipdiez")
    to_keep: Optional[List[str]] = Field(None, description="Params to keep.", example=["page"], alias="tokeep")
    to_remove: Optional[List[str]] = Field(None, description="Params to remove.", example=["utm"], alias="toremove")
    proxy_apify: Optional[str] = Field(None, description="Apify proxy key.", alias="proxyapify")
    bypass_question_mark: Optional[bool] = Field(False, description="Bypass '?' filter", alias="bypassquestionmark")
    bypass_diez: Optional[bool] = Field(False, description="Bypass '#' filter", alias="bypassdiez")
    break_limit: Optional[bool] = Field(False, description="Enable 5000 URLs limit.", alias="breaklimit")
    per_crawl: Optional[int] = Field(0, description="URLs per job.", example=1000, alias="percrawl")
    per_minute: Optional[int] = Field(100, description="Speed limit.", example=100, alias="perminute")

class CrawlResponse(BaseModel):
    message: str
    crawl_id: str

class StopResponse(BaseModel):
    message: str
    crawl_id: str

class ArchiveResponse(BaseModel):
    message: str
    gcs_url: str

class CrawlStatus(BaseModel):
    crawl_id: str
    id_domaine: str # Legacy ID alias
    status: str = Field(..., description="Current status: running, stopping, finished, failed", example="running")
    domain: str
    start_url: HttpUrl
    start_time: datetime
    urls_crawled: int = Field(0, description="Number of URLs successfully crawled and saved.")
    error_urls_crawled: int = Field(0, description="Number of URLs that failed during crawling.")
    nfr_urls_crawled: int = Field(0, description="Number of URLs that were skipped for not being in French.")
    last_activity: Optional[datetime] = Field(None, description="Timestamp of the last saved URL.")
    last_heartbeat: Optional[datetime] = Field(None, description="Timestamp of the last monitor heartbeat for a running job.")
