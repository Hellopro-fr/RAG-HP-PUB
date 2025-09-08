from fastapi import APIRouter, HTTPException, Request
from app.schemas.optimize.optimize import OptimRequest, OptimResponse, BatchOptimRequest, BatchOptimResponse
from app.core.optimize.Optimize import ProductOptimizer
# from app.core.optimize.Qwen3_14B_AWQ_titre import ProductTitleOptimizer
from app.core.optimize.Qwen3_14B_AWQ_par_lots import ProductTitleOptimizer
from typing import List, Dict, Any
import time
import os
import threading

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# On crée un verrou global pour protéger l'initialisation du service
service_initialization_lock = threading.Lock()
qwen_service_instance: ProductTitleOptimizer | None = None

def get_qwen_optimize_service() -> ProductTitleOptimizer:
    """
    Fonction "thread-safe" qui charge le service (et le modèle LLM) de manière différée.
    Le verrou garantit qu'un seul thread peut initialiser le service à la fois.
    """
    global qwen_service_instance
    # Si l'instance existe déjà, on la retourne directement sans attendre
    if qwen_service_instance:
        return qwen_service_instance

    # Le premier thread qui arrive acquiert le verrou. Les autres attendent ici.
    with service_initialization_lock:
        # On revérifie si l'instance n'a pas été créée par un autre thread
        # pendant qu'on attendait le verrou.
        if qwen_service_instance is None:
            print("--- LAZY LOADING: Initialisation du ProductTitleOptimizer (chargement du modèle)... ---")
            qwen_service_instance = ProductTitleOptimizer()
            print("--- LAZY LOADING: Service initialisé et prêt. ---")
    return qwen_service_instance

@router.post("/openai", response_model=OptimResponse)
def optimize(request: OptimRequest):
    try:
        optimizing_service = ProductOptimizer(OPENAI_API_KEY)
        optimize = optimizing_service.optimize_product(request.dict())

        print(optimize)

        # ⚠️ S'assurer que "data" est bien retourné
        return {"data": [optimize]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/qwen", response_model=OptimResponse)
def optimizeQwen(request: Request, payload: OptimRequest):
    try:
        # tokenizer = request.app.state.qwen_tokenizer
        # model = request.app.state.qwen_model

        optimizing_service = get_qwen_optimize_service()
        #optimizeQwen = optimizing_service.optimize_product(request.dict())
        response_optimizeQwen = optimizing_service.optimize_product(payload.dict())

        print(response_optimizeQwen)

        # ⚠️ S'assurer que "data" est bien retourné
        return {"data": [response_optimizeQwen]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/qwen/batch", response_model=BatchOptimResponse)
def optimize_qwen_batch(request: Request, payload: BatchOptimRequest):
    """
    Endpoint pour optimiser plusieurs produits par lots de 1000.
    """
    try:
        start_time = time.time()
        
        print(f"Début du traitement par lots de {len(payload.products)} produits")
        
        optimizing_service = get_qwen_optimize_service()
        
        # Conversion des données Pydantic en dictionnaires
        products_data = [product.dict() for product in payload.products]
        
        # Traitement par lots
        batch_results = optimizing_service.optimize_products_batch(products_data)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"Traitement par lots terminé en {processing_time:.2f} secondes")
        
        # Calcul des statistiques
        success_count = sum(1 for result in batch_results if "success" in result)
        error_count = len(batch_results) - success_count
        
        response = {
            "data": batch_results,
            "metadata": {
                "total_products": len(batch_results),
                "successful_optimizations": success_count,
                "failed_optimizations": error_count,
                "processing_time_seconds": round(processing_time, 2),
                "batch_size": optimizing_service.batch_size
            }
        }
        
        return response
        
    except Exception as e:
        error_msg = f"Erreur lors du traitement par lots: {str(e)}"
        response_error = {
            "ERROR": error_msg
        }
        print(response_error)
        return response_error
