"""
Handlers spécialisés pour différents types d'erreurs
"""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException
from openai import OpenAIError, RateLimitError as OpenAIRateLimit
from pymilvus.exceptions import MilvusException
import requests

from .exceptions import *

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Gestionnaire centralisé des erreurs"""
    
    @staticmethod
    def handle_requests_error(error: requests.RequestException, service_name: str) -> ClassificationAPIException:
        """Gère les erreurs de requêtes HTTP"""
        if isinstance(error, requests.Timeout):
            return TimeoutError(f"Appel à {service_name}", 30)
        elif isinstance(error, requests.ConnectionError):
            return SearchAPIError(f"Impossible de se connecter à {service_name}")
        elif hasattr(error, 'response') and error.response is not None:
            if error.response.status_code == 429:
                retry_after = error.response.headers.get('Retry-After')
                return RateLimitError(service_name, int(retry_after) if retry_after else None)
            elif error.response.status_code >= 500:
                return SearchAPIError(f"Erreur serveur {service_name}: {error.response.status_code}")
            else:
                return SearchAPIError(f"Erreur {service_name}: {error.response.status_code}")
        else:
            return SearchAPIError(f"Erreur inconnue avec {service_name}: {str(error)}")
    
    @staticmethod
    def handle_openai_error(error: Exception, provider: str = "OpenAI") -> ClassificationAPIException:
        """Gère les erreurs spécifiques à OpenAI/DeepSeek"""
        if isinstance(error, OpenAIRateLimit):
            return RateLimitError(provider, getattr(error, 'retry_after', None))
        elif "authentication" in str(error).lower():
            return LLMConnectionError(provider, "Erreur d'authentification")
        elif "timeout" in str(error).lower():
            return TimeoutError(f"Requête {provider}", 30)
        elif "connection" in str(error).lower():
            return LLMConnectionError(provider, "Erreur de connexion réseau")
        else:
            return LLMConnectionError(provider, f"Erreur {provider}: {str(error)}")
    
    @staticmethod
    def handle_milvus_error(error: Exception) -> ClassificationAPIException:
        """Gère les erreurs Milvus/Zilliz"""
        error_str = str(error).lower()
        if "connection" in error_str or "timeout" in error_str:
            return MilvusConnectionError("Impossible de se connecter à Milvus")
        elif "authentication" in error_str or "permission" in error_str:
            return MilvusConnectionError("Erreur d'authentification Milvus")
        elif "collection" in error_str and "not found" in error_str:
            return MilvusConnectionError("Collection Milvus introuvable")
        else:
            return MilvusConnectionError(f"Erreur Milvus: {str(error)}")
    
    @staticmethod
    def handle_validation_error(error: Exception, field: str = "unknown") -> ValidationError:
        """Gère les erreurs de validation"""
        return ValidationError(field, str(error))