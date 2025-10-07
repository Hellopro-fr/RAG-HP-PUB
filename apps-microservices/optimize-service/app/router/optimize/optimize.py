from fastapi import APIRouter, HTTPException, Request
from app.schemas.optimize.optimize import OptimRequest, OptimResponse, BatchOptimRequest, BatchOptimResponse
from app.core.optimize.traitement_donnees import TraitementDonnees
from typing import List, Dict, Any
import time
import os
import traceback
import asyncio
import json
import ast

router = APIRouter()

from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest

# --- Configuration du Batching et Retry ---
BATCH_SIZE = 10  # Augmenté de 2 à 10 pour meilleur parallélisme
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 0.1
MAX_CONCURRENT_TASKS = 50  # Limite de tâches concurrentes
SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

global_traitement_donnees_instance = TraitementDonnees()

async def _process_single_product(product: Dict[str, Any], retry_count: int = 0) -> Dict[str, Any]:
    """
    Traite un seul produit en appelant le LLM avec gestion des retries.
    Utilise un sémaphore pour limiter la concurrence.
    """
    product_id = product.get("id_produit_scrapping", "unknown")
    
    async with SEMAPHORE:  # Limite la concurrence globale
        try:
            # Génération du prompt et appel LLM en séquence (optimisé)
            prompt = global_traitement_donnees_instance.generate_prompt(product)
            chat_request = ChatRequest(prompt=prompt)
            response = await llm_client.get_llm_chat_response(chat_request)
            
            # Nettoyage et parsing dans une seule étape
            cleaned_response = global_traitement_donnees_instance.clean_json_response(response)
            parsed_response = json.loads(cleaned_response)
            
            if not parsed_response:
                raise ValueError("LLM n'a pas retourné de résultat")
            
            print(f"[SUCCESS] Produit {product_id} traité")
            return {
                "status": "success",
                "id_produit_scrapping": product_id,
                "data": parsed_response,
            }
            
        except json.JSONDecodeError as e:
            error_msg = f"JSONDecodeError: {str(e)}"
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
        
        # Gestion des retries
        if retry_count < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            return await _process_single_product(product, retry_count + 1)
        else:
            print(f"[FAILURE] Produit {product_id} - Échec après {MAX_RETRIES} tentatives")
            return {
                "status": "error",
                "id_produit_scrapping": product_id,
                "error": error_msg,
            }


async def _process_batch(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Traite un batch de produits en parallèle avec asyncio.gather.
    """
    if not products:
        return []
    
    batch_size = len(products)
    print(f"⚙️  Traitement d'un batch de {batch_size} produit(s)...")
    
    start_time = time.monotonic()
    
    # Créer et exécuter toutes les tâches en parallèle
    tasks = [_process_single_product(product) for product in products]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    
    end_time = time.monotonic()
    duration = end_time - start_time
    
    # Statistiques
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = sum(1 for r in results if r.get("status") == "error")
    
    print(f"🏁 Batch terminé en {duration:.2f}s - Succès: {success_count}, Échecs: {error_count}")
    
    return results


@router.post("/qwen/v2", response_model=BatchOptimResponse)
async def optimizeQwen(payload: BatchOptimRequest):
    """
    Endpoint principal avec traitement par batch optimisé.
    """
    try:
        overall_start_time = time.time()
        total_products = len(payload.products)
        
        print(f"📦 Réception de {total_products} produit(s)")
        
        # Conversion des produits en dict (une seule fois)
        products_data = [product.dict() for product in payload.products]
        
        # Traiter TOUS les produits en parallèle (pas de batchs séquentiels)
        # Le sémaphore contrôle la concurrence
        all_results = await asyncio.gather(
            *[_process_single_product(product) for product in products_data],
            return_exceptions=True
        )
        
        # Formatage de la réponse finale avec gestion des exceptions
        formatted_results = []
        for result in all_results:
            # Gérer les exceptions retournées par gather
            if isinstance(result, Exception):
                formatted_results.append({
                    "id_produit_scrapping": "unknown",
                    "error": f"{type(result).__name__}: {str(result)}"
                })
            elif result and isinstance(result, dict):
                if result.get("status") == "success":
                    formatted_results.append({
                        "id_produit_scrapping": result["id_produit_scrapping"],
                        "success": result.get("data")
                    })
                else:
                    formatted_results.append({
                        "id_produit_scrapping": result["id_produit_scrapping"],
                        "error": result.get("error")
                    })
        
        overall_end_time = time.time()
        total_duration = overall_end_time - overall_start_time
        
        success_total = sum(1 for r in all_results if r.get("status") == "success")
        error_total = sum(1 for r in all_results if r.get("status") == "error")
        
        print(f"✅ Traitement complet terminé en {total_duration:.2f}s")
        print(f"📊 Résultats: {success_total} succès, {error_total} échecs")
        
        return {"data": formatted_results}
    
    except Exception as e:
        error_msg = f"Erreur lors du traitement: {type(e).__name__}: {str(e)}"
        print(f"{error_msg}\nTraceback:\n{traceback.format_exc()}")
        return {"ERROR": error_msg}