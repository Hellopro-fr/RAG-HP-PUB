from fastapi import APIRouter, HTTPException, Request
from app.schemas.optimize.optimize import OptimRequest, OptimResponse
from app.core.optimize.Optimize import ProductOptimizer
# from app.core.optimize.Qwen3_14B_Q4 import ProductOptimizerQwen
from app.core.optimize.Qwen3_14B_AWQ import ProductOptimizerQwen

import os
import threading

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# On crée un verrou global pour protéger l'initialisation du service
service_initialization_lock = threading.Lock()
qwen_service_instance: ProductOptimizerQwen | None = None

def get_qwen_optimize_service() -> ProductOptimizerQwen:
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
            print("--- LAZY LOADING: Initialisation du ProductOptimizerQwen (chargement du modèle)... ---")
            qwen_service_instance = ProductOptimizerQwen()
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