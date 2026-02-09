"""
Schemas for temporary migration endpoints.
TODO: Remove this file after migration is complete.
"""
from enum import Enum
from typing import Optional
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
