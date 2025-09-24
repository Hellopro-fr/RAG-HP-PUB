from fastapi import APIRouter, HTTPException, Request
from app.schemas.optimize.optimize import OptimRequest, OptimResponse, BatchOptimRequest, BatchOptimResponse
from app.core.optimize.Optimize import ProductOptimizer
from app.core.optimize.Qwen3_14B_AWQ_par_lots import ProductTitleOptimizerBatch
from app.core.optimize.traitement_donnees import TraitementDonnees
from typing import List, Dict, Any
import time
import os
import threading
import traceback
import asyncio
import json
import logging

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Import des clients gRPC de notre architecture
from common_utils.grpc_clients import (
    llm_client,
)

from common_utils.grpc_clients.schemas.chat import ChatRequest


# On crée un verrou global pour protéger l'initialisation du service
service_initialization_lock = threading.Lock()
qwen_service_instance: ProductTitleOptimizerBatch | None = None

def get_qwen_optimize_service() -> ProductTitleOptimizerBatch:
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
            print("--- LAZY LOADING: Initialisation du ProductTitleOptimizerBatch (chargement du modèle)... ---")
            qwen_service_instance = ProductTitleOptimizerBatch()
            print("--- LAZY LOADING: Service initialisé et prêt. ---")
    return qwen_service_instance

@router.post("/openai", response_model=OptimResponse)
def optimize(request: OptimRequest):
    try:
        optimizing_service = ProductOptimizer(OPENAI_API_KEY)
        optimize = optimizing_service.optimize_product(request.dict())

        print(optimize)

        return {"data": [optimize]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/qwen", response_model=OptimResponse)
def optimizeQwen(request: Request, payload: OptimRequest):
    try:

        optimizing_service = get_qwen_optimize_service()
        response_optimizeQwen = optimizing_service.optimize_product(payload.dict())

        print(response_optimizeQwen)

        return {"data": [response_optimizeQwen]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/qwen/batch", response_model=BatchOptimResponse)
def optimize_qwen_batch(request: Request, payload: BatchOptimRequest):
    try:
        start_time = time.time()
        
        print(f"<<<<<<<<<<< >>>>>>>>>>>")
        print(f"Reception de {len(payload.products)} produits")
        
        optimizing_service = get_qwen_optimize_service()
        
        # Conversion des données Pydantic en dictionnaires
        products_data = [product.dict() for product in payload.products]
        
        # Traitement par lots
        batch_results = optimizing_service.optimize_products_batch(products_data)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"Fin traitement en {processing_time:.2f} secondes")
        
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
        error_msg = f"Erreur lors du traitement par lots: {type(e).__name__}: {str(e)}"
        debug_msg = f"{error_msg}\nTraceback:\n{traceback.format_exc()}"
        response_error = {
            "ERROR": error_msg
        }
        print(debug_msg)
        return response_error

@router.post("/qwen/v2", response_model=OptimResponse)
async def optimizeQwen(payload: OptimRequest):
    try:

        instancetraitement = TraitementDonnees()
        prompt = instancetraitement.generate_prompt(payload.dict())
 
        chat_request = ChatRequest(prompt=prompt)

        response = await llm_client.get_llm_chat_response(chat_request)

        try:
            parsed_response = json.loads(response)
        except json.JSONDecodeError:
            print("erreur de parsing")

        print(response)

        return {"data": [response]}

    except Exception as e:
        error_msg = f"Erreur lors du traitement du produit: {type(e).__name__}: {str(e)}"
        debug_msg = f"{error_msg}\nTraceback:\n{traceback.format_exc()}"
        response_error = {
            "ERROR": error_msg
        }
        print(debug_msg)
        return response_error