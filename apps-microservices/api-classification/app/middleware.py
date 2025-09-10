"""
Middleware pour la gestion des erreurs et la logging
"""
import time
import uuid
import logging
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .exceptions import ClassificationAPIException

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware pour la gestion globale des erreurs"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Génération d'un ID de requête unique
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        start_time = time.time()
        
        # Log de la requête entrante
        logger.info(f"[{request_id}] {request.method} {request.url}")
        
        try:
            response = await call_next(request)
            
            # Log de la réponse
            process_time = time.time() - start_time
            logger.info(f"[{request_id}] Response: {response.status_code} - {process_time:.3f}s")
            
            # Ajout de headers utiles
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(round(process_time, 3))
            
            return response
            
        except ClassificationAPIException as e:
            process_time = time.time() - start_time
            logger.error(f"[{request_id}] Classification error: {e.error_code} - {e.message}")
            
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": e.error_code,
                        "message": e.message,
                        "details": e.details,
                        "request_id": request_id,
                        "timestamp": time.time()
                    }
                },
                headers={"X-Request-ID": request_id}
            )
            
        except ValueError as e:
            process_time = time.time() - start_time
            logger.error(f"[{request_id}] Validation error: {str(e)}")
            
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"Erreur de validation: {str(e)}",
                        "details": {},
                        "request_id": request_id,
                        "timestamp": time.time()
                    }
                },
                headers={"X-Request-ID": request_id}
            )
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.exception(f"[{request_id}] Unexpected error: {str(e)}")
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "Une erreur interne est survenue",
                        "details": {"error_type": type(e).__name__},
                        "request_id": request_id,
                        "timestamp": time.time()
                    }
                },
                headers={"X-Request-ID": request_id}
            )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware pour le logging détaillé des requêtes"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Log des headers importants (sans les données sensibles)
        headers_to_log = {
            k: v for k, v in request.headers.items() 
            if k.lower() not in ['authorization', 'cookie', 'x-api-key']
        }
        
        logger.debug(f"Request headers: {headers_to_log}")
        
        # Log du body pour les requêtes POST/PUT (limité en taille)
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if len(body) > 0:
                    body_preview = body[:500] if len(body) > 500 else body
                    logger.debug(f"Request body preview: {body_preview}")
            except Exception as e:
                logger.warning(f"Could not log request body: {e}")
        
        return await call_next(request)