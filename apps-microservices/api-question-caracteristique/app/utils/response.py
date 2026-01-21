from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional

def success_response(data: Any, message: str = "Success") -> JSONResponse:
    """Crée une réponse de succès standardisée"""
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": message,
            "data": data
        }
    )

def error_response(
    error: str, 
    status_code: int = 400, 
    details: Optional[Dict] = None
) -> JSONResponse:
    """Crée une réponse d'erreur standardisée"""
    content = {
        "status": "error",
        "error": error
    }
    
    if details:
        content["details"] = details
    
    return JSONResponse(
        status_code=status_code,
        content=content
    )

