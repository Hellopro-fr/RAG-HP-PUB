# app/api/routes.py
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from typing import List, Dict, Any
import logging
import time
import json

from ..models import (
    ClassificationRequest, ClassificationResponse,
    BatchClassificationRequest, BatchClassificationResponse,
    HealthResponse, BatchSummary, ProductInput
)
from ..services.classifier import ProductClassifier
from ..config import settings
from ..exceptions import ClassificationAPIException, ValidationError

logger = logging.getLogger(__name__)

# Initialisation du classifier (singleton)
_classifier_instance = None

def get_classifier() -> ProductClassifier:
    """Dependency pour obtenir l'instance du classifier"""
    global _classifier_instance
    if _classifier_instance is None:
        try:
            _classifier_instance = ProductClassifier(settings.get_config_dict())
            logger.info("Classifier initialisé avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du classifier: {e}")
            raise HTTPException(
                status_code=503,
                detail="Service temporairement indisponible - Erreur d'initialisation"
            )
    return _classifier_instance

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def health_check(classifier: ProductClassifier = Depends(get_classifier)):
    """Endpoint de santé de l'API"""
    try:
        return HealthResponse(
            status="healthy",
            version="1.0.0",
            available_llms=classifier.get_available_llms(),
            milvus_connected=classifier.is_milvus_connected()
        )
    except Exception as e:
        logger.error(f"Erreur lors du health check: {e}")
        return HealthResponse(
            status="error",
            version="1.0.0",
            available_llms=[],
            milvus_connected=False
        )

