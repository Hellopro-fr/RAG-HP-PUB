import logging
from fastapi import APIRouter, HTTPException, Body

from app.schemas.prix import CaracteristiqueRequest, CaracteristiqueResponse, ReponseResult
from app.core.prix_service import run_identification

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/prix/caracteristique", tags=["Prix - Caractéristiques"], response_model=CaracteristiqueResponse)
async def extract_caracteristiques(request: CaracteristiqueRequest = Body(...)):
    """
    Endpoint pour extraire les caractéristiques qui influencent le prix d'une catégorie.
    
    Pour chaque réponse Q1 de la catégorie, appelle le LLM (Gemini) pour identifier 
    les caractéristiques pertinentes, ajoute les équivalences, et sauvegarde en base.
    """
    try:
        logger.info(f"Requête /prix/caracteristique: id_categorie={request.id_categorie}")
        
        if not request.id_categorie.strip():
            raise ValueError("L'id_categorie ne peut pas être vide.")
        
        result = await run_identification(
            id_categorie=request.id_categorie,
            id_prompt=request.id_prompt
        )
        
        # Construire la liste de ReponseResult si des données existent
        data_results = None
        if result.get("data") and isinstance(result["data"], list):
            data_results = [ReponseResult(**item) if isinstance(item, dict) else item for item in result["data"]]
        
        response = CaracteristiqueResponse(
            success=result.get("success", False),
            data=data_results,
            raw=result.get("raw"),
            errors=result.get("errors", []),
            skipped=result.get("skipped", []),
            time_elapsed=result.get("time_elapsed"),
            message=result.get("message", "")
        )
        
        logger.info(f"Réponse /prix/caracteristique: success={response.success}, message={response.message}")
        return response
        
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")
