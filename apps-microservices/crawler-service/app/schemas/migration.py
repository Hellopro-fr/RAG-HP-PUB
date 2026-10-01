"""
Schemas for temporary migration endpoints.
TODO: Remove this file after migration is complete.
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ArchiveContentType(str, Enum):
    """
    Type of content being uploaded in the archive.
    Matches the directory structure used by the crawler storage.
    """
    DATASET = "dataset"              # datasets/{domain}
    DATASET_NFR = "dataset_nfr"      # datasets/nfr-{domain}
    DATASET_ERROR = "dataset_error"  # datasets/error-{domain}
    REQUEST_QUEUES = "request_queues"  # request_queues/{domain}
    REQUEST_URLS = "request_urls"    # requests_urls/{domain}
    MISCELLANEOUS = "miscellaneous"  # miscellaneous/{domain}


class FileFormat(str, Enum):
    """Supported file formats for the archive."""
    TAR_GZ = "tar.gz"
    ZIP = "zip"
    TAR = "tar"


class MigrationUploadResponse(BaseModel):
    """Response model for migration archive upload endpoint."""
    success: bool
    message: str
    domain_id: str
    domain_name: Optional[str] = Field(None, description="The domain name (e.g., example.com) used for directory structure.")
    storage_path: str
    content_type: ArchiveContentType = Field(
        ...,
        description="The type of content that was uploaded."
    )
    completion_marker_created: bool = Field(
        False,
        description="Whether a _completion_marker.json was created during this upload."
    )
    extracted_files_count: Optional[int] = Field(
        None,
        description="Number of files extracted from the archive."
    )


class MigrationPullRequest(BaseModel):
    """Payload for the pull-from-Ecritel endpoint."""
    domain_name: str = Field(..., description="Domain name (e.g. example.com), used for subdirectory structure.")
    content_types: List[ArchiveContentType] = Field(..., description="List of content types to pull.")
    source_url_base: str = Field(..., description="Base URL of the Ecritel serve endpoint (without query string).")
    token: str = Field(..., description="Auth token shared with Ecritel.")
    is_crawl_finished: bool = Field(True, description="Whether the crawl is complete (creates _completion_marker.json).")
    end_date: Optional[str] = Field(None, description="Crawl end date (ISO format). Uses current time if empty.")


class MigrationPullContentResult(BaseModel):
    """Result for a single content_type pull."""
    success: bool
    extracted_files_count: int = 0
    bytes_downloaded: int = 0
    error: Optional[str] = None


class MigrationPullResponse(BaseModel):
    """Response model for the pull endpoint."""
    success: bool
    domain_id: str
    domain_name: str
    storage_path: str
    completion_marker_created: bool = False
    results: Dict[str, MigrationPullContentResult] = Field(default_factory=dict)
