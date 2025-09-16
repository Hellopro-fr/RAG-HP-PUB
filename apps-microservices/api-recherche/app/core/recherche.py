from functools import lru_cache
import time
import logging
import asyncio
from typing import List

# Import des clients gRPC de notre architecture
from app.grpc_clients import (
    embedding_client,
    database_client,
    llm_client,
    reranking_client,
)
from pymilvus import DataType, Collection

# Import des schémas Pydantic (à adapter si les chemins ont changé)
from app.schemas.search import SearchRequestWs as SearchRequest
from app.core.credentials import settings, model_settings
from openai import OpenAI

class DeepSeek:
	def __init__(self, config=None):
		config = config or {}
		self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
		self.BASE_URL = "https://api.deepseek.com"
		self.MODEL = "deepseek-chat"
		self.TEMPERATURE = 0.4
		self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

	def chat(self, message, stream=False):
		response = self.client.chat.completions.create(
			model=self.MODEL,
			messages=[
				{"role": "system", "content": "Tu es un assistant intelligent et serviable."},
				{"role": "user", "content": message},
			],
			temperature=self.TEMPERATURE,
			stream=stream
		)
		if stream:
			return response
		return {"content": response.choices[0].message.content, "response": response}

	def set_temperature(self, temperature):
		self.TEMPERATURE = float(temperature)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@lru_cache(maxsize=32)
def get_field_type_map(collection_name: str) -> dict:
    """
    Retrieves the schema for a given collection and returns a dictionary
    mapping field names to their pymilvus DataType.
    """
    try:
        collection = Collection(name=collection_name)
        return {field.name: field.dtype for field in collection.schema.fields}
    except Exception as e:
        logger.error(f"Could not retrieve schema for collection '{collection_name}': {e}")
        return {}

def filtre_source (filtre: dict, source: str = "") -> list:
    clauses = []
    field_types = get_field_type_map(source)
    NUMERIC_DTYPES = {DataType.INT8, DataType.INT16, DataType.INT32, DataType.INT64, DataType.FLOAT, DataType.DOUBLE}
    for key, val in filtre.items():
        dtype = field_types.get(key)
        if key == 'id_categorie' and source == 'produits':
            key = 'categorie'
        elif key == 'id_categorie' and source == 'siteweb':
            continue
        
        if not dtype:
            logger.info(f"dtype none {key}")
            continue
        
        if dtype == DataType.ARRAY:
            if isinstance(val, list):
                sub_clauses = [f"array_contains({key}, {repr(str(v))})" for v in val]
                if sub_clauses:
                    clauses.append(f"({' or '.join(sub_clauses)})")
            else:
                clauses.append(f"array_contains({key}, {repr(str(val))})")
                
        elif dtype in NUMERIC_DTYPES:
            if isinstance(val, dict):
                if 'operator' in val and 'values' in val:
                    operator = val['operator']
                    values = val['values'] 
                    if operator == 'entre' and isinstance(values, dict) and 'start' in values and 'end' in values:
                        start_val = values['start']
                        end_val = values['end']
                        clauses.append(f"{key} >= {start_val} and {key} <= {end_val}")
                    else:
                        actual_value = next(iter(values.values()))
                        clauses.append(f"{key} {operator} {actual_value}")
            elif isinstance(val, list):
                numeric_vals = [int(v) if dtype in {DataType.INT8, DataType.INT16, DataType.INT32, DataType.INT64} else float(v) for v in val]
                clauses.append(f"{key} in {numeric_vals}")
            else:
                # Format as: field_name == 123
                numeric_val = int(val) if dtype in {DataType.INT8, DataType.INT16, DataType.INT32, DataType.INT64} else float(val)
                clauses.append(f"{key} == {numeric_val}")
        else:
            if isinstance(val, dict):
                if 'operator' in val and 'values' in val:
                    operator = val['operator']
                    values = val['values'] 
                    if operator == 'entre' and isinstance(values, dict) and 'start' in values and 'end' in values:
                        start_val = values['start']
                        end_val = values['end']
                        clauses.append(f"{key} >= {start_val} and {key} <= {end_val}")
                    else:
                        actual_value = next(iter(values.values()))
                        clauses.append(f"{key} {operator} {actual_value}")
            elif isinstance(val, list):
                # Format as: field_name in ["val1", "val2"]
                quoted_vals = [repr(str(v)) for v in val]
                clauses.append(f"{key} in [{', '.join(quoted_vals)}]")
            else:
                # Format as: field_name == "value"
                clauses.append(f"{key} == {repr(str(val))}")
    return clauses

