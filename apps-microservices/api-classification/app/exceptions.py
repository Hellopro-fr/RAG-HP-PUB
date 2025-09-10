"""
Exceptions personnalisées pour l'API de classification
"""
from typing import Any, Dict, Optional


class ClassificationAPIException(Exception):
    """Exception de base pour l'API de classification"""
    def __init__(self, message: str, error_code: str = "CLASSIFICATION_ERROR", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class LLMConnectionError(ClassificationAPIException):
    """Erreur de connexion aux services LLM"""
    def __init__(self, provider: str, message: str = "Erreur de connexion au service LLM"):
        super().__init__(
            message=f"{message}: {provider}",
            error_code="LLM_CONNECTION_ERROR",
            details={"provider": provider}
        )


class MilvusConnectionError(ClassificationAPIException):
    """Erreur de connexion à Milvus/Zilliz"""
    def __init__(self, message: str = "Erreur de connexion à Milvus"):
        super().__init__(
            message=message,
            error_code="MILVUS_CONNECTION_ERROR"
        )


class SearchAPIError(ClassificationAPIException):
    """Erreur lors de l'appel à l'API de recherche"""
    def __init__(self, message: str = "Erreur lors de la recherche de produits"):
        super().__init__(
            message=message,
            error_code="SEARCH_API_ERROR"
        )


class ProductAPIError(ClassificationAPIException):
    """Erreur lors de l'appel à l'API des produits"""
    def __init__(self, message: str = "Erreur lors de la récupération des détails produits"):
        super().__init__(
            message=message,
            error_code="PRODUCT_API_ERROR"
        )


class ValidationError(ClassificationAPIException):
    """Erreur de validation des données"""
    def __init__(self, field: str, message: str):
        super().__init__(
            message=f"Erreur de validation pour '{field}': {message}",
            error_code="VALIDATION_ERROR",
            details={"field": field}
        )


class ConfigurationError(ClassificationAPIException):
    """Erreur de configuration"""
    def __init__(self, parameter: str, message: str = "Paramètre de configuration manquant ou invalide"):
        super().__init__(
            message=f"{message}: {parameter}",
            error_code="CONFIGURATION_ERROR",
            details={"parameter": parameter}
        )


class ModelNotAvailableError(ClassificationAPIException):
    """Erreur quand un modèle demandé n'est pas disponible"""
    def __init__(self, model_name: str):
        super().__init__(
            message=f"Modèle non disponible: {model_name}",
            error_code="MODEL_NOT_AVAILABLE",
            details={"model_name": model_name}
        )


class TimeoutError(ClassificationAPIException):
    """Erreur de timeout"""
    def __init__(self, operation: str, timeout_seconds: int):
        super().__init__(
            message=f"Timeout lors de l'opération '{operation}' après {timeout_seconds} secondes",
            error_code="TIMEOUT_ERROR",
            details={"operation": operation, "timeout": timeout_seconds}
        )


class RateLimitError(ClassificationAPIException):
    """Erreur de limite de débit"""
    def __init__(self, service: str, retry_after: Optional[int] = None):
        super().__init__(
            message=f"Limite de débit atteinte pour le service: {service}",
            error_code="RATE_LIMIT_ERROR",
            details={"service": service, "retry_after": retry_after}
        )