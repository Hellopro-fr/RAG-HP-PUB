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
import time
import anyio
from datetime import datetime, timezone
from typing import Optional

import httpx

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from app.schemas.migration import (
    ArchiveContentType,
    FileFormat,
    MigrationUploadResponse,
    MigrationPullRequest,
    MigrationPullResponse,
    MigrationPullContentResult,
)

from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

STALE_CHUNK_TTL_SECONDS = 3600  # 1 hour


def sanitize_path_component(value: str, field_name: str) -> str:
    """
    Sanitize a value used as a path component to prevent path traversal attacks.
    Rejects values containing '..', '/', '\\', or null bytes.
    """
    if not value or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{field_name}' cannot be empty."
        )
    if '\x00' in value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{field_name}' contains invalid null bytes."
        )
    if '..' in value or '/' in value or '\\' in value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{field_name}' contains invalid path characters ('..' or path separators)."
        )
    return value.strip()


def cleanup_stale_chunks() -> None:
    """
    Remove chunk directories older than STALE_CHUNK_TTL_SECONDS.
    Called at the start of each upload to prevent orphan accumulation.
    """
    chunks_base = os.path.join(settings.CRAWLER_STORAGE_PATH, "temp_chunks")
    if not os.path.isdir(chunks_base):
        return

    now = time.time()
    try:
        for domain_dir in os.listdir(chunks_base):
            domain_path = os.path.join(chunks_base, domain_dir)
            if not os.path.isdir(domain_path):
                continue
            for chunk_group in os.listdir(domain_path):
                chunk_group_path = os.path.join(domain_path, chunk_group)
                if not os.path.isdir(chunk_group_path):
                    continue
                mtime = os.path.getmtime(chunk_group_path)
                if now - mtime > STALE_CHUNK_TTL_SECONDS:
                    shutil.rmtree(chunk_group_path, ignore_errors=True)
                    logger.info(f"Cleaned up stale chunk directory: {chunk_group_path}")
            # Remove empty domain directories
            if not os.listdir(domain_path):
                os.rmdir(domain_path)
    except Exception as e:
        logger.warning(f"Error during stale chunk cleanup: {e}")


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


def _get_safe_tar_members(tar: tarfile.TarFile, destination: str):
    """
    Filter tar members to prevent path traversal and symlink attacks.
    Rejects members with absolute paths, '..' components, or symlinks
    pointing outside the destination.
    """
    dest_real = os.path.realpath(destination)
    for member in tar.getmembers():
        member_path = os.path.normpath(member.name)
        # Reject absolute paths
        if os.path.isabs(member_path):
            logger.warning(f"Skipping tar member with absolute path: {member.name}")
            continue
        # Reject paths with '..' traversal
        if '..' in member_path.split(os.sep):
            logger.warning(f"Skipping tar member with path traversal: {member.name}")
            continue
        # Reject symlinks pointing outside destination
        if member.issym() or member.islnk():
            link_target = os.path.normpath(os.path.join(destination, os.path.dirname(member_path), member.linkname))
            if not os.path.realpath(link_target).startswith(dest_real):
                logger.warning(f"Skipping tar member with external symlink: {member.name} -> {member.linkname}")
                continue
        # Verify resolved path stays within destination
        resolved = os.path.realpath(os.path.join(destination, member_path))
        if not resolved.startswith(dest_real):
            logger.warning(f"Skipping tar member resolving outside destination: {member.name}")
            continue
        yield member


