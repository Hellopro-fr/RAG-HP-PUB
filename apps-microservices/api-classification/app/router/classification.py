from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import logging
import time

from app.schemas.classification import (
    ProductInput,
    BatchProductsInput,
    ClassificationResult,
    BatchClassificationResponse,
    ConfigurationRequest,
    ApiStatus
)
from app.core.classifier import ProductClassifier
from app.core.search import test_search_api_connection

logger = logging.getLogger(__name__)

router = APIRouter()

# Instance globale du classificateur
classifier = ProductClassifier()

@router.get("/status", response_model=ApiStatus)
async def get_status():
    """Récupère le statut de l'API de classification"""
    try:
        search_available = test_search_api_connection()
        llm_configured = classifier.is_llm_configured()
        
        return ApiStatus(
            status="healthy" if (search_available and llm_configured) else "degraded",
            llm_configured=llm_configured,
            search_api_available=search_available,
            current_config=classifier.get_configuration()
        )
    except Exception as e:
        logger.error(f"Erreur status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/configure")
async def configure_classifier(config: ConfigurationRequest):
    """Configure le classificateur"""
    try:
        classifier.update_configuration(config.dict())
        return {"message": "Configuration mise à jour", "config": classifier.get_configuration()}
    except Exception as e:
        logger.error(f"Erreur configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/config")
async def get_configuration():
    """Récupère la configuration actuelle"""
    return {"config": classifier.get_configuration()}