@router.get("/health/detailed")
async def detailed_health_check(classifier: ProductClassifier = Depends(get_classifier)):
    """Health check détaillé avec vérifications de tous les services"""
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0",
        "services": {},
        "configuration": {}
    }
    
    # Test des LLMs
    try:
        available_llms = classifier.get_available_llms()
        health_status["services"]["llm"] = {
            "status": "healthy" if available_llms else "warning",
            "available_providers": available_llms,
            "details": "LLM services operational" if available_llms else "No LLM providers available"
        }
    except Exception as e:
        health_status["services"]["llm"] = {
            "status": "error", 
            "error": str(e),
            "available_providers": []
        }
    
    # Test Milvus
    try:
        category_api_connected = classifier.is_category_api_connected()
        health_status["services"]["category_api"] = {
            "status": "healthy" if category_api_connected else "warning",
            "connected": category_api_connected,
            "details": "Category API configured" if category_api_connected else "Category API not configured"
        }
    except Exception as e:
        health_status["services"]["category_api"] = {
            "status": "error", 
            "error": str(e),
            "connected": False
        }

     # Test des APIs externes avec l'API catégories
    try:
        from ..services.search_api import health_check_apis
        external_apis_health = health_check_apis(
            search_api_url=settings.search_api_url,
            external_product_api_url=settings.external_product_api_url,
            external_category_api_url=settings.external_category_api_url  # NOUVEAU
        )
        health_status["services"]["external_apis"] = external_apis_health["apis"]
    except Exception as e:
        health_status["services"]["external_apis"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Configuration check
    config_issues = []
    if not settings.search_api_url:
        config_issues.append("search_api_url not configured")
    if not settings.external_product_api_url:
        config_issues.append("external_product_api_url not configured")
    if not settings.external_category_api_url:
        config_issues.append("external_category_api_url not configured")  # NOUVEAU
    if not settings.openai_api_key and not settings.deepseek_api_key:
        config_issues.append("no LLM API keys configured")
    
    health_status["configuration"] = {
        "status": "healthy" if not config_issues else "warning",
        "issues": config_issues
    }
    
    # Statut global
    service_statuses = [svc["status"] for svc in health_status["services"].values()]
    config_status = health_status["configuration"]["status"]
    
    if "error" in service_statuses or config_status == "error":
        health_status["status"] = "error"
    elif "warning" in service_statuses or config_status == "warning":
        health_status["status"] = "warning"
    
    return health_status

@router.get("/llms")
async def get_available_llms(classifier: ProductClassifier = Depends(get_classifier)):
    """Retourne la liste des LLMs disponibles et leur statut"""
    try:
        available_llms = classifier.get_available_llms()
        milvus_connected = classifier.is_milvus_connected()
        
        return {
            "available_llms": available_llms,
            "milvus_connected": milvus_connected,
            "total_providers": len(available_llms),
            "recommendations": {
                "openai": "OpenAI" in available_llms,
                "deepseek": "DeepSeek" in available_llms
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des LLMs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/classify", response_model=ClassificationResponse)
async def classify_product(
    request: ClassificationRequest, 
    background_tasks: BackgroundTasks,
    classifier: ProductClassifier = Depends(get_classifier)
):
    """Classifie un seul produit"""
    start_time = time.time()
    
    try:
        logger.info(f"Classification demandée pour produit: {request.produit.id_produit}")
        
        # Validation additionnelle
        if not request.produit.nom_produit.strip():
            raise ValidationError("nom_produit", "Le nom du produit ne peut pas être vide")
        
        # Vérifier que le LLM demandé est disponible
        available_llms = classifier.get_available_llms()
        if request.llm_provider.value not in available_llms:
            raise HTTPException(
                status_code=400,
                detail=f"LLM {request.llm_provider.value} non disponible. LLMs disponibles: {available_llms}"
            )
        
        # Classification
        result = classifier.classify_product(
            product=request.produit,
            enhance_content=request.enhance_content,
            llm_provider=request.llm_provider,
            n_similar=request.n_similar,
            m_categories=request.m_categories,
            k_products=request.k_products
        )
        
        # Logging asynchrone des métriques
        processing_time = time.time() - start_time
        background_tasks.add_task(
            log_classification_metrics,
            request.produit.id_produit,
            request.llm_provider.value,
            result.status,
            processing_time
        )
        
        return result
        
    except ClassificationAPIException as e:
        logger.error(f"Erreur de classification: {e.error_code} - {e.message}")
        raise HTTPException(status_code=400, detail={
            "error_code": e.error_code,
            "message": e.message,
            "details": e.details
        })
    except ValidationError as e:
        logger.error(f"Erreur de validation: {e.message}")
        raise HTTPException(status_code=422, detail=e.message)
    except Exception as e:
        logger.exception(f"Erreur inattendue lors de la classification: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.post("/classify/batch", response_model=BatchClassificationResponse)
async def classify_products_batch(
    request: BatchClassificationRequest,
    background_tasks: BackgroundTasks,
    classifier: ProductClassifier = Depends(get_classifier)
):
    """Classifie un lot de produits"""
    start_time = time.time()
    
    try:
        logger.info(f"Classification batch demandée pour {len(request.produits)} produits")
        
        # Validation des paramètres batch
        if len(request.produits) == 0:
            raise ValidationError("produits", "La liste de produits ne peut pas être vide")
        
        if len(request.produits) > 100:  # Limite raisonnable
            raise ValidationError("produits", "Maximum 100 produits par batch")
        
        # Vérifier que le LLM demandé est disponible
        available_llms = classifier.get_available_llms()
        if request.llm_provider.value not in available_llms:
            raise HTTPException(
                status_code=400,
                detail=f"LLM {request.llm_provider.value} non disponible. LLMs disponibles: {available_llms}"
            )
        
        # Classification par lots
        results = classifier.classify_batch(
            products=request.produits,
            enhance_content=request.enhance_content,
            llm_provider=request.llm_provider,
            n_similar=request.n_similar,
            m_categories=request.m_categories,
            k_products=request.k_products
        )
        
        # Calcul des statistiques
        successful_classifications = sum(1 for r in results if r.status == "SUCCESS")
        correct_predictions = sum(
            1 for r in results 
            if r.precision_check and r.precision_check.is_correct
        )
        total_with_expected = sum(1 for r in results if r.precision_check)
        total_time = sum(r.processing_time_seconds or 0 for r in results)
        
        # Calcul des métriques
        success_rate = (successful_classifications / len(results)) * 100 if results else 0
        precision_rate = (correct_predictions / total_with_expected) * 100 if total_with_expected > 0 else None
        avg_time = total_time / len(results) if results else 0
        
        summary = BatchSummary(
            total_products=len(request.produits),
            successful_classifications=successful_classifications,
            success_rate=round(success_rate, 2),
            precision_rate=round(precision_rate, 2) if precision_rate is not None else None,
            average_processing_time=round(avg_time, 2),
            llm_used=request.llm_provider.value
        )
        
        # Logging asynchrone
        batch_processing_time = time.time() - start_time
        background_tasks.add_task(
            log_batch_metrics,
            len(request.produits),
            request.llm_provider.value,
            successful_classifications,
            batch_processing_time
        )
        
        return BatchClassificationResponse(
            summary=summary,
            detailed_results=results
        )
        
    except ClassificationAPIException as e:
        logger.error(f"Erreur de classification batch: {e.error_code} - {e.message}")
        raise HTTPException(status_code=400, detail={
            "error_code": e.error_code,
            "message": e.message,
            "details": e.details
        })
    except ValidationError as e:
        logger.error(f"Erreur de validation batch: {e.message}")
        raise HTTPException(status_code=422, detail=e.message)
    except Exception as e:
        logger.exception(f"Erreur inattendue lors de la classification batch: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.post("/classify/batch/parse")
async def parse_batch_data(request: Dict[str, str]):
    """Endpoint utilitaire pour parser et valider des données batch avant classification"""
    try:
        batch_text = request.get("batch_text", "")
        if not batch_text:
            raise ValidationError("batch_text", "Le texte batch ne peut pas être vide")
        
        # Utiliser le parser du classifier
        classifier = get_classifier()
        products_data = classifier._parse_batch_input(batch_text)
        
        # Convertir en objets ProductInput pour validation
        valid_products = []
        validation_errors = []
        
        for i, product_data in enumerate(products_data, 1):
            try:
                product = ProductInput(**product_data)
                valid_products.append(product)
            except Exception as e:
                validation_errors.append(f"Produit {i}: {str(e)}")
        
        return {
            "total_parsed": len(products_data),
            "valid_products": len(valid_products),
            "validation_errors": validation_errors,
            "sample_products": valid_products[:3] if valid_products else [],
            "parsing_successful": len(validation_errors) == 0
        }
        
    except Exception as e:
        logger.error(f"Erreur lors du parsing batch: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stats")
async def get_api_stats():
    """Retourne les statistiques d'utilisation de l'API"""
    # Ce serait idéalement connecté à un système de métriques comme Prometheus
    # Pour l'instant, on retourne des stats basiques
    return {
        "api_version": "1.0.0",
        "uptime_seconds": time.time() - start_time if 'start_time' in globals() else 0,
        "endpoints": {
            "classify": "/api/v1/classify",
            "classify_batch": "/api/v1/classify/batch", 
            "health": "/api/v1/health",
            "stats": "/api/v1/stats"
        },
        "limits": {
            "max_batch_size": 100,
            "max_description_length": 10000,
            "max_title_length": 500
        }
    }

@router.get("/config")
async def get_api_config():
    """Retourne la configuration publique de l'API (sans informations sensibles)"""
    return {
        "default_parameters": {
            "n_similar": settings.default_n_similar,
            "m_categories": settings.default_m_categories,
            "k_products": settings.default_k_products
        },
        "available_llm_providers": ["OpenAI", "DeepSeek"],
        "supported_enhancement": True,
        "vector_database": "Milvus/Zilliz",
        "reranker_model": settings.bge_reranker_model
    }

# Fonctions utilitaires pour le logging asynchrone
async def log_classification_metrics(product_id: str, llm_provider: str, status: str, processing_time: float):
    """Log les métriques de classification de manière asynchrone"""
    logger.info(f"METRICS: product_id={product_id}, llm={llm_provider}, status={status}, time={processing_time:.3f}s")

async def log_batch_metrics(batch_size: int, llm_provider: str, successful: int, processing_time: float):
    """Log les métriques de batch de manière asynchrone"""
    success_rate = (successful / batch_size) * 100
    logger.info(f"BATCH_METRICS: size={batch_size}, llm={llm_provider}, success_rate={success_rate:.1f}%, time={processing_time:.3f}s")

# Middleware pour ajouter des headers de cache si nécessaire
@router.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Ajoute des headers de cache appropriés"""
    response = await call_next(request)
    
    # Pas de cache pour les endpoints de classification
    if request.url.path.endswith(("/classify", "/classify/batch")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    
    # Cache court pour les endpoints de configuration
    elif request.url.path.endswith(("/config", "/llms")):
        response.headers["Cache-Control"] = "public, max-age=300"  # 5 minutes
    
    return response