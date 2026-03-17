import logging
from fastapi import APIRouter, HTTPException, Body

from app.schemas.prix import CaracteristiqueRequest, CaracteristiqueResponse, ReponseResult
from app.schemas.prix import QuestionnaireRequest, QuestionnaireResponse
from app.core.prix_service import run_identification, run_questionnaire

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


@router.post("/prix/questionnaire", tags=["Prix - Questionnaire"], response_model=QuestionnaireResponse)
async def questionnaire_prix(request: QuestionnaireRequest = Body(...)):
    """
    Endpoint pour extraire et structurer des informations de prix via RAG + LLM.
    
    Effectue une recherche RAG sur la source "prix" filtrée par id_categorie,
    formate les chunks trouvés, et les envoie au LLM (Gemini) avec le prompt 114
    pour générer une réponse structurée.
    """
    try:
        logger.info(f"Requête /prix/questionnaire: texte='{request.texte_recherche[:50]}...', id_categorie={request.id_categorie}")
        
        if not request.texte_recherche.strip():
            raise ValueError("Le texte_recherche ne peut pas être vide.")
        if not request.id_categorie.strip():
            raise ValueError("L'id_categorie ne peut pas être vide.")
        
        result = await run_questionnaire(
            texte_recherche=request.texte_recherche,
            id_categorie=request.id_categorie,
            nom_categorie=request.nom_categorie
        )
        
        response = QuestionnaireResponse(
            success=result.get("success", False),
            reponse=result.get("reponse"),
            api_response=result.get("api_response"),
            time_elapsed=result.get("time_elapsed"),
            message=result.get("message", "")
        )
        
        logger.info(f"Réponse /prix/questionnaire: success={response.success}, message={response.message}")
        return response
        
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")
