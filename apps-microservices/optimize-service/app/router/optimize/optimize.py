from fastapi import APIRouter, HTTPException, Request
from app.schemas.optimize.optimize import OptimRequest, OptimResponse
from app.core.optimize.Optimize import ProductOptimizer
from app.core.optimize.Qwen3_4B_Q4 import ProductOptimizerQwen
import os

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
        tokenizer = request.app.state.qwen_tokenizer
        model = request.app.state.qwen_model

        optimizing_service = ProductOptimizerQwen(tokenizer, model)
        #optimizeQwen = optimizing_service.optimize_product(request.dict())
        optimizeQwen = optimizing_service.optimize_product(payload.dict())

        print(optimizeQwen)

        # ⚠️ S'assurer que "data" est bien retourné
        return {"data": [optimizeQwen]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))