import logging
import time
from fastapi import FastAPI, Request, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from google.protobuf.json_format import MessageToDict
from typing import List, Optional

# Import des clients gRPC
from common_utils.grpc_clients import (
    embedding_client,
    database_client,
    llm_client,
    reranking_client,
)
from common_utils.grpc_clients.schemas.chat import ChatRequest
from common_utils.grpc_clients.embedding_client import get_embeddings, get_embedding

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="API de Test pour Microservices IA",
    description="Cette API sert de point d'entrée pour tester les services gRPC sous-jacents.",
)

templates = Jinja2Templates(directory="app/templates")


class TextInput(BaseModel):
    input: str


class MultiTextInput(BaseModel):
    inputs: List[str]


# --- Endpoints ---


@app.post("/embedding")
async def create_embedding(data: MultiTextInput):
    # TODO: Sécuriser cet endpoint (authentification, validation)
    embedding_vector = await embedding_client.get_embeddings(data.input)
    return {"output": embedding_vector}


@app.get("/database/search")
async def search_database(
    query: str,
    source: str = Query(..., description="Nom de la collection Milvus"),
    k: int = 5,
    filter: Optional[str] = Query(
        None, description="Filtre Milvus, ex: 'category == \"tech\"'"
    ),
    # NOUVEAU: Paramètre pour activer le reranking
    rerank: bool = Query(
        False, description="Activer le reranking pour améliorer la pertinence"
    ),
):
    # --- Étape 1: Génération de l'embedding pour la requête (commun aux deux cas) ---
    logging.info(
        f"Recherche pour '{query}' dans '{source}'. Reranking activé: {rerank}"
    )
    start_embed = time.perf_counter()
    query_vector = await get_embedding(query)
    embed_duration = time.perf_counter() - start_embed
    logging.info(
        f"Temps d'embedding : {round(embed_duration, 2)}"
    )

    if not query_vector:
        return {"error": "Impossible de générer l'embedding pour la requête."}

    # --- Étape 2: Logique conditionnelle pour le reranking ---
    top_k = k
    if rerank:
        top_k = k*2
    logging.info(
        f"Phase 1 (Retrieve): Récupération des {k} - {top_k} meilleurs candidats de Milvus."
    )
    start_recuperation = time.perf_counter()
    search_results_proto = await database_client.search_vector(
        source, query_vector, top_k, filter_expr=filter
    )
    logging.info(
        f"Temps de récupération : {round((time.perf_counter() - start_recuperation), 2)}"
    )
    if search_results_proto is None:
        return {"error": "Erreur lors de la recherche dans la base de données."}
    
    results_list = [MessageToDict(res) for res in search_results_proto]
    
    if rerank:
        # Préparation des données pour le reranker.
        # HYPOTHÈSE CRUCIALE: Le texte du document est stocké dans metadata sous la clé 'text'.
        # Adaptez cette clé si votre schéma Milvus est différent.
        docs_to_rerank = []
        result_map = {}
        start_get_texte = time.perf_counter()
        for res in results_list:
            doc_text = res.get("metadata", {}).get('entity', {}).get("text")
            if doc_text:
                docs_to_rerank.append(doc_text)
                # On mappe le texte à son résultat complet pour pouvoir le reconstruire après
                result_map[doc_text] = res
        logging.info(
            f"Temps de récupération : {round((time.perf_counter() - start_get_texte), 2)}"
        )
        if not docs_to_rerank:
            logging.warning(
                "Reranking demandé mais aucun champ 'text' trouvé dans les métadonnées des résultats."
            )
            return {"results": results_list[:k]}

        logging.info(
            f"Phase 2 (Rerank): Envoi de {len(docs_to_rerank)} documents au service de reranking."
        )
        start_reranking = time.perf_counter()
        ranked_texts = await reranking_client.rerank_documents(query, docs_to_rerank)
        logging.info(
            f"Temps de reranking : {round((time.perf_counter() - start_reranking), 2)}"
        )
        # Reconstruction de la liste de résultats dans le nouvel ordre
        start_reconstruction = time.perf_counter()
        final_results = [
            result_map[text] for text in ranked_texts if text in result_map
        ]
        logging.info(
            f"Temps de reconstruction : {round((time.perf_counter() - start_reconstruction), 2)}"
        )

        # On retourne le top k final
        return {"results": final_results[:k]}
    return {"results": results_list}


@app.post("/llm/chat/stream")
async def llm_chat_endpoint(data: TextInput):
    # TODO: Sécuriser cet endpoint
    # Retourne une réponse en streaming
    return StreamingResponse(
        llm_client.stream_llm_chat(data.input), media_type="text/event-stream"
    )

@app.post("/llm/chat")
async def llm_chat_endpoint(data: ChatRequest):
    # Utilise le nouveau client partagé non-streamé
    response_message = await llm_client.get_llm_chat_response(data)
    return {"response": response_message}

@app.get("/recherche.html", response_class=HTMLResponse)
async def get_test_page(request: Request):
    return templates.TemplateResponse("recherche.html", {"request": request})


@app.get("/")
def read_root():
    return {
        "message": "API de test pour les microservices IA. Accédez à /recherche.html pour l'interface de test."
    }