def extract_archive_to_dir(archive_path: str, file_format: FileFormat, destination: str) -> None:
    """
    Extract an archive to the destination directory (raw extraction, no nesting fix).
    Tar members are filtered to prevent path traversal and symlink attacks.
    """
    if file_format in (FileFormat.TAR_GZ, FileFormat.TAR):
        mode = "r:gz" if file_format == FileFormat.TAR_GZ else "r:"
        with tarfile.open(archive_path, mode) as tar:
            safe_members = list(_get_safe_tar_members(tar, destination))
            tar.extractall(path=destination, members=safe_members)
    elif file_format == FileFormat.ZIP:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            dest_real = os.path.realpath(destination)
            for info in zip_ref.infolist():
                member_path = os.path.normpath(info.filename)
                if os.path.isabs(member_path) or '..' in member_path.split(os.sep):
                    logger.warning(f"Skipping zip member with unsafe path: {info.filename}")
                    continue
                resolved = os.path.realpath(os.path.join(destination, member_path))
                if not resolved.startswith(dest_real):
                    logger.warning(f"Skipping zip member resolving outside destination: {info.filename}")
                    continue
                zip_ref.extract(info, destination)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def extract_and_fix_nesting(archive_path: str, file_format: FileFormat, target_dir: str) -> int:
    """
    Extract an archive and automatically fix double nesting.
    
    Client archives may contain either:
    - Flat files: fichier1.json, fichier2.json
    - A single subdirectory: example.com/fichier1.json
    
    In the second case, the subdirectory contents are moved up one level
    to avoid double nesting (since target_dir already includes the domain name).
    
    Returns the number of files in the final target directory.
    """
    # 1. Extract to a temporary directory
    temp_extract_dir = tempfile.mkdtemp(prefix="migration_extract_")
    
    try:
        extract_archive_to_dir(archive_path, file_format, temp_extract_dir)
        
        # 2. Check for double nesting: single subdirectory as only content
        contents = os.listdir(temp_extract_dir)
        
        if (len(contents) == 1
                and os.path.isdir(os.path.join(temp_extract_dir, contents[0]))):
            # Double nesting detected: archive contains a single directory
            nested_dir = os.path.join(temp_extract_dir, contents[0])
            source_dir = nested_dir
            logger.info(f"Double nesting detected: archive contains single directory '{contents[0]}'. Unwrapping.")
        else:
            # Flat files or multiple items: use directly
            source_dir = temp_extract_dir
            logger.info(f"No nesting detected: {len(contents)} items at root level.")
        
        # 3. Move contents to the final target directory
        os.makedirs(target_dir, exist_ok=True)
        for item in os.listdir(source_dir):
            src = os.path.join(source_dir, item)
            dst = os.path.join(target_dir, item)
            # If destination exists (e.g. incremental uploads), overwrite
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)
        
        return count_files_in_directory(target_dir)
    
    finally:
        # 4. Cleanup temp extraction directory
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)


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
    # Sanitize inputs to prevent path traversal
    domain_id = sanitize_path_component(domain_id, "domain_id")
    if domain_name:
        domain_name = sanitize_path_component(domain_name, "domain_name")

    # Cleanup stale chunks from previous failed uploads (run in thread to avoid blocking event loop)
    await anyio.to_thread.run_sync(cleanup_stale_chunks)

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
            safe_chunk_name = sanitize_path_component(archive.filename or f"chunk_{total_parts}", "chunk_filename")
            chunk_path = os.path.join(chunk_dir, safe_chunk_name)
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

        # Extract the archive (whether reassembled or single) with auto nesting fix
        try:
            extracted_count = extract_and_fix_nesting(tmp_path, actual_format, storage_path)
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
                    parsed_end_date = datetime.now(timezone.utc)
            else:
                parsed_end_date = datetime.now(timezone.utc)
            
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

            # Create _status_snapshot.json so GET /status/{crawl_id} and
            # POST /archive/{crawl_id} have proper domain/URL metadata
            # instead of falling back to "unknown" from missing crawler.log
            snapshot_path = os.path.join(base_storage_path, "_status_snapshot.json")
            if not os.path.exists(snapshot_path):
                datasets_base = os.path.join(base_storage_path, "storage", "datasets")
                dataset_dir = os.path.join(datasets_base, eff_domain_name)
                nfr_dir = os.path.join(datasets_base, f"nfr-{eff_domain_name}")
                error_dir = os.path.join(datasets_base, f"error-{eff_domain_name}")

                snapshot_data = {
                    "crawl_id": domain_id,
                    "id_domaine": domain_id,
                    "status": "finished",
                    "domain": eff_domain_name,
                    "start_url": f"https://www.{eff_domain_name}/",
                    "start_time": parsed_end_date.isoformat(),
                    "urls_crawled": count_files_in_directory(dataset_dir) if os.path.isdir(dataset_dir) else 0,
                    "error_urls_crawled": count_files_in_directory(error_dir) if os.path.isdir(error_dir) else 0,
                    "nfr_urls_crawled": count_files_in_directory(nfr_dir) if os.path.isdir(nfr_dir) else 0,
                    "last_activity": parsed_end_date.isoformat(),
                    "last_heartbeat": None
                }

                with open(snapshot_path, "w") as f:
                    json.dump(snapshot_data, f, indent=2)
                logger.info(f"Status snapshot created at {snapshot_path}")

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


