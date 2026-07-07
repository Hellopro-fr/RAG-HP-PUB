import logging
from fastapi import APIRouter, HTTPException, Body

from app.schemas.prix import CaracteristiqueRequest, CaracteristiqueResponse, ReponseResult
from app.schemas.prix import QuestionnaireRequest, QuestionnaireResponse
from app.schemas.prix import QuestionnaireV2Request, QuestionnaireV2Response
from app.schemas.prix import CaracteristiqueLotRequest, CaracteristiqueLotResponse, CaracteristiqueLotItemResult
from app.core.prix_service import run_identification, run_questionnaire, run_questionnaire_v2, run_identification_lot

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
            id_prompt=request.id_prompt,
            source=request.source
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
            nom_categorie=request.nom_categorie,
            texte_prompt=request.texte_prompt,
            model=request.model,
            type_source=request.type_source
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


@router.post("/prix/questionnaire-v2", tags=["Prix - Questionnaire V2"], response_model=QuestionnaireV2Response)
async def questionnaire_prix_v2(request: QuestionnaireV2Request = Body(...)):
    """
    Endpoint V2 du questionnaire prix : matching équivalences × _cppi + LLM.

    Remplace la recherche RAG par un matching direct via les caractéristiques textuelles
    de l'acheteur (équivalences filtrées) contre les prix caractérisés en base (_cppi).
    Les résultats matchés sont formatés et envoyés au LLM (prompt 114).
    """
    try:
        logger.info(f"Requête /prix/questionnaire-v2: id_categorie={request.id_categorie}, {len(request.equivalences)} équivalences")

        if not request.id_categorie.strip():
            raise ValueError("L'id_categorie ne peut pas être vide.")
        if not request.equivalences:
            raise ValueError("Les equivalences ne peuvent pas être vides.")
        if not request.texte_prompt.strip():
            raise ValueError("Le texte_prompt ne peut pas être vide.")

        result = await run_questionnaire_v2(
            equivalences=request.equivalences,
            id_categorie=request.id_categorie,
            nom_categorie=request.nom_categorie,
            texte_prompt=request.texte_prompt,
            model=request.model,
            id_reponse_q1=request.id_reponse_q1,
            nom_reponse_q1=request.nom_reponse_q1,
            source=request.source
        )

        response = QuestionnaireV2Response(
            success=result.get("success", False),
            reponse=result.get("reponse"),
            matching=result.get("matching"),
            api_response=result.get("api_response"),
            time_elapsed=result.get("time_elapsed"),
            message=result.get("message", "")
        )

        logger.info(f"Réponse /prix/questionnaire-v2: success={response.success}, message={response.message}")
        return response

    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")


@router.post("/prix/caracteristique-lot", tags=["Prix - Caractéristiques Lot"], response_model=CaracteristiqueLotResponse)
async def extract_caracteristiques_lot(request: CaracteristiqueLotRequest = Body(...)):
    """
    Endpoint batch pour extraire les caractéristiques prix de plusieurs catégories en parallèle.
    
    Accepte une liste de CaracteristiqueRequest et les traite en parallèle (max 5 simultanées)
    via asyncio.Semaphore, suivant le pattern de prix-extraction-message/prix_extractor.py.
    """
    try:
        total = len(request.categories)
        logger.info(f"Requête /prix/caracteristique-lot: {total} catégories")
        
        if total == 0:
            raise ValueError("La liste de catégories ne peut pas être vide.")
        
        # Convertir la liste de CaracteristiqueRequest en liste de dicts
        categories_dicts = [
            {"id_categorie": str(cat.id_categorie), "id_prompt": cat.id_prompt, "source": cat.source}
            for cat in request.categories
        ]
        
        result = await run_identification_lot(categories=categories_dicts)
        
        # Construire les résultats par catégorie
        item_results = []
        for r in result.get("results", []):
            # Construire la liste de ReponseResult si des données existent
            data_results = None
            if r.get("data") and isinstance(r["data"], list):
                data_results = [ReponseResult(**item) if isinstance(item, dict) else item for item in r["data"]]
            
            item_results.append(CaracteristiqueLotItemResult(
                id_categorie=r.get("id_categorie", ""),
                success=r.get("success", False),
                data=data_results,
                raw=r.get("raw"),
                errors=r.get("errors", []),
                skipped=r.get("skipped", []),
                time_elapsed=r.get("time_elapsed"),
                message=r.get("message", "")
            ))
        
        response = CaracteristiqueLotResponse(
            success=result.get("success", False),
            total=result.get("total", 0),
            success_count=result.get("success_count", 0),
            error_count=result.get("error_count", 0),
            results=item_results,
            time_elapsed=result.get("time_elapsed"),
            message=result.get("message", "")
        )
        
        logger.info(f"Réponse /prix/caracteristique-lot: {response.success_count}/{response.total} succès")
        return response
        
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")
