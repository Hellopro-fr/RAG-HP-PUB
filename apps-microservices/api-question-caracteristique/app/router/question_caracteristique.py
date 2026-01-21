import json
from re import A
from typing import List
from fastapi import APIRouter, HTTPException, Body, WebSocket, WebSocketDisconnect
from app.schemas.question_caracteristique import  RequestProcessus, ApiResponse

from common_utils.grpc_clients.schemas.chat import ChatRequest, ChatProvider
# from app.core.search import search_in_milvus
from app.core.question_generator import QuestionGenerator
from app.core.caracteristique_generator import CaracteristiqueGenerator
from app.core.enrichissement_generator import EnrichissementGenerator
from app.core.equivalence_generator import EquivalenceGenerator
from app.core.caracterisation_produit import CaracterisationProduitGenerator

from app.core.api_client import HelloProAPIClient

from app.core.credentials import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/generate/question1", response_model=ApiResponse)
@router.post("/generate/question2aN", response_model=ApiResponse)
async def generate_questions(request: RequestProcessus = Body(...)):
    """
    Lance la génération complète de question 1 et question 2aN pour une catégorie
    
    Args:
        request: Paramètres de la requête (id_categorie, is_reset, etc.)
    
    Returns:
        ApiResponse avec le résultat de la génération
    """
    try:
        # On récupère le chemin utilisé
        path = request.url.path
        etape = "1"
        step = "question1"
        if "question2aN" in path:
            etape = "2"
            step = "question2aN"

        # Validation de base
        if not request.id_categorie:
            raise ValueError("ID catégorie requis")
        
        logger.info(f"Début génération {step} pour catégorie: {request.id_categorie}")
        
        # Initialiser le générateur
        api_client = HelloProAPIClient()  
        generator = QuestionGenerator(api_client, etape)
                
        # Lancer la génération
        result = await generator.generate_all_questions(request)
        
        # Fermer les connexions
        await generator.close()
        
        logger.info(f"Génération terminée pour catégorie: {request.id_categorie}")
        
        return ApiResponse(
            success=True,
            message=f"{step} générées avec succès pour catégorie: {request.id_categorie}",
            data=result.dict()
        )
        
    except ValueError as ve:
        logger.error(f"Erreur de validation: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    
    except Exception as e:
        logger.error(f"Erreur lors de la génération: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne du serveur: {str(e)}"
        )



@router.post("/generate/list_caracteristiques", response_model=ApiResponse)
@router.post("/generate/info_caracteristiques", response_model=ApiResponse)
async def generate_caracteristiques(request: RequestProcessus = Body(...)):
    """
    Lance la génération complète de list de caractéristiques et info caractéristiques 1a1 pour une catégorie
    
    Processus:
    1. Génère 25 caractéristiques initiales
    2. Pour chaque caractéristique, génère les valeurs (textuelles ou numériques)
    
    Args:
        request: Paramètres de la requête (id_categorie, is_reset, etc.)
    
    Returns:
        ApiResponse avec le résultat de la génération
    """
    try:
        # On récupère le chemin utilisé
        path = request.url.path
        etape = "3"
        step = "list_caracteristiques"
        if "info_caracteristiques" in path:
            etape = "4"
            step = "info_caracteristiques"

        # Validation de base
        if not request.id_categorie:
            raise ValueError("ID catégorie requis")
        
        logger.info(f"Début génération caractéristiques pour catégorie: {request.id_categorie}")
        
        # Initialiser le générateur
        api_client = HelloProAPIClient()  
        generator = CaracteristiqueGenerator(api_client, etape)
                
        # Lancer la génération
        result = await generator.generate_all_caracteristiques(request)
        
        # Fermer les connexions
        await generator.close()
        
        logger.info(f"Génération terminée pour catégorie: {request.id_categorie}")
        
        return ApiResponse(
            success=True,
            message=f"Caractéristiques générées avec succès pour catégorie: {request.id_categorie}",
            data=result.dict()
        )
        
    except ValueError as ve:
        logger.error(f"Erreur de validation: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    
    except Exception as e:
        logger.error(f"Erreur lors de la génération: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne du serveur: {str(e)}"
        )


@router.post("/generate/enrichissement", response_model=ApiResponse)
async def generate_enrichissement(request: RequestProcessus = Body(...)):
    """
    Lance le processus d'enrichissement des caractéristiques via les questions
    
    Processus:
    1. Récupère les questions générées (Q1 et Q2aN)
    2. Récupère le jeu de caractéristiques final
    3. Pour chaque question, vérifie si elle nécessite des ajouts/modifications de caractéristiques
    4. Met à jour le jeu de caractéristiques progressivement
    5. Sauvegarde le jeu final enrichi
    
    Args:
        request: Paramètres de la requête (id_categorie, is_reset, etc.)
    
    Returns:
        ApiResponse avec le résultat de l'enrichissement
    """
    try:
        # Validation de base
        if not request.id_categorie:
            raise ValueError("ID catégorie requis")
        
        logger.info(f"Début enrichissement pour catégorie: {request.id_categorie}")
        
        # Initialiser le générateur
        api_client = HelloProAPIClient()  
        generator = EnrichissementGenerator(api_client)
                
        # Lancer l'enrichissement
        result = await generator.generate_enrichissement(request)
        
        # Fermer les connexions
        await generator.close()
        
        logger.info(f"Enrichissement terminé pour catégorie: {request.id_categorie}")
        
        return ApiResponse(
            success=True,
            message=f"Enrichissement terminé avec succès pour catégorie: {request.id_categorie}",
            data=result.dict()
        )
        
    except ValueError as ve:
        logger.error(f"Erreur de validation: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    
    except Exception as e:
        logger.error(f"Erreur lors de l'enrichissement: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne du serveur: {str(e)}"
        )


@router.post("/generate/equivalences", response_model=ApiResponse)
async def generate_equivalences(request: RequestProcessus = Body(...)):
    """
    Lance le processus de génération des équivalences Question/Caractéristique
    
    Processus:
    1. Récupère les questions générées (Q1 et Q2aN)
    2. Récupère le jeu de caractéristiques final
    3. Pour Question 1: génère les équivalences entre réponses et caractéristiques
    4. Pour chaque Question suivante: génère les équivalences
    5. Sauvegarde directement via l'API
    
    Args:
        request: Paramètres de la requête (id_categorie, is_reset, etc.)
    
    Returns:
        ApiResponse avec le résultat de la génération
    """
    try:
        # Validation de base
        if not request.id_categorie:
            raise ValueError("ID catégorie requis")
        
        logger.info(f"Début génération équivalences pour catégorie: {request.id_categorie}")
        
        # Initialiser le générateur
        api_client = HelloProAPIClient()  
        generator = EquivalenceGenerator(api_client)
                
        # Lancer la génération
        result = await generator.generate_all_equivalences(request)
        
        # Fermer les connexions
        await generator.close()
        
        logger.info(f"Génération équivalences terminée pour catégorie: {request.id_categorie}")
        
        return ApiResponse(
            success=True,
            message=f"Équivalences générées avec succès pour catégorie: {request.id_categorie}",
            data=result.dict()
        )
        
    except ValueError as ve:
        logger.error(f"Erreur de validation: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    
    except Exception as e:
        logger.error(f"Erreur lors de la génération: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne du serveur: {str(e)}"
        )


@router.post("/generate/caracterisation_produit", response_model=ApiResponse)
async def generate_caracterisation_produit(request: RequestProcessus = Body(...)):
    """
    Lance le processus de caractérisation des produits via LLM
    
    Processus:
    1. Récupère les produits scrapés de la catégorie
    2. Pour chaque produit, appelle le LLM avec le jeu de caractéristiques
    3. Fait une repasse pour valider/corriger les caractéristiques
    4. Sauvegarde les résultats via l'API
    
    Args:
        request: Paramètres de la requête (id_categorie, is_reset, etc.)
    
    Returns:
        ApiResponse avec le résultat de la caractérisation
    """
    try:
        # Validation de base
        if not request.id_categorie:
            raise ValueError("ID catégorie requis")
        
        logger.info(f"Début caractérisation produit pour catégorie: {request.id_categorie}")
        
        # Initialiser le générateur
        api_client = HelloProAPIClient()  
        generator = CaracterisationProduitGenerator(api_client)
                
        # Lancer la caractérisation
        result = await generator.generate_all_caracterisations(request)
        
        # Fermer les connexions
        await generator.close()
        
        logger.info(f"Caractérisation terminée pour catégorie: {request.id_categorie}")
        
        return ApiResponse(
            success=True,
            message=f"Caractérisation terminée avec succès pour catégorie: {request.id_categorie}",
            data=result.dict()
        )
        
    except ValueError as ve:
        logger.error(f"Erreur de validation: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    
    except Exception as e:
        logger.error(f"Erreur lors de la caractérisation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne du serveur: {str(e)}"
        )


@router.post("/stop/{id_categorie}", response_model=ApiResponse)
async def stop_generation(id_categorie: str):
    """
    Marque une catégorie pour arrêt manuel lors de la prochaine vérification
    
    Args:
        id_categorie: ID de la catégorie à arrêter
    
    Returns:
        ApiResponse avec confirmation
    """
    try:
        # Charger la liste des stoppers
        stopper_file = "fichiers/stopper.json"
        stopper_list = utils.load_json_file(stopper_file) or []
        
        # Ajouter l'ID si pas déjà présent
        if id_categorie not in stopper_list:
            stopper_list.append(id_categorie)
            utils.save_json_file(stopper_file, stopper_list)
        
        return ApiResponse(
            success=True,
            message=f"Catégorie {id_categorie} marquée pour arrêt"
        )
        
    except Exception as e:
        logger.error(f"Erreur arrêt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))