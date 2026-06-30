from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from datetime import datetime

class IncludeInArchive(str, Enum):
    """Enumeration of components that can be included in the results archive."""
    DATASET = "dataset"
    DATASET_NFR = "dataset_nfr"
    DATASET_ERROR = "dataset_error"
    DATASET_UPDATE = "dataset_update"
    REQUEST_QUEUES = "request_queues"
    REQUEST_URLS = "request_urls"
    MISCELLANEOUS = "miscellaneous"

class CrawlMode(str, Enum):
    """Mode of operation for the crawler."""
    STANDARD = "standard"
    UPDATE = "update"

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

class PruneResponse(BaseModel):
    """Response for the archive cleanup operation."""
    deleted_count: int
    retained_count: int
    errors: int
    message: str

class UpdateThresholds(BaseModel):
    """Thresholds for aborting an update job."""
    max_errors: Optional[int] = Field(None, description="Legacy: Abort if error count exceeds this value.")
    max_redirects: Optional[int] = Field(None, description="Legacy: Abort if redirect count exceeds this value.")
    max_new_urls: Optional[int] = Field(None, description="Legacy: Abort if new URL discovery count exceeds this value.")
    
    # New V1 Circuit Breaker Params
    min_sample: Optional[int] = Field(None, description="Standard Mode: Minimum processed URLs before checking percentages (default: 50).")
    max_error_rate: Optional[float] = Field(None, description="Standard Mode: Abort if error rate exceeds this ratio (e.g. 0.15 for 15%).")
    max_redirect_rate: Optional[float] = Field(None, description="Standard Mode: Abort if redirect rate exceeds this ratio (e.g. 0.30 for 30%).")
    max_growth_rate: Optional[float] = Field(None, description="Standard Mode: Abort if new URLs exceed this ratio relative to previous total (e.g. 0.50 for 50%).")
    
    max_abs_errors: Optional[int] = Field(None, description="Micro Mode: Abort if absolute error count exceeds this value (default: 5).")
    max_abs_redirects: Optional[int] = Field(None, description="Micro Mode: Abort if absolute redirect count exceeds this value (default: 10).")
    max_abs_new: Optional[int] = Field(None, description="Micro Mode: Abort if absolute new URL count exceeds this value (default: 20).")

class CrawlRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="An identifier for the crawl job, e.g., from a database.", example="domaine_123")
    domain: str = Field(..., description="The domain name being crawled.", example="example.com")
    start_url: HttpUrl = Field(..., description="The initial URL to start crawling from.", example="https://example.com")
    callback_url: HttpUrl = Field(..., description="URL to be called when the crawl finishes successfully.", example="https://api.example.com/crawl_finished_hook")
    failure_callback_url: Optional[HttpUrl] = Field(None, description="URL to be called if the crawl job fails.", example="https://api.example.com/crawl_failed_hook")

    # Update Mode Parameters
    crawl_mode: CrawlMode = Field(CrawlMode.STANDARD, description="Mode of operation: 'standard' for fresh crawl, 'update' for diff check.")
    previous_crawl_id: Optional[str] = Field(None, description="ID of the previous crawl to update from (required if mode is 'update').")
    update_thresholds: Optional[UpdateThresholds] = Field(None, description="Circuit breaker thresholds for update mode.")

    # Optional parameters mirroring the old shell script (with legacy aliases)
    type_crawling: Optional[str] = Field(None, example="default", alias="typecrawling")
    method: Optional[str] = Field(None, description="Optional method flag for post-processing.", example="test")
    drop_data: Optional[bool] = Field(False, description="Whether to drop existing data before starting.", alias="dropdata")
    skip_question_mark: Optional[bool] = Field(False, description="Process and filter URLs with '?'", alias="skipquestionmark")
    skip_diez: Optional[bool] = Field(False, description="Process and filter URLs with '#'", alias="skipdiez")
    to_keep: Optional[List[str]] = Field(None, description="List of URL query parameters to keep.", example=["page", "id"], alias="tokeep")
    to_remove: Optional[List[str]] = Field(None, description="List of URL query parameters to remove.", example=["utm_source"], alias="toremove")
    proxy_apify: Optional[str] = Field(None, description="Apify proxy key.", example="my_apify_proxy_key", alias="proxyapify")
    bypass_question_mark: Optional[bool] = Field(False, description="Bypass filtering of URLs with '?'", alias="bypassquestionmark")
    bypass_diez: Optional[bool] = Field(False, description="Bypass filtering of URLs with '#'", alias="bypassdiez")
    break_limit: Optional[bool] = Field(True, description="Bypass the 5000 URLs crawl limit.", alias="breaklimit")
    queue_limit: Optional[int] = Field(None, description="Maximum number of URLs allowed in the request queue before stopping.", alias="queuelimit")
    bypass_queue: Optional[bool] = Field(False, description="Bypass the queue size limit set by queuelimit.", alias="bypassqueue")
    per_crawl: Optional[int] = Field(0, description="Number of URLs to crawl per job. 0 means unlimited.", example=1000, alias="percrawl")
    per_minute: Optional[int] = Field(100, description="Crawling speed in URLs per minute. 0 means unlimited.", example=100, alias="perminute")
    
    # Camoufox Integration
    camoufox: Optional[bool] = Field(True, description="Use Camoufox stealth browser (default). Set to false to fall back to Playwright multi-browser rotation.")

