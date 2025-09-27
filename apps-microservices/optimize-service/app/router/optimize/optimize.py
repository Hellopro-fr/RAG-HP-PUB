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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Import des clients gRPC de notre architecture
from common_utils.grpc_clients import (
    llm_client,
)

from common_utils.grpc_clients.schemas.chat import ChatRequest


@router.post("/openai", response_model=OptimResponse)
def optimize(request: OptimRequest):
    try:
        optimizing_service = ProductOptimizer(OPENAI_API_KEY)
        optimize = optimizing_service.optimize_product(request.dict())

        print(optimize)

        return {"data": [optimize]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/qwen/v2", response_model=BatchOptimResponse)
async def optimizeQwen(payload: BatchOptimRequest):
    try:
        start_time = time.time()
        print(f"Reception de {len(payload.products)} produits")

        instancetraitement = TraitementDonnees()
        results = []
        
        products_data = [product.dict() for product in payload.products]

        for product in products_data:
            try:
                prompt = instancetraitement.generate_prompt(product)
        
                chat_request = ChatRequest(prompt=prompt)

                response = await llm_client.get_llm_chat_response(chat_request)

                response = instancetraitement.clean_json_response(response)

                try:
                    parsed_response = json.loads(response)
                    if not parsed_response:
                        print("LLM n'a pas retourné de résultat")
                        results.append({
                            "id_produit_scrapping": product["id_produit_scrapping"],
                            "error": "LLM n'a pas retourné de résultat"
                        })
                    else:
                        print("tentative de parsing reussie")
                        results.append({
                            "id_produit_scrapping": product["id_produit_scrapping"],
                            "success": parsed_response
                        })

                except json.JSONDecodeError:
                    try:
                        parsed_response = ast.literal_eval(response)
                    except Exception:
                        print("tentative de parsing échouée")
                        print(response)
                        results.append({
                            "id_produit_scrapping": product["id_produit_scrapping"],
                            "error": f"Tentative de parsing échouée: {response}"
                        })

            except Exception as e:
                print(f"Erreur lors du traitement du produit {product['id_produit_scrapping']}: {str(e)}")
                results.append({
                    "id_produit_scrapping": product["id_produit_scrapping"],
                    "error": f"Erreur lors du traitement: {type(e).__name__}: {str(e)}"
                })

        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"Fin traitement en {processing_time:.2f} secondes")
        return {"data": results}

    except Exception as e:
        error_msg = f"Erreur lors du traitement: {type(e).__name__}: {str(e)}"
        debug_msg = f"{error_msg}\nTraceback:\n{traceback.format_exc()}"
        response_error = {
            "ERROR": error_msg
        }
        print(debug_msg)
        return response_error