from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

class CrawlRequest(BaseModel):
    id: str = Field(..., description="An identifier for the crawl job, e.g., from a database.", example="domaine_123")
    domain: str = Field(..., description="The domain name being crawled.", example="example.com")
    start_url: HttpUrl = Field(..., description="The initial URL to start crawling from.", example="https://example.com")
    callback_url: HttpUrl = Field(..., description="URL to be called when the crawl finishes.", example="https://api.example.com/crawl_finished_hook")

    # Optional parameters mirroring the old shell script
    type_crawling: Optional[str] = Field(None, example="default")
    method: Optional[str] = Field(None, description="Optional method flag for post-processing.", example="test")
    drop_data: Optional[bool] = Field(False, description="Whether to drop existing data before starting.")
    skip_question_mark: Optional[bool] = Field(False, description="Process and filter URLs with '?'")
    skip_diez: Optional[bool] = Field(False, description="Process and filter URLs with '#'")
    to_keep: Optional[List[str]] = Field(None, description="List of URL query parameters to keep.", example=["page", "id"])
    to_remove: Optional[List[str]] = Field(None, description="List of URL query parameters to remove.", example=["utm_source"])
    proxy_apify: Optional[str] = Field(None, description="Apify proxy key.", example="my_apify_proxy_key")
    bypass_question_mark: Optional[bool] = Field(False, description="Bypass filtering of URLs with '?'")
    bypass_diez: Optional[bool] = Field(False, description="Bypass filtering of URLs with '#'")
    break_limit: Optional[bool] = Field(False, description="Enable break limit of 5000 URLs to be crawled.")
    per_crawl: Optional[int] = Field(0, description="Number of URLs to crawl per job. 0 means unlimited.", example=1000)
    per_minute: Optional[int] = Field(100, description="Crawling speed in URLs per minute. 0 means unlimited.", example=100)

class CrawlResponse(BaseModel):
    message: str
    crawl_id: str

class StopResponse(BaseModel):
    message: str
    crawl_id: str

class CrawlStatus(BaseModel):
    crawl_id: str
    status: str = Field(..., description="Current status: running, stopping, finished, failed", example="running")
    domain: str
    start_url: HttpUrl
    start_time: datetime
    urls_crawled: int = Field(0, description="Number of URLs successfully crawled and saved.")
    last_activity: Optional[datetime] = Field(None, description="Timestamp of the last saved URL.")