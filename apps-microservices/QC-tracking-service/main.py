"""
QC Tracking Service - Interface de visualisation des fichiers tracking
"""
import os
import io
import zipfile
from datetime import datetime, date, timedelta
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="QC Tracking Service", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Base path for tracking files - mounted via Docker volume
TRACKING_BASE_PATH = os.environ.get("TRACKING_BASE_PATH", "/app/tracking")


class FileItem(BaseModel):
    name: str
    path: str
    is_directory: bool
    size: Optional[int] = None
    modified: Optional[str] = None


class DirectoryContent(BaseModel):
    current_path: str
    parent_path: Optional[str]
    items: List[FileItem]
    total_items: int = 0
    has_more: bool = False


class SearchResult(BaseModel):
    path: str
    name: str
    preview: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/browse")
async def browse_directory(path: str = "", limit: int = 20, show_all: bool = False) -> DirectoryContent:
    """Browse directory contents"""
    # Sanitize path to prevent directory traversal
    safe_path = os.path.normpath(path).lstrip(os.sep).lstrip(".")
    full_path = os.path.join(TRACKING_BASE_PATH, safe_path)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    if not os.path.isdir(full_path):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    # Security check
    if not os.path.abspath(full_path).startswith(os.path.abspath(TRACKING_BASE_PATH)):
        raise HTTPException(status_code=403, detail="Access denied")

    directories = []
    files = []
    try:
        for entry in os.scandir(full_path):
            try:
                stat = entry.stat()
                item = FileItem(
                    name=entry.name,
                    path=os.path.join(safe_path, entry.name) if safe_path else entry.name,
                    is_directory=entry.is_dir(),
                    size=stat.st_size if entry.is_file() else None,
                    modified=str(stat.st_mtime)
                )
                if entry.is_dir():
                    directories.append(item)
                else:
                    files.append(item)
            except Exception as e:
                logger.warning(f"Error reading {entry.name}: {e}")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Sort directories alphabetically, files by most recent first
    directories.sort(key=lambda x: x.name.lower())
    files.sort(key=lambda x: float(x.modified or 0), reverse=True)

    total_files = len(files)
    total_dirs = len(directories)

    # Apply limit only to files (directories are always shown)
    has_more = False
    if not show_all and limit > 0 and len(files) > limit:
        files = files[:limit]
        has_more = True

    items = directories + files

    # Calculate parent path
    parent_path = os.path.dirname(safe_path) if safe_path else None

    return DirectoryContent(
        current_path=safe_path or "/",
        parent_path=parent_path,
        items=items,
        total_items=total_dirs + total_files,
        has_more=has_more
    )


