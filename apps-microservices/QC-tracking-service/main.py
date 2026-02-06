"""
QC Tracking Service - Interface de visualisation des fichiers tracking
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
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
async def browse_directory(path: str = "") -> DirectoryContent:
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
    
    items = []
    try:
        for entry in os.scandir(full_path):
            try:
                stat = entry.stat()
                items.append(FileItem(
                    name=entry.name,
                    path=os.path.join(safe_path, entry.name) if safe_path else entry.name,
                    is_directory=entry.is_dir(),
                    size=stat.st_size if entry.is_file() else None,
                    modified=str(stat.st_mtime)
                ))
            except Exception as e:
                logger.warning(f"Error reading {entry.name}: {e}")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Sort: directories first, then by name
    items.sort(key=lambda x: (not x.is_directory, x.name.lower()))
    
    # Calculate parent path
    parent_path = os.path.dirname(safe_path) if safe_path else None
    
    return DirectoryContent(
        current_path=safe_path or "/",
        parent_path=parent_path,
        items=items
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8590)
