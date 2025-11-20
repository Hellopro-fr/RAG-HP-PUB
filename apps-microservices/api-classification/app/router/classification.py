from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Dict
import logging
import time
import asyncio
import httpx
import math
import os
from collections import defaultdict, Counter
from datetime import datetime

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

# --- START METRICS IMPORTS ---
from common_utils.metrics.prometheus import measure_processing_time, PROCESSING_TIME_SECONDS
# --- END METRICS IMPORTS ---

# --- START REDIS IMPORTS ---
from common_utils.redis.cache_service import scan_keys_by_prefix, get_json
# --- END REDIS IMPORTS ---

logger = logging.getLogger(__name__)

router = APIRouter()

# Instance globale du classificateur
classifier = ProductClassifier()

# Métriques de distribution (stockage en mémoire)
distribution_metrics = {
    "total_requests": 0,
    "total_products_processed": 0,
    "total_success": 0,
    "total_errors": 0,
    "total_processing_time": 0.0,
    "replica_stats": defaultdict(lambda: {
        "requests": 0,
        "products": 0,
        "success": 0,
        "errors": 0,
        "total_time": 0.0,
        "avg_time": 0.0,
        "last_used": None
    }),
    "batch_history": []  # Garder les 100 dernières requêtes
}

@router.get("/cache/categories", tags=["Cache"])
async def get_cached_categories():
    """Récupère toutes les catégories avec résumés en cache Redis"""
    try:
        # Scanner les nouvelles clés courtes (format: cache:cat_summary:<hash>)
        cache_keys = await scan_keys_by_prefix("cache:cat_summary")

        cached_categories = []
        for key in cache_keys:
            data = await get_json(key)
            if data:
                cached_categories.append({
                    "cache_key": key,
                    "data": data
                })

        return {
            "total_cached": len(cached_categories),
            "categories": cached_categories
        }
    except Exception as e:
        logger.error(f"Erreur récupération cache catégories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/classify", response_model=ClassificationResult)