@app.get("/api/file")
async def get_file_content(path: str):
    """Get file content"""
    safe_path = os.path.normpath(path).lstrip(os.sep).lstrip(".")
    full_path = os.path.join(TRACKING_BASE_PATH, safe_path)
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=400, detail="Path is not a file")
    
    # Security check
    if not os.path.abspath(full_path).startswith(os.path.abspath(TRACKING_BASE_PATH)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"path": safe_path, "content": content, "size": os.path.getsize(full_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")


@app.get("/api/download")
async def download_file(path: str):
    """Download file"""
    safe_path = os.path.normpath(path).lstrip(os.sep).lstrip(".")
    full_path = os.path.join(TRACKING_BASE_PATH, safe_path)
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=400, detail="Path is not a file")
    
    # Security check
    if not os.path.abspath(full_path).startswith(os.path.abspath(TRACKING_BASE_PATH)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return FileResponse(full_path, filename=os.path.basename(full_path))


@app.get("/api/search")
async def search_files(query: str, max_results: int = 50) -> List[SearchResult]:
    """Search for files containing query in filename or content"""
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    results = []
    query_lower = query.lower()
    
    for root, dirs, files in os.walk(TRACKING_BASE_PATH):
        for filename in files:
            if len(results) >= max_results:
                break
                
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, TRACKING_BASE_PATH)
            
            # Search in filename
            if query_lower in filename.lower():
                preview = None
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(500)
                        preview = content[:200] + "..." if len(content) > 200 else content
                except:
                    pass
                
                results.append(SearchResult(
                    path=rel_path,
                    name=filename,
                    preview=preview
                ))
                continue
            
            # Search in content for .txt files
            if filename.endswith(".txt"):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                        if query_lower in content.lower():
                            # Find context around match
                            idx = content.lower().find(query_lower)
                            start = max(0, idx - 50)
                            end = min(len(content), idx + len(query) + 100)
                            preview = "..." + content[start:end] + "..."
                            
                            results.append(SearchResult(
                                path=rel_path,
                                name=filename,
                                preview=preview
                            ))
                except:
                    pass
        
        if len(results) >= max_results:
            break
    
    return results


@app.get("/api/download-by-date")
async def download_files_by_date(
    target_date: str = Query(..., description="Date au format YYYY-MM-DD"),
):
    """Download all tracking files modified on a given date as a ZIP archive"""
    try:
        parsed_date = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide. Utilisez YYYY-MM-DD")

    matched_files = []
    for root, dirs, files in os.walk(TRACKING_BASE_PATH):
        for filename in files:
            full_path = os.path.join(root, filename)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(full_path)).date()
                if mtime == parsed_date:
                    rel_path = os.path.relpath(full_path, TRACKING_BASE_PATH)
                    matched_files.append((full_path, rel_path))
            except Exception as e:
                logger.warning(f"Error reading mtime for {full_path}: {e}")

    if not matched_files:
        raise HTTPException(
            status_code=404,
            detail=f"Aucun fichier trouvé pour la date {target_date}"
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for full_path, rel_path in matched_files:
            zf.write(full_path, rel_path)
    zip_buffer.seek(0)

    filename = f"tracking_{target_date}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class OldFileItem(BaseModel):
    path: str
    name: str
    modified: str  # ISO date
    size: int


class ServiceBucket(BaseModel):
    service: str
    count: int
    total_size: int
    files: List[OldFileItem]


class OldFilesResponse(BaseModel):
    threshold_date: str  # ISO date
    total_count: int
    total_size: int
    by_service: List[ServiceBucket]


class DeleteFilesRequest(BaseModel):
    paths: List[str]


class DeleteFilesResponse(BaseModel):
    deleted: List[str]
    errors: List[Dict[str, str]]


def _infer_service_from_relpath(rel_path: str) -> str:
    """
    Déduit le nom du service depuis le chemin relatif.
    Les volumes sont montés sous /app/tracking/<service>/..., donc le 1er segment = service.
    """
    parts = rel_path.replace("\\", "/").split("/")
    return parts[0] if parts and parts[0] else "inconnu"


@app.get("/api/old-files", response_model=OldFilesResponse)
async def list_old_files(months: int = Query(3, ge=1, le=24, description="Âge minimum en mois")):
    """
    Liste les fichiers tracking plus vieux que N mois, groupés par service.
    Le service est déduit du 1er segment du chemin (ex: /app/tracking/prix-traitement/... → prix-traitement).
    """
    threshold = datetime.now() - timedelta(days=months * 30)

    buckets: Dict[str, List[OldFileItem]] = {}

    for root, _dirs, files in os.walk(TRACKING_BASE_PATH):
        for filename in files:
            full_path = os.path.join(root, filename)
            try:
                stat = os.stat(full_path)
                mtime = datetime.fromtimestamp(stat.st_mtime)
                if mtime > threshold:
                    continue
                rel_path = os.path.relpath(full_path, TRACKING_BASE_PATH)
                service = _infer_service_from_relpath(rel_path)
                buckets.setdefault(service, []).append(OldFileItem(
                    path=rel_path.replace("\\", "/"),
                    name=filename,
                    modified=mtime.isoformat(timespec="seconds"),
                    size=stat.st_size,
                ))
            except Exception as e:
                logger.warning(f"Erreur stat {full_path}: {e}")

    by_service: List[ServiceBucket] = []
    total_count = 0
    total_size = 0
    for service in sorted(buckets.keys()):
        items = buckets[service]
        items.sort(key=lambda x: x.modified)
        size_sum = sum(x.size for x in items)
        by_service.append(ServiceBucket(
            service=service,
            count=len(items),
            total_size=size_sum,
            files=items,
        ))
        total_count += len(items)
        total_size += size_sum

    return OldFilesResponse(
        threshold_date=threshold.date().isoformat(),
        total_count=total_count,
        total_size=total_size,
        by_service=by_service,
    )


@app.post("/api/delete-files", response_model=DeleteFilesResponse)
async def delete_files(req: DeleteFilesRequest):
    """Supprime une liste de fichiers tracking (paths relatifs à TRACKING_BASE_PATH)."""
    deleted: List[str] = []
    errors: List[Dict[str, str]] = []

    for raw_path in req.paths:
        safe_path = os.path.normpath(raw_path).lstrip(os.sep).lstrip(".")
        full_path = os.path.join(TRACKING_BASE_PATH, safe_path)

        # Security check
        if not os.path.abspath(full_path).startswith(os.path.abspath(TRACKING_BASE_PATH)):
            errors.append({"path": raw_path, "error": "Access denied"})
            continue

        if not os.path.exists(full_path):
            errors.append({"path": raw_path, "error": "File not found"})
            continue

        if not os.path.isfile(full_path):
            errors.append({"path": raw_path, "error": "Not a file"})
            continue

        try:
            os.remove(full_path)
            deleted.append(safe_path.replace("\\", "/"))
        except Exception as e:
            errors.append({"path": raw_path, "error": str(e)})

    return DeleteFilesResponse(deleted=deleted, errors=errors)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8590)
