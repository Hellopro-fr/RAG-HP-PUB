from fastapi import APIRouter, HTTPException, Body
from app.schemas.classify import ClassificationRequest, ClassificationResponse
# from app.core.classify import classify 
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/classify", tags=["Classification"])
async def classify(request: ClassificationRequest = Body(...)):
    try:
        if not request.data:
            raise ValueError("Le paramètre data ne peut pas être vide.")
        
        return { "response" : "OK" }
        
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")