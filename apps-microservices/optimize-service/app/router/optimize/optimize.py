from fastapi import APIRouter, HTTPException, Request
from app.schemas.optimize.optimize import OptimRequest, OptimResponse, BatchOptimRequest, BatchOptimResponse
from app.core.optimize.traitement_donnees import TraitementDonnees
from typing import List, Dict, Any
import time
import os
import threading
import traceback
import asyncio
import json
import logging
import ast

router = APIRouter()

# Import des clients gRPC de notre architecture
from common_utils.grpc_clients import (
    llm_client,
)

from common_utils.grpc_clients.schemas.chat import ChatRequest

# --- Configuration du Batching et Retry ---
BATCH_SIZE = 5  # Nombre de produits à traiter en parallèle
MAX_RETRIES = 3  # Nombre de tentatives avant échec définitif
RETRY_DELAY_SECONDS = 2.0  # Délai entre chaque retry

logger = logging.getLogger(__name__)

async def _process_single_product(product: Dict[str, Any], retry_count: int = 0) -> Dict[str, Any]:
    """
    Traite un seul produit en appelant le LLM.
    Gère automatiquement les retries en cas d'erreur.
    """
    product_id = product.get("id_produit_scrapping", "unknown")
    
    try:
        instancetraitement = TraitementDonnees()
        
        # Génération du prompt
        prompt = instancetraitement.generate_prompt(product)
        
        # Appel gRPC au LLM
        chat_request = ChatRequest(prompt=prompt)
        response = await llm_client.get_llm_chat_response(chat_request)
        
        # Nettoyage de la réponse
        cleaned_response = instancetraitement.clean_json_response(response)
        
        # Parsing JSON
        try:
            parsed_response = json.loads(cleaned_response)
            
            if not parsed_response:
                raise ValueError("LLM n'a pas retourné de résultat")
            
            logger.info(f"[SUCCESS] Produit {product_id} traité avec succès (tentative {retry_count + 1})")
            return {
                "status": "success",
                "id_produit_scrapping": product_id,
                "data": parsed_response,
                "retry_count": retry_count
            }
            
        except json.JSONDecodeError:
            # Tentative avec ast.literal_eval
            try:
                parsed_response = ast.literal_eval(cleaned_response)
                logger.info(f"[SUCCESS] Produit {product_id} traité via ast.literal_eval")
                return {
                    "status": "success",
                    "id_produit_scrapping": product_id,
                    "data": parsed_response,
                    "retry_count": retry_count
                }
            except Exception as parse_error:
                raise ValueError(f"Parsing échoué: {cleaned_response[:200]}")
    
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        
        # Gestion du retry
        if retry_count < MAX_RETRIES:
            logger.warning(f"[RETRY {retry_count + 1}/{MAX_RETRIES}] Produit {product_id} - Erreur: {error_msg}")
            await asyncio.sleep(RETRY_DELAY_SECONDS)  # Attente avant retry
            return await _process_single_product(product, retry_count + 1)
        else:
            logger.error(f"[FAILURE] Produit {product_id} - Échec définitif après {MAX_RETRIES} tentatives: {error_msg}")
            return {
                "status": "error",
                "id_produit_scrapping": product_id,
                "error": error_msg,
                "retry_count": retry_count
            }


async def _process_batch(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Traite un batch de produits en parallèle.
    Utilise asyncio.gather pour exécuter toutes les tâches simultanément.
    """
    if not products:
        return []
    
    batch_size = len(products)
    logger.info(f"⚙️  Traitement d'un batch de {batch_size} produit(s)...")
    
    start_time = time.monotonic()
    
    # Créer une tâche asyncio pour chaque produit
    tasks = [_process_single_product(product) for product in products]
    
    # Exécuter toutes les tâches en parallèle
    results = await asyncio.gather(*tasks)
    
    end_time = time.monotonic()
    duration = end_time - start_time
    
    # Statistiques
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] == "error")
    
    logger.info(f"🏁 Batch terminé en {duration:.2f}s - Succès: {success_count}, Échecs: {error_count}")
    
    return results

@router.post("/qwen/v2", response_model=BatchOptimResponse)
async def optimizeQwen(payload: BatchOptimRequest):
    """
    Endpoint principal qui reçoit un batch de produits et les traite par lots.
    """
    try:
        overall_start_time = time.time()
        total_products = len(payload.products)
        
        logger.info(f"📦 Réception de {total_products} produit(s)")
        
        # Conversion des produits en dict
        products_data = [product.dict() for product in payload.products]
        
        # Division en batches de BATCH_SIZE
        all_results = []
        for i in range(0, total_products, BATCH_SIZE):
            batch = products_data[i:i + BATCH_SIZE]
            batch_results = await _process_batch(batch)
            all_results.extend(batch_results)
        
        # Formatage de la réponse finale
        formatted_results = []
        for result in all_results:
            if result["status"] == "success":
                formatted_results.append({
                    "id_produit_scrapping": result["id_produit_scrapping"],
                    "success": result["data"]
                })
            else:
                formatted_results.append({
                    "id_produit_scrapping": result["id_produit_scrapping"],
                    "error": result["error"]
                })
        
        overall_end_time = time.time()
        total_duration = overall_end_time - overall_start_time
        
        success_total = sum(1 for r in all_results if r["status"] == "success")
        error_total = sum(1 for r in all_results if r["status"] == "error")
        
        logger.info(f"✅ Traitement complet terminé en {total_duration:.2f}s")
        logger.info(f"📊 Résultats: {success_total} succès, {error_total} échecs sur {total_products} produits")
        
        return {"data": formatted_results}
    
    except Exception as e:
        logger.error(f"❌ Erreur critique: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du traitement: {type(e).__name__}: {str(e)}"
        )