class CrawlResponse(BaseModel):
    message: str
    crawl_id: str

class StopResponse(BaseModel):
    message: str
    crawl_id: str

class ArchiveResponse(BaseModel):
    message: str
    crawl_id: str
    archive_status: str = Field("pending_upload", description="'pending_upload' = local archive created, awaiting daemon upload to GCS.")
    archive_size_bytes: Optional[int] = Field(None, description="Size of the archive file in bytes.")

class StashResponse(BaseModel):
    """Response for POST /stash/{crawl_id} — 202 Accepted shape."""
    crawl_id: str
    status: str = Field("stashing", description="Always 'stashing' when 202 returned; data is in /app/stash awaiting daemon upload to GCS.")
    stash_path: str = Field(..., description="Target GCS object path (gs://{bucket}/stash/{id}.tar.gz).")
    stashed_at: datetime = Field(..., description="ISO 8601 UTC timestamp written to Redis job_data.")


class UnstashResponse(BaseModel):
    """Response for POST /unstash/{crawl_id} — 200 OK shape."""
    crawl_id: str
    status: str = Field("unstashed", description="Always 'unstashed' when 200 returned.")
    restored_to: str = Field(..., description="Local storage path where the archive was extracted.")
    elapsed_seconds: float = Field(..., description="Total round-trip wall-time (request marker write -> Redis flag clear).")
    gcs_cleanup_status: Optional[str] = Field(
        None,
        description="'cleaned' when the GCS source was deleted within UNSTASH_CLEANUP_GRACE_SECONDS, 'deferred' when the cleanup marker did not arrive in time (an orphan GCS object remains and must be manually cleaned)."
    )


class RetrieveResponse(BaseModel):
    message: str
    crawl_id: str
    status: str = Field(..., description="Restored job status after retrieval (e.g., 'finished').")
    domain: str

class FailedCallback(BaseModel):
    crawl_id: str
    webhook_type: str = Field(..., description="Type of webhook: success, failure, or stop")
    url: str
    params: dict
    error: Optional[str] = None
    failed_at: datetime

class PendingCallbacksResponse(BaseModel):
    count: int
    callbacks: List[FailedCallback]

class CrawlStatus(BaseModel):
    crawl_id: str
    id_domaine: str # Legacy alias
    status: str = Field(..., description="Current status: running, stopping, finished, failed", example="running")
    domain: str
    start_url: HttpUrl
    start_time: datetime
    urls_crawled: int = Field(0, description="Number of URLs successfully crawled and saved.")
    error_urls_crawled: int = Field(0, description="Number of URLs that failed during crawling.")
    nfr_urls_crawled: int = Field(0, description="Number of URLs that were skipped for not being in French.")
    last_activity: Optional[datetime] = Field(None, description="Timestamp of the last saved URL.")
    last_heartbeat: Optional[datetime] = Field(None, description="Timestamp of the last monitor heartbeat for a running job.")
    is_error: Optional[str] = Field(
        None,
        description="Error category from _callback_payload.json "
                    "(e.g., 'stoppedManually', 'insufficientData', 'limitCrawl'). "
                    "Empty/null for successful crawls. Used by BO reconciliation "
                    "to route to the correct error branch."
    )
    stashed_at: Optional[str] = Field(None, description="ISO ts when data was moved to GCS stash; null if local.")
    downloaded_at: Optional[str] = Field(None, description="ISO ts of the last successful /results download (auto-stash grace start).")
    finished_at: Optional[str] = Field(None, description="ISO ts of the terminal transition (auto-stash safety-timeout start).")
    size_bytes: Optional[int] = Field(None, description="Estimated archive size in bytes (auto-stash disk-pressure ordering).")
    queue_total: Optional[int] = Field(None, description="Total URLs enqueued (Crawlee totalRequestCount); running/stopping jobs only, else null.")
    queue_remaining: Optional[int] = Field(None, description="URLs still pending in the queue (Crawlee pendingRequestCount); running/stopping jobs only, else null.")