@measure_processing_time(service_name="api-classification-service", payload_arg_name="product", collection_field_name="llm")
async def classify_single_product(product: ProductInput):
    """Classifie un seul produit"""
    try:
        # Déterminer le LLM à utiliser : celui spécifié dans la requête ou DeepSeek par défaut
        llm_to_use = product.llm if product.llm else "DeepSeek"
        enable_thinking = product.enable_thinking if product.enable_thinking is not None else False
        optimize = product.optimize if product.optimize is not None else False

        if not classifier.is_llm_configured():
            raise HTTPException(status_code=503, detail="LLM non configuré")

        # Conversion du modèle Pydantic en dict
        product_dict = {
            'id_produit': product.id_produit,
            'nom_produit': product.nom_produit,
            'description': product.description,
            'id_categorie_attendue': product.id_categorie_attendue
        }

        result = await classifier.classify_single(product_dict, llm_override=llm_to_use, enable_thinking=enable_thinking, optimize=optimize)

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
    # --- MANUAL INSTRUMENTATION START ---
    start_time_manual = time.monotonic()
    metric_status = 'success'
    llm_to_use = None
    # --- END MANUAL INSTRUMENTATION START ---
    try:
        # Déterminer le LLM à utiliser : celui spécifié dans la requête ou DeepSeek par défaut
        llm_to_use = batch_input.llm if batch_input.llm else "DeepSeek"
        enable_thinking = batch_input.enable_thinking if batch_input.enable_thinking is not None else False
        optimize = batch_input.optimize if batch_input.optimize is not None else False

        if not classifier.is_llm_configured():
            raise HTTPException(status_code=503, detail="LLM non configuré")

        if len(batch_input.produits) == 0:
            raise HTTPException(status_code=400, detail="Liste de produits vide")

        if len(batch_input.produits) > 200:  # Limite de sécurité
            raise HTTPException(status_code=400, detail="Trop de produits (max 200)")

        # Conversion des modèles Pydantic en dicts
        products_dict = []
        for product in batch_input.produits:
            products_dict.append({
                'id_produit': product.id_produit,
                'nom_produit': product.nom_produit,
                'description': product.description,
                'id_categorie_attendue': product.id_categorie_attendue
            })

        result = await classifier.classify_batch(products_dict, llm_override=llm_to_use, enable_thinking=enable_thinking, optimize=optimize)

        # Conversion en modèle de réponse
        classification_results = [ClassificationResult(**res) for res in result['resultats']]
        
        return BatchClassificationResponse(
            total_produits=result['total_produits'],
            success_count=result['success_count'],
            error_count=result['error_count'],
            resultats=classification_results,
            llm_type=result.get('llm_type'),
            processing_time_total=result['processing_time_total']
        )
        
    except HTTPException:
        metric_status = 'failure'
        raise
    except Exception as e:
        metric_status = 'failure'
        logger.error(f"Erreur classification batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # --- MANUAL INSTRUMENTATION FINALIZATION ---
        duration = time.monotonic() - start_time_manual
        num_products = len(batch_input.produits)
        collection_type = str(llm_to_use or "Default")

        if num_products == 0:
             PROCESSING_TIME_SECONDS.labels(
                service_name="api-classification-service", 
                status=metric_status, 
                collection_type='empty_batch'
            ).observe(duration)
        else:
            metric = PROCESSING_TIME_SECONDS.labels(
                service_name="api-classification-service",
                status=metric_status,
                collection_type=collection_type
            )
            # Observe the full duration once to increment the sum correctly
            metric.observe(duration)
            # Observe a zero duration for the rest of the items to increment the count correctly
            if num_products > 1:
                for _ in range(num_products - 1):
                    metric.observe(0)

# @router.post("/classify/batch/async")
# async def classify_batch_products_async(
#     batch_input: BatchProductsInput, 
#     background_tasks: BackgroundTasks
# ):
#     """Lance une classification en lot en arrière-plan (pour de gros volumes)"""
#     try:
#         if not classifier.is_llm_configured():
#             raise HTTPException(status_code=503, detail="LLM non configuré")
        
#         if len(batch_input.produits) == 0:
#             raise HTTPException(status_code=400, detail="Liste de produits vide")
        
#         # Génération d'un ID de tâche
#         task_id = f"batch_{int(time.time())}"
        
#         # Conversion des modèles Pydantic en dicts
#         products_dict = []
#         for product in batch_input.produits:
#             products_dict.append({
#                 'id_produit': product.id_produit,
#                 'nom_produit': product.nom_produit,
#                 'description': product.description,
#                 'id_categorie_attendue': product.id_categorie_attendue
#             })
        
#         # Lancement de la tâche en arrière-plan
#         background_tasks.add_task(
#             _process_batch_classification,
#             task_id,
#             products_dict
#         )
        
#         return {
#             "task_id": task_id,
#             "message": f"Classification de {len(products_dict)} produits lancée en arrière-plan",
#             "total_products": len(products_dict)
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Erreur classification batch async: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# def _process_batch_classification(task_id: str, products: list):
#     """Traite la classification en arrière-plan"""
#     global task_results
#     try:
#         # Marquer comme en cours
#         task_results[task_id] = {
#             "status": "PROCESSING",
#             "progress": 0,
#             "total_products": len(products),
#             "start_time": time.time()
#         }
        
#         logger.info(f"Début traitement batch {task_id} - {len(products)} produits")
#         result = classifier.classify_batch(products)
        
#         # Sauvegarder le résultat complet
#         task_results[task_id] = {
#             "status": "COMPLETED",
#             "progress": 100,
#             "total_products": len(products),
#             "start_time": task_results[task_id]["start_time"],
#             "end_time": time.time(),
#             "result": result
#         }
        
#         logger.info(f"Fin traitement batch {task_id} - {result['success_count']} succès, {result['error_count']} erreurs")
        
#     except Exception as e:
#         # Marquer comme échoué
#         task_results[task_id] = {
#             "status": "FAILED",
#             "progress": 0,
#             "total_products": len(products),
#             "start_time": task_results[task_id]["start_time"],
#             "end_time": time.time(),
#             "error": str(e)
#         }
#         logger.error(f"Erreur traitement batch {task_id}: {e}")

# @router.get("/classify/batch/status/{task_id}")
# async def get_batch_status(task_id: str):
#     global task_results
#     """Récupère le statut d'une tâche de classification en lot"""
#     if task_id not in task_results:
#         raise HTTPException(status_code=404, detail="Tâche non trouvée")
    
#     task_info = task_results[task_id].copy()
    
#     # Ajouter des infos calculées
#     if "start_time" in task_info:
#         elapsed_time = time.time() - task_info["start_time"]
#         task_info["elapsed_time"] = round(elapsed_time, 2)
    
#     return task_info

# @router.get("/classify/batch/result/{task_id}", response_model=BatchClassificationResponse)
# async def get_batch_result(task_id: str):
#     global task_results
#     """Récupère le résultat complet d'une tâche terminée"""
#     if task_id not in task_results:
#         raise HTTPException(status_code=404, detail="Tâche non trouvée")
    
#     task_info = task_results[task_id]
    
#     if task_info["status"] == "PROCESSING":
#         raise HTTPException(status_code=202, detail="Tâche en cours de traitement")
#     elif task_info["status"] == "FAILED":
#         raise HTTPException(status_code=500, detail=f"Tâche échouée: {task_info.get('error', 'Erreur inconnue')}")
#     elif task_info["status"] != "COMPLETED":
#         raise HTTPException(status_code=400, detail=f"Statut de tâche invalide: {task_info['status']}")
    
#     result = task_info["result"]
#     classification_results = [ClassificationResult(**res) for res in result['resultats']]
    
#     return BatchClassificationResponse(
#         total_produits=result['total_produits'],
#         success_count=result['success_count'],
#         error_count=result['error_count'],
#         resultats=classification_results,
#         processing_time_total=result['processing_time_total']
#     )

# @router.delete("/classify/batch/task/{task_id}")
# async def delete_batch_task(task_id: str):
#     global task_results
#     """Supprime une tâche du cache"""
#     if task_id not in task_results:
#         raise HTTPException(status_code=404, detail="Tâche non trouvée")
    
#     del task_results[task_id]
#     return {"message": f"Tâche {task_id} supprimée"}

# @router.get("/classify/batch/tasks")
# async def list_batch_tasks():
#     global task_results
#     """Liste toutes les tâches avec leur statut"""
#     tasks_summary = {}
#     for task_id, task_info in task_results.items():
#         tasks_summary[task_id] = {
#             "status": task_info["status"],
#             "progress": task_info.get("progress", 0),
#             "total_products": task_info.get("total_products", 0),
#             "elapsed_time": round(time.time() - task_info["start_time"], 2) if "start_time" in task_info else None
#         }
    
#     return {"tasks": tasks_summary, "total_tasks": len(tasks_summary)}

@router.post("/classify/batch/distributed", response_model=BatchClassificationResponse)
async def classify_batch_distributed(batch_input: BatchProductsInput):
    """
    Classifie plusieurs produits en distribuant intelligemment la charge sur les replicas disponibles.

    Cette méthode divise automatiquement le batch en sous-batches et les envoie en parallèle
    aux différentes instances du service via des requêtes HTTP, exploitant ainsi tous les replicas
    pour accélérer le traitement global.

    Avantages:
    - Utilise tous les replicas disponibles (4x plus rapide avec 4 replicas)
    - Division automatique selon le nombre de produits
    - Agrégation transparente des résultats
    """
    # --- MANUAL INSTRUMENTATION START ---
    start_time_manual = time.monotonic()
    metric_status = 'success'
    llm_to_use = None
    # --- END MANUAL INSTRUMENTATION START ---
    try:
        start_time = time.time()

        # Déterminer le LLM à utiliser
        llm_to_use = batch_input.llm if batch_input.llm else "DeepSeek"
        enable_thinking = batch_input.enable_thinking if batch_input.enable_thinking is not None else False
        optimize = batch_input.optimize if batch_input.optimize is not None else False

        if not classifier.is_llm_configured():
            raise HTTPException(status_code=503, detail="LLM non configuré")

        if len(batch_input.produits) == 0:
            raise HTTPException(status_code=400, detail="Liste de produits vide")

        if len(batch_input.produits) > 1000:
            raise HTTPException(status_code=400, detail="Trop de produits (max 1000)")

        # Configuration de distribution
        # Récupérer le nom du service depuis une variable d'environnement ou utiliser le nom par défaut
        service_name = os.getenv("CLASSIFICATION_SERVICE_NAME", "api-classification-service")
        service_port = os.getenv("CLASSIFICATION_SERVICE_PORT", "8577")
        num_replicas = int(os.getenv("CLASSIFICATION_NUM_REPLICAS", "4"))

        total_products = len(batch_input.produits)

        # Si on a moins de produits que de replicas, on utilise seulement le nombre nécessaire
        replicas_to_use = min(num_replicas, total_products)

        # Calculer la taille de chaque sous-batch
        batch_size = math.ceil(total_products / replicas_to_use)

        # logger.info(f"📦 Distribution de {total_products} produits sur {replicas_to_use} replicas ({batch_size} produits/replica)")

        # Diviser les produits en sous-batches
        sub_batches = []
        for i in range(0, total_products, batch_size):
            sub_batch = batch_input.produits[i:i + batch_size]
            sub_batches.append(sub_batch)

        # Créer les requêtes HTTP pour chaque sous-batch
        async def send_sub_batch(sub_batch: List[ProductInput], batch_index: int):
            """Envoie un sous-batch au service de classification"""
            sub_batch_start = time.time()
            replica_used = None

            try:
                # Utilise le nom du service Docker - le DNS round-robin distribue automatiquement
                # IMPORTANT: Chaque nouvelle connexion TCP = nouveau round-robin
                url = f"http://{service_name}:{service_port}/classification/classify/batch"

                payload = {
                    "produits": [p.dict() for p in sub_batch],
                    "llm": llm_to_use,
                    "enable_thinking": enable_thinking,
                    "optimize": optimize
                }

                # Créer un nouveau client pour chaque requête avec keep-alive désactivé
                # Cela force une nouvelle connexion TCP et donc une nouvelle résolution DNS round-robin
                limits = httpx.Limits(max_keepalive_connections=0, max_connections=1)
                async with httpx.AsyncClient(timeout=300.0, limits=limits) as client:
                    # logger.info(f"  → Envoi du sous-batch {batch_index + 1}/{len(sub_batches)} ({len(sub_batch)} produits) à {url}")
                    response = await client.post(url, json=payload, headers={"Connection": "close"})
                    response.raise_for_status()
                    result = response.json()

                    # Extraire l'identifiant du replica depuis les headers (si disponible) ou générer un ID
                    replica_used = response.headers.get("X-Replica-ID", f"replica-{batch_index % num_replicas}")
                    sub_batch_time = time.time() - sub_batch_start

                    # Mettre à jour les métriques du replica
                    distribution_metrics["replica_stats"][replica_used]["requests"] += 1
                    distribution_metrics["replica_stats"][replica_used]["products"] += len(sub_batch)
                    distribution_metrics["replica_stats"][replica_used]["success"] += result.get('success_count', 0)
                    distribution_metrics["replica_stats"][replica_used]["errors"] += result.get('error_count', 0)
                    distribution_metrics["replica_stats"][replica_used]["total_time"] += sub_batch_time
                    distribution_metrics["replica_stats"][replica_used]["avg_time"] = (
                        distribution_metrics["replica_stats"][replica_used]["total_time"] /
                        distribution_metrics["replica_stats"][replica_used]["requests"]
                    )
                    distribution_metrics["replica_stats"][replica_used]["last_used"] = datetime.now().isoformat()

                    # logger.info(f"  ✅ Sous-batch {batch_index + 1} terminé sur {replica_used} en {sub_batch_time:.2f}s : {result.get('success_count', 0)} succès, {result.get('error_count', 0)} erreurs")
                    return result

            except httpx.HTTPError as e:
                logger.error(f"  ❌ Erreur HTTP pour sous-batch {batch_index + 1}: {e}")
                # Retourner des résultats d'erreur pour tous les produits du sous-batch
                error_results = []
                for product in sub_batch:
                    error_results.append({
                        'id_produit': product.id_produit,
                        'titre_produit': product.nom_produit,
                        'description_produit': product.description,
                        'status': 'ERROR',
                        'id_categorie': None,
                        'nom_categorie': None,
                        'score_llm': None,
                        'error': f'Erreur HTTP: {str(e)}',
                        'llm_type': llm_to_use,
                        'enable_thinking': enable_thinking,
                        'llm_response': None,
                        'processing_time': 0.0
                    })
                return {
                    'total_produits': len(sub_batch),
                    'success_count': 0,
                    'error_count': len(sub_batch),
                    'resultats': error_results,
                    'llm_type': llm_to_use,
                    'processing_time_total': 0.0
                }
            except Exception as e:
                logger.error(f"  ❌ Erreur inattendue pour sous-batch {batch_index + 1}: {e}")
                # Retourner des résultats d'erreur
                error_results = []
                for product in sub_batch:
                    error_results.append({
                        'id_produit': product.id_produit,
                        'titre_produit': product.nom_produit,
                        'description_produit': product.description,
                        'status': 'ERROR',
                        'id_categorie': None,
                        'nom_categorie': None,
                        'score_llm': None,
                        'error': f'Erreur: {str(e)}',
                        'llm_type': llm_to_use,
                        'enable_thinking': enable_thinking,
                        'llm_response': None,
                        'processing_time': 0.0
                    })
                return {
                    'total_produits': len(sub_batch),
                    'success_count': 0,
                    'error_count': len(sub_batch),
                    'resultats': error_results,
                    'llm_type': llm_to_use,
                    'processing_time_total': 0.0
                }

        # Envoyer tous les sous-batches en parallèle
        # Docker DNS round-robin distribue automatiquement sur les replicas disponibles
        tasks = [send_sub_batch(sub_batch, i) for i, sub_batch in enumerate(sub_batches)]
        results = await asyncio.gather(*tasks)

        # Agréger tous les résultats
        all_results = []
        total_success = 0
        total_errors = 0

        for result in results:
            all_results.extend(result['resultats'])
            total_success += result['success_count']
            total_errors += result['error_count']

        processing_time = time.time() - start_time

        # Mettre à jour les métriques globales
        distribution_metrics["total_requests"] += 1
        distribution_metrics["total_products_processed"] += total_products
        distribution_metrics["total_success"] += total_success
        distribution_metrics["total_errors"] += total_errors
        distribution_metrics["total_processing_time"] += processing_time

        # Ajouter à l'historique (garder les 100 dernières)
        batch_record = {
            "timestamp": datetime.now().isoformat(),
            "products": total_products,
            "replicas_used": replicas_to_use,
            "success": total_success,
            "errors": total_errors,
            "processing_time": round(processing_time, 2),
            "products_per_second": round(total_products / processing_time, 2) if processing_time > 0 else 0
        }
        distribution_metrics["batch_history"].append(batch_record)
        if len(distribution_metrics["batch_history"]) > 100:
            distribution_metrics["batch_history"].pop(0)

        logger.info(f"Batch distribué: {total_products} produits, {replicas_to_use} replicas, {processing_time:.2f}s, {total_products/processing_time:.2f} p/s")

        # Conversion en modèle de réponse
        classification_results = [ClassificationResult(**res) for res in all_results]

        return BatchClassificationResponse(
            total_produits=total_products,
            success_count=total_success,
            error_count=total_errors,
            resultats=classification_results,
            llm_type=llm_to_use,
            processing_time_total=processing_time
        )

    except HTTPException:
        metric_status = 'failure'
        raise
    except Exception as e:
        metric_status = 'failure'
        logger.error(f"Erreur classification batch distribuée: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # --- MANUAL INSTRUMENTATION FINALIZATION ---
        duration = time.monotonic() - start_time_manual
        num_products = len(batch_input.produits)
        collection_type = str(llm_to_use or "Default")

        if num_products == 0:
             PROCESSING_TIME_SECONDS.labels(
                service_name="api-classification-service", 
                status=metric_status, 
                collection_type='empty_batch'
            ).observe(duration)
        else:
            metric = PROCESSING_TIME_SECONDS.labels(
                service_name="api-classification-service",
                status=metric_status,
                collection_type=collection_type
            )
            # Observe the full duration once to increment the sum correctly
            metric.observe(duration)
            # Observe a zero duration for the rest of the items to increment the count correctly
            if num_products > 1:
                for _ in range(num_products - 1):
                    metric.observe(0)

