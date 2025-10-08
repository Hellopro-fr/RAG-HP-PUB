from fastapi import APIRouter, HTTPException
from app.schemas.optimize.optimize import BatchOptimRequest, BatchOptimResponse
from app.core.optimize.traitement_donnees import TraitementDonnees
from typing import List, Dict, Any
import time
import asyncio
import json
import ast
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

router = APIRouter()

from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest

# --- Configuration ---
BATCH_SIZE = 5
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 0.1

global_traitement_donnees_instance = TraitementDonnees()

# Pool de workers avec event loop persistant
class AsyncWorkerPool:
    def __init__(self, num_workers=10):
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
        self._loop = None
    
    def _worker_loop(self, coro):
        """Exécute la coroutine dans une event loop persistante du worker"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    async def run_async(self, coro):
        """Exécute une coroutine dans le pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._worker_loop, coro)

# Créer un pool global
worker_pool = AsyncWorkerPool(num_workers=10)


async def _call_llm_async(prompt: str) -> str:
    """Appel asynchrone au LLM"""
    chat_request = ChatRequest(prompt=prompt)
    return await llm_client.get_llm_chat_response(chat_request)


async def _process_single_product(product: Dict[str, Any], retry_count: int = 0) -> Dict[str, Any]:
    """
    Traite un seul produit en appelant le LLM.
    """
    product_id = product.get("id_produit_scrapping", "unknown")
    start_time = time.time()
    print(f"[{product_id}] START at {start_time:.3f}")
    
    try:
        # Génération du prompt
        prompt = global_traitement_donnees_instance.generate_prompt(product)
        
        # Appel gRPC via le pool de workers
        response = await worker_pool.run_async(_call_llm_async(prompt))
        
        # Nettoyage de la réponse
        cleaned_response = global_traitement_donnees_instance.clean_json_response(response)
        
        # Parsing JSON
        try:
            parsed_response = json.loads(cleaned_response)
            
            if not parsed_response:
                raise ValueError("LLM n'a pas retourné de résultat")
            
            end_time = time.time()
            duration = end_time - start_time
            print(f"[{product_id}] SUCCESS at {end_time:.3f} (duration: {duration:.3f}s)")
            
            return {
                "status": "success",
                "id_produit_scrapping": product_id,
                "data": parsed_response,
            }
            
        except json.JSONDecodeError:
            raise ValueError(f"Parsing échoué: {cleaned_response[:200]}")
    
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        end_time = time.time()
        duration = end_time - start_time
        print(f"[{product_id}] ERROR at {end_time:.3f} (duration: {duration:.3f}s) - {error_msg}")
        
        # Gestion du retry
        if retry_count < MAX_RETRIES:
            print(f"[RETRY {retry_count + 1}/{MAX_RETRIES}] Produit {product_id}")
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            return await _process_single_product(product, retry_count + 1)
        else:
            return {
                "status": "error",
                "id_produit_scrapping": product_id,
                "error": error_msg,
                "retry_count": retry_count
            }


async def _process_batch(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Traite un batch de produits en parallèle.
    """
    if not products:
        return []
    
    batch_size = len(products)
    print(f"\n⚙️  Traitement d'un batch de {batch_size} produit(s)...")
    
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
    
    print(f"🏁 Batch terminé en {duration:.3f}s - Succès: {success_count}, Échecs: {error_count}\n")
    
    return results


@router.post("/qwen/v2", response_model=BatchOptimResponse)
async def optimizeQwen(payload: BatchOptimRequest):
    """
    Endpoint principal qui reçoit un batch de produits et les traite par lots.
    """
    try:
        overall_start_time = time.time()
        total_products = len(payload.products)
        
        print(f"\n{'='*60}")
        print(f"📦 Réception de {total_products} produit(s)")
        print(f"{'='*60}")
        
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
        
        print(f"{'='*60}")
        print(f"✅ Traitement complet terminé en {total_duration:.3f}s")
        print(f"📊 Résultats: {success_total} succès, {error_total} échecs sur {total_products} produits")
        print(f"{'='*60}\n")
        
        return {"data": formatted_results}
    
    except Exception as e:
        error_msg = f"Erreur lors du traitement: {type(e).__name__}: {str(e)}"
        print(f"❌ ERREUR CRITIQUE: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)