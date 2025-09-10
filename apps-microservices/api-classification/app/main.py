# app/main.py
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

from .api.routes import router
from .config import settings
from .middleware import ErrorHandlingMiddleware, RequestLoggingMiddleware
from .exceptions import ClassificationAPIException

# Configuration avancée du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Ajout d'un filtre pour les logs avec request_id
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        # Récupère le request_id depuis le contexte si disponible
        request_id = getattr(record, 'request_id', 'no-request-id')
        record.request_id = request_id
        return True

# Application du filtre à tous les handlers
for handler in logging.root.handlers:
    handler.addFilter(RequestIdFilter())

logger = logging.getLogger(__name__)

# Variable globale pour tracker l'uptime
app_start_time = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestionnaire de cycle de vie de l'application avec vérifications au démarrage.
    Cette fonction est appelée au démarrage et à l'arrêt de l'application.
    """
    # === DÉMARRAGE ===
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE DE L'API DE CLASSIFICATION DE PRODUITS")
    logger.info("=" * 60)
    
    try:
        # Test de la configuration
        logger.info("🔧 Vérification de la configuration...")
        
        # Import dynamique pour éviter les erreurs au démarrage si mal configuré
        try:
            from .services.classifier import ProductClassifier
            classifier = ProductClassifier(settings.get_config_dict())
            
            available_llms = classifier.get_available_llms()
            milvus_connected = classifier.is_milvus_connected()
            
            logger.info(f"✅ LLMs disponibles: {available_llms}")
            logger.info(f"✅ Milvus connecté: {milvus_connected}")
            
            if not available_llms:
                logger.warning("⚠️  ATTENTION: Aucun LLM disponible!")
                logger.warning("   Vérifiez vos clés API OpenAI/DeepSeek")
            
            if not milvus_connected:
                logger.warning("⚠️  ATTENTION: Milvus non connecté!")
                logger.warning("   Les descriptions de catégories ne seront pas disponibles")
            
        except Exception as e:
            logger.error(f"❌ ERREUR lors de l'initialisation du classifier: {e}")
            # On ne fait pas d'exit ici, l'API peut démarrer sans classifier
            # Les erreurs seront gérées au niveau des endpoints
        
        # Vérification des URLs des APIs externes
        if settings.search_api_url:
            logger.info(f"🔗 API de recherche configurée: {settings.search_api_url}")
        else:
            logger.warning("⚠️  API de recherche non configurée")
        
        if settings.external_product_api_url:
            logger.info(f"🔗 API produits configurée: {settings.external_product_api_url}")
        else:
            logger.warning("⚠️  API produits non configurée")
        
        # Informations sur l'environnement
        logger.info(f"🌍 Environnement: {'DEBUG' if settings.api_debug else 'PRODUCTION'}")
        logger.info(f"🌐 Serveur: {settings.api_host}:{settings.api_port}")
        logger.info(f"📝 Niveau de log: {logging.getLevelName(logger.getEffectiveLevel())}")
        
        logger.info("=" * 60)
        logger.info("✅ API PRÊTE À RECEVOIR DES REQUÊTES")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ ERREUR CRITIQUE au démarrage: {e}")
        logger.error("L'API va démarrer mais risque de ne pas fonctionner correctement")
        # On ne raise pas l'exception pour permettre le démarrage
    
    yield  # L'application fonctionne ici
    
    # === ARRÊT ===
    logger.info("=" * 60)
    logger.info("🛑 ARRÊT DE L'API DE CLASSIFICATION")
    logger.info("=" * 60)
    uptime = time.time() - app_start_time
    logger.info(f"📊 Uptime total: {uptime:.2f} secondes ({uptime/3600:.2f} heures)")
    logger.info("👋 Arrêt terminé")

def custom_openapi():
    """Génère une documentation OpenAPI personnalisée"""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="API de Classification de Produits",
        version="1.0.0",
        description="""
        ## 🚀 API de Classification Automatique de Produits
        
        Cette API utilise l'intelligence artificielle pour classifier automatiquement des produits 
        dans les bonnes catégories en se basant sur leur titre et description.
        
        ### ✨ Fonctionnalités principales
        
        - **Classification simple** : Classifier un produit unique
        - **Classification par lots** : Traiter jusqu'à 100 produits simultanément  
        - **LLMs multiples** : Support OpenAI et DeepSeek
        - **Amélioration automatique** : Optimisation des descriptions avant classification
        - **Métriques détaillées** : Temps de traitement et scores de confiance
        
        ### 🔧 Configuration requise
        
        - Au moins une clé API LLM (OpenAI ou DeepSeek)
        - URL de l'API de recherche configurée
        - URL de l'API produits configurée (optionnel)
        - Base vectorielle Milvus/Zilliz (optionnel)
        
        ### 📊 Limites
        
        - Maximum 100 produits par batch
        - Timeout de 30 secondes par requête
        - Limite de longueur: 10000 caractères pour les descriptions
        """,
        routes=app.routes,
    )
    
    # Ajout d'informations supplémentaires
    openapi_schema["info"]["contact"] = {
        "name": "Support API",
        "email": "support@yourcompany.com"
    }
    
    openapi_schema["info"]["license"] = {
        "name": "Propriétaire"
    }
    
    # Tags pour organiser la documentation
    openapi_schema["tags"] = [
        {
            "name": "Classification",
            "description": "Endpoints de classification de produits"
        },
        {
            "name": "Santé",
            "description": "Endpoints de santé et monitoring"
        },
        {
            "name": "Configuration", 
            "description": "Endpoints de configuration et informations"
        },
        {
            "name": "Utilitaires",
            "description": "Endpoints utilitaires et helpers"
        }
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Création de l'application FastAPI
app = FastAPI(
    title="API de Classification de Produits",
    description="API robuste pour classifier des produits en catégories en utilisant l'IA",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Application de la documentation personnalisée
app.openapi = custom_openapi

# === MIDDLEWARE ===
# L'ordre des middlewares est important ! (LIFO - Last In, First Out)

# 1. Middleware de gestion d'erreurs (en dernier pour capturer tout)
app.add_middleware(ErrorHandlingMiddleware)

# 2. Middleware de logging des requêtes
app.add_middleware(RequestLoggingMiddleware)

# 3. Configuration CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.api_debug else [
        "https://yourcompany.com",
        "https://admin.yourcompany.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"]
)

# === ROUTES ===
# Inclusion des routes avec préfixe
app.include_router(router, prefix="/api/v1", tags=["API v1"])

# === ENDPOINTS GLOBAUX ===

@app.get("/", tags=["Informations"])
async def root():
    """
    Endpoint racine avec informations générales sur l'API.
    Point d'entrée principal pour découvrir l'API.
    """
    uptime_seconds = time.time() - app_start_time
    
    return {
        "message": "API de Classification de Produits",
        "version": "1.0.0",
        "status": "operational",
        "uptime_seconds": round(uptime_seconds, 2),
        "timestamp": time.time(),
        
        # Liens utiles
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi_schema": "/openapi.json"
        },
        
        # Endpoints principaux
        "endpoints": {
            "health_check": "GET /api/v1/health",
            "classify_single": "POST /api/v1/classify", 
            "classify_batch": "POST /api/v1/classify/batch",
            "available_llms": "GET /api/v1/llms",
            "api_stats": "GET /api/v1/stats",
            "configuration": "GET /api/v1/config"
        },
        
        # Informations techniques
        "technical_info": {
            "supported_llms": ["OpenAI", "DeepSeek"],
            "max_batch_size": 100,
            "timeout_seconds": 30,
            "supported_formats": ["JSON"],
            "cors_enabled": True
        }
    }

@app.get("/favicon.ico")
async def favicon():
    """Favicon pour éviter les erreurs 404 dans les navigateurs"""
    return JSONResponse(
        status_code=204,
        content=None
    )

# === HANDLERS D'ERREURS GLOBAUX ===
# Ces handlers servent de backup si le middleware ne capture pas tout

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Handler pour les erreurs 404 personnalisé"""
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "NOT_FOUND",
                "message": "Endpoint non trouvé",
                "path": str(request.url.path),
                "method": request.method,
                "available_endpoints": {
                    "docs": "/docs",
                    "health": "/api/v1/health",
                    "classify": "/api/v1/classify"
                },
                "timestamp": time.time()
            }
        }
    )