@router.post("/classify", response_model=ClassificationResult)
async def classify_single_product(product: ProductInput):
    """Classifie un seul produit"""
    try:
        if not classifier.is_llm_configured():
            raise HTTPException(status_code=503, detail="LLM non configuré")
        
        # Conversion du modèle Pydantic en dict
        product_dict = {
            'id_produit': product.id_produit,
            'nom_produit': product.nom_produit,
            'description': product.description,
            'id_categorie_attendue': product.id_categorie_attendue
        }
        
        result = classifier.classify_single(product_dict)
        
        # Conversion en modèle de réponse
        return ClassificationResult(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur classification single: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/classify/batch", response_model=BatchClassificationResponse)
async def classify_batch_products(batch_input: BatchProductsInput):
    """Classifie plusieurs produits en lot"""
    try:
        if not classifier.is_llm_configured():
            raise HTTPException(status_code=503, detail="LLM non configuré")
        
        if len(batch_input.produits) == 0:
            raise HTTPException(status_code=400, detail="Liste de produits vide")
        
        if len(batch_input.produits) > 100:  # Limite de sécurité
            raise HTTPException(status_code=400, detail="Trop de produits (max 100)")
        
        # Conversion des modèles Pydantic en dicts
        products_dict = []
        for product in batch_input.produits:
            products_dict.append({
                'id_produit': product.id_produit,
                'nom_produit': product.nom_produit,
                'description': product.description,
                'id_categorie_attendue': product.id_categorie_attendue
            })
        
        result = classifier.classify_batch(products_dict)
        
        # Conversion en modèle de réponse
        classification_results = [ClassificationResult(**res) for res in result['resultats']]
        
        return BatchClassificationResponse(
            total_produits=result['total_produits'],
            success_count=result['success_count'],
            error_count=result['error_count'],
            resultats=classification_results,
            processing_time_total=result['processing_time_total']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur classification batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/classify/batch/async")
async def classify_batch_products_async(
    batch_input: BatchProductsInput, 
    background_tasks: BackgroundTasks
):
    """Lance une classification en lot en arrière-plan (pour de gros volumes)"""
    try:
        if not classifier.is_llm_configured():
            raise HTTPException(status_code=503, detail="LLM non configuré")
        
        if len(batch_input.produits) == 0:
            raise HTTPException(status_code=400, detail="Liste de produits vide")
        
        # Génération d'un ID de tâche
        task_id = f"batch_{int(time.time())}"
        
        # Conversion des modèles Pydantic en dicts
        products_dict = []
        for product in batch_input.produits:
            products_dict.append({
                'id_produit': product.id_produit,
                'nom_produit': product.nom_produit,
                'description': product.description,
                'id_categorie_attendue': product.id_categorie_attendue
            })
        
        # Lancement de la tâche en arrière-plan
        background_tasks.add_task(
            _process_batch_classification,
            task_id,
            products_dict
        )
        
        return {
            "task_id": task_id,
            "message": f"Classification de {len(products_dict)} produits lancée en arrière-plan",
            "total_products": len(products_dict)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur classification batch async: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _process_batch_classification(task_id: str, products: list):
    """Traite la classification en arrière-plan"""
    global task_results
    try:
        # Marquer comme en cours
        task_results[task_id] = {
            "status": "PROCESSING",
            "progress": 0,
            "total_products": len(products),
            "start_time": time.time()
        }
        
        logger.info(f"Début traitement batch {task_id} - {len(products)} produits")
        result = classifier.classify_batch(products)
        
        # Sauvegarder le résultat complet
        task_results[task_id] = {
            "status": "COMPLETED",
            "progress": 100,
            "total_products": len(products),
            "start_time": task_results[task_id]["start_time"],
            "end_time": time.time(),
            "result": result
        }
        
        logger.info(f"Fin traitement batch {task_id} - {result['success_count']} succès, {result['error_count']} erreurs")
        
    except Exception as e:
        # Marquer comme échoué
        task_results[task_id] = {
            "status": "FAILED",
            "progress": 0,
            "total_products": len(products),
            "start_time": task_results[task_id]["start_time"],
            "end_time": time.time(),
            "error": str(e)
        }
        logger.error(f"Erreur traitement batch {task_id}: {e}")

@router.get("/classify/batch/status/{task_id}")
async def get_batch_status(task_id: str):
    global task_results
    """Récupère le statut d'une tâche de classification en lot"""
    if task_id not in task_results:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    
    task_info = task_results[task_id].copy()
    
    # Ajouter des infos calculées
    if "start_time" in task_info:
        elapsed_time = time.time() - task_info["start_time"]
        task_info["elapsed_time"] = round(elapsed_time, 2)
    
    return task_info

@router.get("/classify/batch/result/{task_id}", response_model=BatchClassificationResponse)
async def get_batch_result(task_id: str):
    global task_results
    """Récupère le résultat complet d'une tâche terminée"""
    if task_id not in task_results:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    
    task_info = task_results[task_id]
    
    if task_info["status"] == "PROCESSING":
        raise HTTPException(status_code=202, detail="Tâche en cours de traitement")
    elif task_info["status"] == "FAILED":
        raise HTTPException(status_code=500, detail=f"Tâche échouée: {task_info.get('error', 'Erreur inconnue')}")
    elif task_info["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail=f"Statut de tâche invalide: {task_info['status']}")
    
    result = task_info["result"]
    classification_results = [ClassificationResult(**res) for res in result['resultats']]
    
    return BatchClassificationResponse(
        total_produits=result['total_produits'],
        success_count=result['success_count'],
        error_count=result['error_count'],
        resultats=classification_results,
        processing_time_total=result['processing_time_total']
    )

@router.delete("/classify/batch/task/{task_id}")
async def delete_batch_task(task_id: str):
    global task_results
    """Supprime une tâche du cache"""
    if task_id not in task_results:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    
    del task_results[task_id]
    return {"message": f"Tâche {task_id} supprimée"}

@router.get("/classify/batch/tasks")
async def list_batch_tasks():
    global task_results
    """Liste toutes les tâches avec leur statut"""
    tasks_summary = {}
    for task_id, task_info in task_results.items():
        tasks_summary[task_id] = {
            "status": task_info["status"],
            "progress": task_info.get("progress", 0),
            "total_products": task_info.get("total_products", 0),
            "elapsed_time": round(time.time() - task_info["start_time"], 2) if "start_time" in task_info else None
        }
    
    return {"tasks": tasks_summary, "total_tasks": len(tasks_summary)}

@router.get("/test")
async def test_classification():
    """Endpoint de test pour valider le fonctionnement"""
    test_product = {
        'id_produit': 'test_001',
        'nom_produit': 'Perceuse électrique',
        'description': 'Perceuse électrique professionnelle 750W avec mandrin automatique',
        'id_categorie_attendue': None
    }
    
    try:
        if not classifier.is_llm_configured():
            return {"error": "LLM non configuré", "test_product": test_product}
        
        result = classifier.classify_single(test_product)
        return {"test_result": result, "test_product": test_product}
        
    except Exception as e:
        logger.error(f"Erreur test: {e}")
        return {"error": str(e), "test_product": test_product}