async def _download_and_extract_one(
    client: httpx.AsyncClient,
    source_url_base: str,
    token: str,
    domain_id: str,
    eff_domain_name: str,
    content_type: ArchiveContentType,
    base_storage_path: str,
) -> MigrationPullContentResult:
    """
    Télécharge UN content_type depuis Ecritel via streaming HTTP, puis extrait
    dans le bon sous-dossier du storage du conteneur.

    Idempotent : si appelé plusieurs fois, écrase le contenu précédent
    (extract_and_fix_nesting overwrite la destination).
    """
    tmp_path = None
    try:
        params = {
            "id_domaine": domain_id,
            "content_type": content_type.value,
            "token": token,
        }

        # Sauvegarde dans un tempfile via streaming pour gérer les gros fichiers
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
            tmp_path = tmp.name

        bytes_downloaded = 0
        async with client.stream("GET", source_url_base, params=params) as resp:
            if resp.status_code == 404:
                # Fichier absent côté Ecritel : on le note mais ce n'est pas forcément fatal
                # (par ex. dataset_error peut ne pas exister)
                logger.info(f"[pull] {content_type.value} not found on Ecritel for domain_id={domain_id} (HTTP 404)")
                return MigrationPullContentResult(
                    success=False,
                    error=f"HTTP 404: file not found on Ecritel for content_type={content_type.value}"
                )
            if resp.status_code != 200:
                body = await resp.aread()
                return MigrationPullContentResult(
                    success=False,
                    error=f"HTTP {resp.status_code}: {body[:500].decode('utf-8', errors='ignore')}"
                )

            with open(tmp_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=8 * 1024 * 1024):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)

        logger.info(f"[pull] {content_type.value} downloaded ({bytes_downloaded} bytes) for domain_id={domain_id}")

        # Extraction dans le bon sous-dossier
        subpath = get_storage_subpath(content_type, eff_domain_name)
        target_dir = os.path.join(base_storage_path, subpath)

        extracted_count = await anyio.to_thread.run_sync(
            extract_and_fix_nesting, tmp_path, FileFormat.TAR_GZ, target_dir
        )

        return MigrationPullContentResult(
            success=True,
            extracted_files_count=extracted_count,
            bytes_downloaded=bytes_downloaded,
        )

    except Exception as e:
        logger.error(f"[pull] Error for content_type={content_type.value}, domain_id={domain_id}: {e}", exc_info=True)
        return MigrationPullContentResult(success=False, error=str(e))

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post("/pull/{domain_id}", response_model=MigrationPullResponse)
async def pull_migration_archives(
    domain_id: str,
    payload: MigrationPullRequest,
):
    """
    Endpoint inverse de /upload : le service GCP télécharge les .tar.gz directement
    depuis Ecritel, évitant la limite de l'api-gateway et le chunking côté client.

    Pour chaque content_type, fait un GET streaming sur source_url_base avec
    auth token, puis extrait dans le storage volume.

    Crée _completion_marker.json + _status_snapshot.json si is_crawl_finished=true
    et qu'au moins un download a réussi.
    """
    # Sanitize
    domain_id = sanitize_path_component(domain_id, "domain_id")
    eff_domain_name = sanitize_path_component(payload.domain_name, "domain_name")

    if not payload.content_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content_types must not be empty",
        )

    base_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, domain_id)
    storage_path = os.path.join(base_storage_path, "storage")
    os.makedirs(base_storage_path, exist_ok=True)

    logger.info(
        f"[pull] domain_id={domain_id}, domain_name={eff_domain_name}, "
        f"content_types={[c.value for c in payload.content_types]}"
    )

    # === Téléchargement de chaque content_type ===
    results: Dict[str, MigrationPullContentResult] = {}

    # Timeout généreux pour les gros fichiers (10 min total)
    timeout = httpx.Timeout(connect=30.0, read=600.0, write=60.0, pool=30.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for content_type in payload.content_types:
            result = await _download_and_extract_one(
                client=client,
                source_url_base=payload.source_url_base,
                token=payload.token,
                domain_id=domain_id,
                eff_domain_name=eff_domain_name,
                content_type=content_type,
                base_storage_path=base_storage_path,
            )
            results[content_type.value] = result

    # === Completion marker + status snapshot (si au moins un succès) ===
    any_success = any(r.success for r in results.values())
    completion_marker_created = False

    if payload.is_crawl_finished and any_success:
        marker_path = os.path.join(base_storage_path, "_completion_marker.json")
        if not os.path.exists(marker_path):
            if payload.end_date:
                try:
                    parsed_end_date = datetime.fromisoformat(payload.end_date.replace("Z", "+00:00"))
                except ValueError:
                    parsed_end_date = datetime.now(timezone.utc)
            else:
                parsed_end_date = datetime.now(timezone.utc)

            marker_data = {
                "final_status": "finished",
                "exit_code": 2,
                "end_timestamp": parsed_end_date.isoformat(),
            }
            with open(marker_path, "w") as f:
                json.dump(marker_data, f, indent=2)
            completion_marker_created = True
            logger.info(f"[pull] Completion marker created at {marker_path}")

            # Status snapshot
            snapshot_path = os.path.join(base_storage_path, "_status_snapshot.json")
            if not os.path.exists(snapshot_path):
                datasets_base = os.path.join(base_storage_path, "storage", "datasets")
                dataset_dir = os.path.join(datasets_base, eff_domain_name)
                nfr_dir = os.path.join(datasets_base, f"nfr-{eff_domain_name}")
                error_dir = os.path.join(datasets_base, f"error-{eff_domain_name}")

                snapshot_data = {
                    "crawl_id": domain_id,
                    "id_domaine": domain_id,
                    "status": "finished",
                    "domain": eff_domain_name,
                    "start_url": f"https://www.{eff_domain_name}/",
                    "start_time": parsed_end_date.isoformat(),
                    "urls_crawled": count_files_in_directory(dataset_dir) if os.path.isdir(dataset_dir) else 0,
                    "error_urls_crawled": count_files_in_directory(error_dir) if os.path.isdir(error_dir) else 0,
                    "nfr_urls_crawled": count_files_in_directory(nfr_dir) if os.path.isdir(nfr_dir) else 0,
                    "last_activity": parsed_end_date.isoformat(),
                    "last_heartbeat": None,
                }
                with open(snapshot_path, "w") as f:
                    json.dump(snapshot_data, f, indent=2)
                logger.info(f"[pull] Status snapshot created at {snapshot_path}")

    overall_success = all(r.success for r in results.values())

    return MigrationPullResponse(
        success=overall_success,
        domain_id=domain_id,
        domain_name=eff_domain_name,
        storage_path=storage_path,
        completion_marker_created=completion_marker_created,
        results=results,
    )