@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception):
    """Handler global pour les erreurs 500 non capturées"""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.exception(f"[{request_id}] Erreur serveur non gérée: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Une erreur interne est survenue",
                "request_id": request_id,
                "timestamp": time.time()
            }
        }
    )

@app.exception_handler(ClassificationAPIException)
async def classification_exception_handler(request: Request, exc: ClassificationAPIException):
    """Handler pour les exceptions métier de classification"""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(f"[{request_id}] Exception de classification: {exc.error_code} - {exc.message}")
    
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
                "timestamp": time.time()
            }
        }
    )

# === EVENTS ===

@app.on_event("startup")
async def startup_event():
    """Événement de démarrage (deprecated mais gardé pour compatibilité)"""
    logger.info("🔄 Event startup déclenché (utilise maintenant lifespan)")

@app.on_event("shutdown") 
async def shutdown_event():
    """Événement d'arrêt (deprecated mais gardé pour compatibilité)"""
    logger.info("🔄 Event shutdown déclenché (utilise maintenant lifespan)")

# === POINT D'ENTRÉE ===

if __name__ == "__main__":
    import uvicorn
    
    # Configuration pour le développement
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["default"],
        },
    }
    
    logger.info(f"🚀 Démarrage du serveur en mode {'DEBUG' if settings.api_debug else 'PRODUCTION'}")
    logger.info(f"🌐 Adresse: http://{settings.api_host}:{settings.api_port}")
    logger.info(f"📚 Documentation: http://{settings.api_host}:{settings.api_port}/docs")
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level="info",
        log_config=log_config,
        access_log=True,
        use_colors=True
    )