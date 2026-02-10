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

from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def get_storage_subpath(content_type: ArchiveContentType, domain_name: str) -> str:
    """
    Returns the correct storage subdirectory based on content type.
    Matches the directory structure used by the crawler and PHP scripts.
    Uses domain_name (e.g. 'example.com') for subdirectories.
    """
    if content_type == ArchiveContentType.DATASET:
        return os.path.join("storage", "datasets", domain_name)
    elif content_type == ArchiveContentType.DATASET_NFR:
        return os.path.join("storage", "datasets", f"nfr-{domain_name}")
    elif content_type == ArchiveContentType.DATASET_ERROR:
        return os.path.join("storage", "datasets", f"error-{domain_name}")
    elif content_type == ArchiveContentType.REQUEST_QUEUES:
        return os.path.join("storage", "request_queues", domain_name)
    elif content_type == ArchiveContentType.REQUEST_URLS:
        return os.path.join("storage", "requests_urls", domain_name)
    elif content_type == ArchiveContentType.MISCELLANEOUS:
        return os.path.join("storage", "miscellaneous", domain_name)
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


def reassemble_chunks(chunk_dir: str, output_path: str) -> None:
    """
    Reassemble split chunks into a single file.
    Chunks are expected to be named lexicographically (e.g. .partaa, .partab).
    """
    chunks = sorted(os.listdir(chunk_dir))
    with open(output_path, 'wb') as outfile:
        for chunk in chunks:
            chunk_path = os.path.join(chunk_dir, chunk)
            with open(chunk_path, 'rb') as infile:
                shutil.copyfileobj(infile, outfile)
    logger.info(f"Reassembled {len(chunks)} chunks from {chunk_dir} to {output_path}")


@router.post("/upload/{domain_id}", response_model=MigrationUploadResponse)
async def upload_migration_archive(
    domain_id: str,
    archive: UploadFile = File(..., description="The archive file or chunk to upload."),
    content_type: ArchiveContentType = Form(..., description="Type of content: dataset, dataset_nfr, dataset_error, request_queues, request_urls, miscellaneous."),
    is_crawl_finished: bool = Form(..., description="Indicates if the crawl is complete."),
    domain_name: Optional[str] = Form(None, description="The domain name (e.g. example.com). Used for directory structure. If not provided, domain_id is used."),
    end_date: Optional[str] = Form(None, description="End date of the crawl (ISO format). Uses current time if empty and crawl is finished."),
    file_format: Optional[FileFormat] = Form(None, description="File format (auto-detected from filename if not provided)."),
    total_parts: int = Form(1, description="Total number of parts if the upload is chunked (default 1)."),
    original_filename: Optional[str] = Form(None, description="Original filename for chunked uploads (e.g. dataset.tar.gz).")
):
    """
    Temporary endpoint for migration: Upload and extract an archive (or chunk) to the domain's storage.
    
    - **domain_id**: The ID of the domain (used as directory name)
    - **archive**: The archive file or chunk
    - **content_type**: Type of content being uploaded
    - **is_crawl_finished**: Whether the crawl is complete
    - **domain_name**: Domain name for subdirectory structure
    - **total_parts**: Total number of chunks (default 1)
    - **original_filename**: Original filename if chunked
    
    The archive will be extracted to:
    `/app/storage/{domain_id}/storage/{content_type_folder}/`
    
    If `total_parts > 1`, chunks are stored in:
    `/app/storage/temp_chunks/{domain_id}/{original_filename}/`
    until all parts are received, then reassembled and extracted.
    
    If `is_crawl_finished=true`, a `_completion_marker.json` is created.
    """
    # Determine file format and effective filename
    filename_to_use = original_filename or archive.filename or "archive.tar.gz"
    actual_format = file_format or detect_file_format(filename_to_use)
    
    # Use domain_name for subdirectories, fallback to domain_id if not provided
    eff_domain_name = domain_name if domain_name else domain_id
    
    # Construct storage paths using settings.CRAWLER_STORAGE_PATH (internal container path)
    subpath = get_storage_subpath(content_type, eff_domain_name)
    storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, domain_id, subpath)
    
    # Base storage for completion marker (root of domain_id)
    base_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, domain_id)
    
    logger.info(f"Migration upload started for domain_id={domain_id}, domain_name={eff_domain_name}, content_type={content_type}, format={actual_format}, parts={total_parts}")
    
    try:
        # Create storage directory if it doesn't exist (needed for final extraction)
        os.makedirs(storage_path, exist_ok=True)
        # Also ensure base path exists for marker
        os.makedirs(base_storage_path, exist_ok=True)
        
        logger.info(f"Storage directory ensured: {storage_path}")
        
        tmp_path = None
        extracted_count = 0
        
        if total_parts > 1:
            # Chunked upload logic
            chunk_dir = os.path.join(settings.CRAWLER_STORAGE_PATH, "temp_chunks", domain_id, filename_to_use)
            os.makedirs(chunk_dir, exist_ok=True)
            
            # Save the chunk
            chunk_path = os.path.join(chunk_dir, archive.filename)
            with open(chunk_path, "wb") as f:
                shutil.copyfileobj(archive.file, f)
            
            logger.info(f"Saved chunk {archive.filename} to {chunk_dir}")
            
            # Check if all chunks are present
            current_chunks = len(os.listdir(chunk_dir))
            if current_chunks < total_parts:
                return MigrationUploadResponse(
                    success=True,
                    message=f"Chunk {archive.filename} received. {current_chunks}/{total_parts} parts.",
                    domain_id=domain_id,
                    domain_name=eff_domain_name,
                    storage_path=storage_path,
                    content_type=content_type,
                    completion_marker_created=False,
                    extracted_files_count=0
                )
            
            # All chunks present, reassemble
            logger.info(f"All {total_parts} chunks received. Reassembling...")
            suffix = f".{actual_format.value}" if '.' not in actual_format.value else actual_format.value
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_path = tmp_file.name
            
            reassemble_chunks(chunk_dir, tmp_path)
            
            # Cleanup chunks directory
            shutil.rmtree(chunk_dir)
            logger.info("Chunks reassembled and temp directory cleaned.")
            
        else:
            # Standard single file upload
            suffix = f".{actual_format.value}" if '.' not in actual_format.value else actual_format.value
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_path = tmp_file.name
                shutil.copyfileobj(archive.file, tmp_file)
            logger.info(f"Archive saved to temporary file: {tmp_path}")

        # Extract the archive (whether reassembled or single)
        try:
            extracted_count = extract_archive(tmp_path, actual_format, storage_path)
            logger.info(f"Archive extracted to {storage_path}, {extracted_count} files")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
        # Handle completion marker
        completion_marker_created = False
        marker_path = os.path.join(base_storage_path, "_completion_marker.json")
        
        if is_crawl_finished and not os.path.exists(marker_path):
            if end_date:
                try:
                    parsed_end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"Could not parse end_date '{end_date}', using current time")
                    parsed_end_date = datetime.utcnow()
            else:
                parsed_end_date = datetime.utcnow()
            
            # Create completion marker - format matches crawler_manager.py
            marker_data = {
                "final_status": "finished",
                "exit_code": 2,
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
            domain_name=eff_domain_name,
            storage_path=storage_path,
            content_type=content_type,
            completion_marker_created=completion_marker_created,
            extracted_files_count=extracted_count
        )
        
    except Exception as e:
        logger.error(f"Migration upload failed for domain_id={domain_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process migration archive: {str(e)}"
        )
