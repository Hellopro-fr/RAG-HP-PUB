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

# --- START METRICS IMPORTS ---
from common_utils.metrics.prometheus import PROCESSING_TIME_SECONDS
# --- END METRICS IMPORTS ---

router = APIRouter()


# Import des clients gRPC de notre architecture
from common_utils.grpc_clients import (
    llm_client,
)

from common_utils.grpc_clients.schemas.chat import ChatRequest


@router.post("/qwen/v2", response_model=BatchOptimResponse)
async def optimizeQwen(payload: BatchOptimRequest):
    # --- MANUAL INSTRUMENTATION START ---
    start_time_manual = time.monotonic()
    metric_status = 'success'
    # --- END MANUAL INSTRUMENTATION START ---
    try:
        start_time = time.time()
        print(f"Reception de {len(payload.products)} produits")

        instancetraitement = TraitementDonnees()

        products_data = [product.dict() for product in payload.products]

        # Fonction async pour traiter un produit
        async def process_product(product):
            try:
                prompt = instancetraitement.generate_prompt(product)

                chat_request = ChatRequest(prompt=prompt, temperature=0.4)

                response = await llm_client.get_llm_chat_response(chat_request)

                print(f"Réponse brute LLM: {response}")

                # Extraction du contenu JSON depuis la nouvelle structure
                if isinstance(response, dict) and 'full_message' in response:
                    llm_content = response['full_message']
                    usage = response.get('response', {}).get('usage', {})
                    model = response.get('response', {}).get('model')
                    llm_usage_info = {
                        "prompt_tokens": usage.get('prompt_tokens'),
                        "completion_tokens": usage.get('completion_tokens'),
                        "total_tokens": usage.get('total_tokens'),
                        "model": model
                    }

                llm_content = instancetraitement.clean_json_response(llm_content)

                try:
                    parsed_response = json.loads(llm_content)
                    if not parsed_response:
                        print("LLM n'a pas retourné de résultat")
                        return {
                            "id_produit_scrapping": product["id_produit_scrapping"],
                            "error": "LLM n'a pas retourné de résultat",
                            "info": llm_usage_info
                        }
                    else:
                        print("tentative de parsing reussie")
                        print(parsed_response)
                        return {
                            "id_produit_scrapping": product["id_produit_scrapping"],
                            "success": parsed_response,
                            "info": llm_usage_info
                        }

                except json.JSONDecodeError:
                    try:
                        parsed_response = ast.literal_eval(llm_content)
                        return {
                            "id_produit_scrapping": product["id_produit_scrapping"],
                            "success": parsed_response,
                            "info": llm_usage_info
                        }
                    except Exception:
                        print("tentative de parsing échouée")
                        print(llm_content)
                        return {
                            "id_produit_scrapping": product["id_produit_scrapping"],
                            "error": f"Tentative de parsing échouée: {llm_content}",
                            "info": llm_usage_info
                        }

            except Exception as e:
                print(f"Erreur lors du traitement du produit {product['id_produit_scrapping']}: {str(e)}")
                return {
                    "id_produit_scrapping": product["id_produit_scrapping"],
                    "error": f"Erreur lors du traitement: {type(e).__name__}: {str(e)}",
                    "info": {
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "model": None
                    }
                }

        # Traitement parallèle de tous les produits
        results = await asyncio.gather(*[process_product(product) for product in products_data])

        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"Fin traitement en {processing_time:.2f} secondes")
        print (f"Résultats: {results}")
        print(f"lots traité, taille results: {len(results)}")
        return {"data": results}

    except Exception as e:
        metric_status = 'failure'
        error_msg = f"Erreur lors du traitement: {type(e).__name__}: {str(e)}"
        debug_msg = f"{error_msg}\nTraceback:\n{traceback.format_exc()}"
        response_error = {
            "ERROR": error_msg
        }
        print(debug_msg)
        return response_error
    finally:
        # --- MANUAL INSTRUMENTATION FINALIZATION ---
        duration = time.monotonic() - start_time_manual
        num_products = len(payload.products)
        collection_type = 'product_title_optimization'

        if num_products == 0:
             PROCESSING_TIME_SECONDS.labels(
                service_name="optimize-service", 
                status=metric_status, 
                collection_type='empty_batch'
            ).observe(duration)
        else:
            metric = PROCESSING_TIME_SECONDS.labels(
                service_name="optimize-service",
                status=metric_status,
                collection_type=collection_type
            )
            # Observe the full duration once to increment the sum correctly
            metric.observe(duration)
            # Observe a zero duration for the rest of the items to increment the count correctly
            if num_products > 1:
                for _ in range(num_products - 1):
                    metric.observe(0)