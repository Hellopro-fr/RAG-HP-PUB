from fastapi import APIRouter, HTTPException
from app.schemas.optimize.optimize import OptimRequest, OptimResponse
from app.core.optimize.Optimize import ProductOptimizer
import os

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

@router.post("/", response_model=OptimResponse)
def optimize(request: OptimRequest):
    try:
        optimizing_service = ProductOptimizer(OPENAI_API_KEY)
        optimize = optimizing_service.optimize_product(request.dict())

        print(optimize)

        # ⚠️ S'assurer que "data" est bien retourné
        return {"data": [optimize]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))