async def search_in_milvus_stream(request: SearchRequest):
    """
    Orchestre le flux de recherche en appelant les microservices gRPC dédiés.
    Cette fonction est maintenant un pur orchestrateur, sans logique d'inférence.
    """
    start_total_time = time.perf_counter()
    
    try:
        # --- ÉTAPE 1: EMBEDDING ---
        yield {"type": "status", "payload": "Génération de l'embedding pour la requête..."}
        start_embed = time.perf_counter()
        
        # Appel au microservice d'embedding
        query_vector = await embedding_client.get_embedding(request.prompt)
        
        embed_duration = time.perf_counter() - start_embed
        if not query_vector:
            yield {"type": "error", "payload": "Impossible de générer l'embedding pour la requête."}
            return
        yield {"type": "embedding_complete", "payload": {"duration": round(embed_duration, 2)}}

        # --- ÉTAPE 2: RÉCUPÉRATION (VECTOR SEARCH) ---
        top_k_final = int(request.top_k)
        # On récupère plus de documents si le reranking est activé
        top_k_retrieval = top_k_final * 2 if request.options.use_reranker else top_k_final
        
        # NOTE: La logique de filtrage complexe (filtre_source) doit maintenant être gérée
        # soit ici (pour construire la chaîne `filter_expr`), soit déléguée au service de recherche.
        # Pour l'instant, nous supposons un filtre simple.
        # filter_expr = " and ".join(request.filtre) if request.filtre else ""

        all_source_results = []
        search_duration = 0

        # Boucle sur les sources demandées
        for item in request.source:
            source_name = item.source
            filtre = item.filtre
            yield {"type": "status", "payload": f"Recherche dans la source '{source_name}'..."}
            start_search_source = time.perf_counter()

            filters = []
            filter_expr = filtre_source(request.filtre, source_name)
            if filter_expr:
                filters.append(" and ".join(filter_expr))
            
            filter_expr_source = filtre_source(filtre, source_name) if filtre else ""
            if filter_expr_source:
                filters.append(" and ".join(filter_expr_source))

            # Appel au microservice de recherche en base de données
            # Le client gRPC gère la conversion en dictionnaire
            source_results = await database_client.search_vector_and_convert(
                collection=source_name,
                vector=query_vector,
                k=top_k_retrieval,
                filter_expr=filter_expr # Le filtre est passé directement
            )
            
            search_duration += time.perf_counter() - start_search_source
            
            if source_results is None:
                yield {"type": "warning", "payload": f"Erreur lors de la recherche dans la source '{source_name}'."}
                continue
            
            all_source_results.extend(source_results)

        # On trie tous les résultats par score de similarité initial
        initial_matches = sorted(all_source_results, key=lambda x: x.get('score', 0.0), reverse=True)
        
        # Envoi des résultats initiaux (avant reranking)
        yield {"type": "initial_results", "payload": {"results": initial_matches[:top_k_final], "duration": round(search_duration, 2)}}

        # --- ÉTAPE 3: RERANKING (Optionnel) ---
        final_results = initial_matches
        rerank_duration = 0
        if request.options.use_reranker and initial_matches:
            yield {"type": "status", "payload": "Reclassement (reranking) des résultats..."}
            start_rerank_time = time.perf_counter()

            # Préparation des documents pour le reranker
            # HYPOTHÈSE: Le texte est dans metadata.text
            docs_to_rerank = [res.get("metadata", {}).get("text", "") for res in initial_matches]
            
            # Appel au microservice de reranking
            ranked_texts = await reranking_client.rerank_documents(request.prompt, docs_to_rerank)
            
            # Reconstruction de la liste de résultats dans le nouvel ordre
            result_map = {res.get("metadata", {}).get("text", ""): res for res in initial_matches}
            final_results = [result_map[text] for text in ranked_texts if text in result_map]
            
            rerank_duration = time.perf_counter() - start_rerank_time
            yield {"type": "rerank_complete", "payload": {"results": final_results[:top_k_final], "duration": round(rerank_duration, 2)}}
        
        # --- ÉTAPE 4: GÉNÉRATION LLM (Optionnel) ---
        llm_duration = 0
        if request.action == 2 and final_results:
            yield {"type": "status", "payload": f"Génération de la réponse avec le LLM..."}
            
            # Préparation du contexte pour le LLM
            context_texts = [res.get("metadata", {}).get("text", "") for res in final_results[:top_k_final]]
            context = "\n-----\n".join(context_texts)
            full_user_prompt = f"Contexte:\n{context}\n\nQuestion:\n{request.prompt}" # Template simplifié

            yield {"type": "llm_start"}
            start_llm_time = time.perf_counter()
            
            # Appel au microservice LLM en streaming
            async for token in llm_client.stream_llm_chat(full_user_prompt):
                yield {"type": "llm_chunk", "payload": token}
            
            llm_duration = time.perf_counter() - start_llm_time

        # --- FIN DU FLUX ---
        total_duration = time.perf_counter() - start_total_time
        final_summary = {
            "timings": {
                "embedding": round(embed_duration, 2),
                "vector_search": round(search_duration, 2),
                "rerank": round(rerank_duration, 2),
                "llm_execution": round(llm_duration, 2),
                "total_process": round(total_duration, 2),
            },
            "result_count": len(final_results[:top_k_final])
        }
        yield {"type": "end_of_stream", "payload": final_summary}

    except Exception as e:
        logger.error(f"Une erreur majeure est survenue dans le flux de recherche: {e}", exc_info=True)
        yield {"type": "error", "payload": f"Erreur serveur: {e}"}
    finally:
        # Le nettoyage de la mémoire GPU n'est plus nécessaire ici,
        # car il est géré par les microservices dédiés.
        logger.info("Flux de recherche terminé.")