"""
Temporary migration router for archive uploads during data migration.
TODO: Remove this file and its registration in main.py after migration is complete.
"""
import os
import logging
import json
import tarfile
import zipfile
import shutil
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from app.schemas.migration import ArchiveContentType, FileFormat, MigrationUploadResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Base path for crawler storage - matches the PHP script configuration
MIGRATION_BASE_PATH = "/mnt/data/docker/volumes/rag-hp-pub_crawler_data/_data"


def get_storage_subpath(content_type: ArchiveContentType, domain_id: str) -> str:
    """
    Returns the correct storage subdirectory based on content type.
    Matches the directory structure used by the crawler and PHP scripts.
    """
    if content_type == ArchiveContentType.DATASET:
        return os.path.join("storage", "datasets", domain_id)
    elif content_type == ArchiveContentType.DATASET_NFR:
        return os.path.join("storage", "datasets", f"nfr-{domain_id}")
    elif content_type == ArchiveContentType.DATASET_ERROR:
        return os.path.join("storage", "datasets", f"error-{domain_id}")
    elif content_type == ArchiveContentType.REQUEST_QUEUES:
        return os.path.join("storage", "request_queues", domain_id)
    elif content_type == ArchiveContentType.REQUEST_URLS:
        return os.path.join("storage", "requests_urls", domain_id)
    elif content_type == ArchiveContentType.MISCELLANEOUS:
        return os.path.join("storage", "miscellaneous", domain_id)
    else:
        raise ValueError(f"Unknown content type: {content_type}")


def count_files_in_directory(path: str) -> int:
    """Count all files recursively in a directory."""
    count = 0
    for root, dirs, files in os.walk(path):
        count += len(files)
    return count


def detect_file_format(filename: str) -> FileFormat:
    """Auto-detect file format from filename extension."""
    lower_name = filename.lower()
    if lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz'):
        return FileFormat.TAR_GZ
    elif lower_name.endswith('.zip'):
        return FileFormat.ZIP
    elif lower_name.endswith('.tar'):
        return FileFormat.TAR
    else:
        # Default to tar.gz if unknown
        return FileFormat.TAR_GZ


def extract_archive(archive_path: str, file_format: FileFormat, destination: str) -> int:
    """
    Extract an archive to the destination directory.
    Returns the number of files extracted.
    """
    if file_format == FileFormat.TAR_GZ:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=destination)
    elif file_format == FileFormat.TAR:
        with tarfile.open(archive_path, "r:") as tar:
            tar.extractall(path=destination)
    elif file_format == FileFormat.ZIP:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(destination)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")
    
    return count_files_in_directory(destination)


@router.post("/upload/{domain_id}", response_model=MigrationUploadResponse)
async def upload_migration_archive(
    domain_id: str,
    archive: UploadFile = File(..., description="The archive file to upload and extract."),
    content_type: ArchiveContentType = Form(..., description="Type of content: dataset, dataset_nfr, dataset_error, request_queues, request_urls, miscellaneous."),
    is_crawl_finished: bool = Form(..., description="Indicates if the crawl is complete."),
    end_date: Optional[str] = Form(None, description="End date of the crawl (ISO format). Uses current time if empty and crawl is finished."),
    file_format: Optional[FileFormat] = Form(None, description="File format (auto-detected from filename if not provided).")
):
    """
    Temporary endpoint for migration: Upload and extract an archive to the domain's storage.
    
    - **domain_id**: The ID of the domain (used as directory name)
    - **archive**: The archive file (tar.gz, zip, or tar)
    - **content_type**: Type of content being uploaded (dataset, request_queues, etc.)
    - **is_crawl_finished**: Whether the crawl is complete
    - **end_date**: Optional end date (defaults to now if crawl is finished and this is empty)
    - **file_format**: Optional file format (auto-detected if not provided)
    
    Based on content_type, the archive will be extracted to:
    - dataset: `/mnt/data/.../storage/datasets/{domain_id}`
    - dataset_nfr: `/mnt/data/.../storage/datasets/nfr-{domain_id}`
    - dataset_error: `/mnt/data/.../storage/datasets/error-{domain_id}`
    - request_queues: `/mnt/data/.../storage/request_queues/{domain_id}`
    - request_urls: `/mnt/data/.../storage/requests_urls/{domain_id}`
    - miscellaneous: `/mnt/data/.../storage/miscellaneous/{domain_id}`
    
    If `is_crawl_finished=true` and no `_completion_marker.json` exists in the domain's
    base storage directory, one will be created.
    """
    # Determine file format
    actual_format = file_format or detect_file_format(archive.filename or "archive.tar.gz")
    
    # Construct storage paths
    subpath = get_storage_subpath(content_type, domain_id)
    storage_path = os.path.join(MIGRATION_BASE_PATH, domain_id, subpath)
    # Base storage for completion marker
    base_storage_path = os.path.join(MIGRATION_BASE_PATH, domain_id, "storage")
    
    logger.info(f"Migration upload started for domain_id={domain_id}, content_type={content_type}, format={actual_format}, is_crawl_finished={is_crawl_finished}")
    
    try:
        # Create storage directory if it doesn't exist
        os.makedirs(storage_path, exist_ok=True)
        logger.info(f"Storage directory ensured: {storage_path}")
        
        # Save uploaded archive to a temporary file
        suffix = f".{actual_format.value}" if '.' not in actual_format.value else actual_format.value
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_path = tmp_file.name
            # Stream the file to disk to handle large files
            shutil.copyfileobj(archive.file, tmp_file)
        
        logger.info(f"Archive saved to temporary file: {tmp_path}")
        
        try:
            # Extract the archive
            files_count = extract_archive(tmp_path, actual_format, storage_path)
            logger.info(f"Archive extracted to {storage_path}, {files_count} files")
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
        # Handle completion marker (in base storage directory)
        completion_marker_created = False
        os.makedirs(base_storage_path, exist_ok=True)
        marker_path = os.path.join(base_storage_path, "_completion_marker.json")
        
        if is_crawl_finished and not os.path.exists(marker_path):
            # Parse end_date or use current time
            if end_date:
                try:
                    parsed_end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    # Fallback to current time if parsing fails
                    logger.warning(f"Could not parse end_date '{end_date}', using current time")
                    parsed_end_date = datetime.utcnow()
            else:
                parsed_end_date = datetime.utcnow()
            
            # Create completion marker - format matches crawler_manager.py
            marker_data = {
                "final_status": "finished",
                "exit_code": 2,  # Node.js success exit code
                "end_timestamp": parsed_end_date.isoformat()
            }
            
            with open(marker_path, "w") as f:
                json.dump(marker_data, f, indent=2)
            
            completion_marker_created = True
            logger.info(f"Completion marker created at {marker_path}")
        
        return MigrationUploadResponse(
            success=True,
            message="Archive uploaded and extracted successfully.",
            domain_id=domain_id,
            storage_path=storage_path,
            content_type=content_type,
            completion_marker_created=completion_marker_created,
            extracted_files_count=files_count
        )
        
    except Exception as e:
        logger.error(f"Migration upload failed for domain_id={domain_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process migration archive: {str(e)}"
        )
