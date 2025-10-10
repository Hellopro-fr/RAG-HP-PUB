from functools import lru_cache
import time
import logging
import asyncio
from typing import List
from unittest import result
from google.protobuf.json_format import MessageToDict

# Import des clients gRPC de notre architecture
from common_utils.grpc_clients import (
    embedding_client,
    database_client,
    llm_client,
    reranking_client,
)
from pymilvus import DataType, Collection

# Import des schémas Pydantic (à adapter si les chemins ont changé)
from app.schemas.search import LLMPipeline, SearchReponse, SearchRequestWs as SearchRequest, SearchResponse
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

@lru_cache(maxsize=None)
def get_openai_client():
    logger.info("Initialisation du client OpenAI...")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    logger.info("Client OpenAI initialisé.")
    return client

def llm_prompt_stream(request: SearchRequest, context_texts):
    """
    Génère une réponse LLM en streaming et yield chaque token.
    """
    context = "\n-----\n\n\n".join(context_texts)
    try:
        full_user_prompt = request.llm.template_prompt.format(chunks=context, recherche=request.prompt)
    except Exception as e:
        error_message = f"Erreur de formatage du prompt : la clé '{e}' est manquante ou le format est invalide.\nMerci de doubler les accolades dans le prompt à part {{chunks}} et {{recherche}} : {{{{'key_1': 'value_1', 'key_2': 'value_2'}}}}"
        logger.error(error_message)
        # On envoie un message d'erreur clair via le WebSocket
        yield {"type": "error", "payload": error_message}
        return
    
    type_prompt = next((key for key, values in model_settings.items() if request.llm.chat_model in values), "openai")

    try:
        if type_prompt == "openai":
            if request.llm.chat_model == "deepseek":
                deepseek = DeepSeek()
                deepseek.set_temperature(request.llm.temperature)
                stream = deepseek.chat(full_user_prompt, stream=True)
            else:
                openai_client = get_openai_client()
                stream = openai_client.chat.completions.create(
                    model=request.llm.chat_model,
                    messages=[{"role": "user", "content": full_user_prompt}],
                    temperature=float(request.llm.temperature),
                    stream=True
                )
        else: # OpenRouter
            client_or = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )
            stream = client_or.chat.completions.create(
                model=request.llm.chat_model,
                messages=[{"role": "user", "content": full_user_prompt}],
                temperature=float(request.llm.temperature),
                stream=True
            )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    except Exception as e:
        logger.error(f"Erreur durant le streaming LLM: {e}")
        yield f"\n\n--- ERREUR --- \n{e}"
        
def llm_prompt(request: SearchRequest, context_texts) -> LLMPipeline:
    llm_response, full_user_prompt, llm_duration, context = "", "", 0, ""
    completion = {}
    if request.action == 2 and context_texts:
        context = "\n-----\n\n\n".join(context_texts)
        # full_user_prompt = request.llm.template_prompt.format(chunks=context, recherche=request.prompt)
        try:
            full_user_prompt = request.llm.template_prompt.format(chunks=context, recherche=request.prompt)
        except (KeyError, ValueError) as e:
            error_message = f"Erreur de formatage du prompt : la clé '{e}' est manquante ou le format est invalide.\nMerci de doubler les accolades dans le prompt à part {{chunks}} et {{recherche}} : {{{{'key_1': 'value_1', 'key_2': 'value_2'}}}}"
            logger.error(error_message)
            # On retourne un objet LLMPipeline avec le message d'erreur
            return LLMPipeline(llm_response=error_message, context=context,error=True)
        
        type_prompt = next((key for key, values in model_settings.items() if request.llm.chat_model in values), "openai")
            
        start_llm_time = time.perf_counter()
        if type_prompt == "openai":
            if request.llm.chat_model == "deepseek":
                deepseek = DeepSeek()
                deepseek.set_temperature(request.llm.temperature)
                response = deepseek.chat(full_user_prompt)
                llm_response = response['content']
                completion = response["response"]
            else:
                openai_client = get_openai_client()
                completion = openai_client.chat.completions.create(
                    model=request.llm.chat_model,
                    messages=[{"role": "user", "content": full_user_prompt}],
                    temperature=float(request.llm.temperature)
                )
                llm_response = completion.choices[0].message.content
            completion = completion.model_dump()
        else:
            client_or = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )
            completion = client_or.chat.completions.create(
                extra_body={},
                model=request.llm.chat_model,
                temperature=float(request.llm.temperature),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": full_user_prompt
                            }
                        ]
                    }
                ]
            )
            llm_response = completion.choices[0].message.content
            completion = completion.model_dump()
            
        llm_duration = time.perf_counter() - start_llm_time
    return LLMPipeline(llm_duration=llm_duration,llm_response=llm_response,full_user_prompt=full_user_prompt,context=context,response=completion)

async def filtre_source (filtre: dict, source: str = "") -> list:
    clauses = []
    field_types = await database_client.get_collection_schema(source)
    if not field_types:
        logger.warning(f"Impossible de récupérer le schéma pour la collection '{source}'. Le filtrage sera ignoré pour cette source.")
        return []
    NUMERIC_DTYPES = {
        DataType.INT8.value, DataType.INT16.value, DataType.INT32.value, 
        DataType.INT64.value, DataType.FLOAT.value, DataType.DOUBLE.value
    }
    logger.info(f"numeric_dtypes : {NUMERIC_DTYPES}")
    for key, val in filtre.items():
        dtype = field_types.get(key)
        if isinstance(dtype, DataType):
            # Si oui, on extrait sa valeur entière (ex: 5)
            dtype = dtype.value
        else:
            # Sinon (c'est un string comme 'VARCHAR' ou None), on l'utilise directement
            dtype = dtype
        if key == 'id_categorie' and source == 'produits':
            key = 'categorie'
        elif key == 'id_categorie' and source == 'siteweb':
            continue
        
        if not dtype:
            logger.info(f"dtype none {key}")
            continue
        
        logger.info(f'dtype {key} : {dtype}, val : {val}')
        
        if dtype == DataType.ARRAY:
            if isinstance(val, list):
                sub_clauses = [f"array_contains({key}, {repr(str(v))})" for v in val]
                if sub_clauses:
                    clauses.append(f"({' or '.join(sub_clauses)})")
            else:
                clauses.append(f"array_contains({key}, {repr(str(val))})")
                
        elif dtype in NUMERIC_DTYPES:
            logger.info(f"numeric {key} : {dtype}, val : {val}")
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
                if key == 'id_categorie' and source == 'devis':
                    logger.info("forcer numéric pour id_categorie dans devis")
                    numeric_vals = [int(v) for v in val]
                    clauses.append(f"{key} in {numeric_vals}")
                    continue
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
        # logger.info(f'embedding : {query_vector}')
        yield {"type": "embedding_complete", "payload": {"duration": round(embed_duration, 2)}}

        # --- ÉTAPE 2: RÉCUPÉRATION (VECTOR SEARCH) ---
        top_k_final = int(request.top_k)
        # On récupère plus de documents si le reranking est activé
        top_k_retrieval = top_k_final * 2 if request.options.use_reranker else top_k_final
        
        all_source_results = []
        start_search_time = time.perf_counter()
        
        search_tasks = []
        for item in request.source:
            source_name = item.source
            filtre = item.filtre
            yield {"type": "status", "payload": f"Préparation de la recherche pour '{source_name}'..."}

            # Fonction interne pour créer la coroutine de recherche avec le bon contexte
            async def create_search_task(s_name=source_name, s_filtre=filtre):
                filters = []
                filter_expr_global = await filtre_source(request.filtre, s_name)
                if filter_expr_global:
                    filters.append(" and ".join(filter_expr_global))
                
                filter_expr_source = await filtre_source(s_filtre, s_name) if s_filtre else ""
                if filter_expr_source:
                    filters.append(" and ".join(filter_expr_source))
                
                final_filter_expr = " and ".join(filters) if filters else ""

                # Retourne la coroutine de recherche prête à être exécutée
                return await database_client.search_vector(
                    collection=s_name,
                    vector=query_vector,
                    k=top_k_retrieval,
                    filter_expr=final_filter_expr
                )

            search_tasks.append(create_search_task())

        # Exécuter toutes les tâches de recherche en parallèle
        yield {"type": "status", "payload": f"Lancement de la recherche parallèle sur {len(search_tasks)} source(s)..."}
        # asyncio.gather exécute toutes les coroutines en même temps et attend leurs résultats
        list_of_results_groups = await asyncio.gather(*search_tasks, return_exceptions=True)
        search_duration = time.perf_counter() - start_search_time

        # Aplatir la liste de listes de résultats et gérer les erreurs
        for source_results in list_of_results_groups:
            if isinstance(source_results, Exception):
                logging.error(f"Une tâche de recherche a échoué: {source_results}")
                continue
            if source_results:
                all_source_results.extend([MessageToDict(res) for res in source_results])

        # On trie tous les résultats par score de similarité initial
        initial_matches = sorted(all_source_results, key=lambda x: x['score'], reverse=True)
        
        # Envoi des résultats initiaux (avant reranking)
        yield {"type": "initial_results", "payload": {"results": initial_matches[:top_k_final], "duration": round(search_duration, 2)}}

        # --- ÉTAPE 3: RERANKING (Optionnel) ---
        final_results = initial_matches
        rerank_duration = 0
        if request.options.use_reranker and initial_matches:
            yield {"type": "status", "payload": "Reclassement (reranking) des résultats..."}
            start_rerank_time = time.perf_counter()

            # Préparation optimisée pour le reranker
            docs_to_rerank = []
            # Créer une map pour reconstruire les résultats après le reranking
            result_map = {}
            for res in initial_matches:
                # On s'assure que le texte existe et n'est pas déjà dans la map (cas de doublons)
                doc_text = res.get('metadata', {}).get('entity', {}).get('text')
                if doc_text and doc_text not in result_map:
                    docs_to_rerank.append(doc_text)
                    result_map[doc_text] = res

            if not docs_to_rerank:
                yield {"type": "status", "payload": "Reranking annulé: aucun texte trouvé dans les résultats."}
            else:
                yield {"type": "status", "payload": f"Reclassement de {len(docs_to_rerank)} documents..."}
                start_rerank_time = time.perf_counter()

                # Appel au microservice avec une charge utile minimale
                ranked_texts = await reranking_client.rerank_documents(request.prompt, docs_to_rerank)
                
                # Reconstruction de la liste de résultats dans le nouvel ordre
                final_results = [result_map[text] for text in ranked_texts if text in result_map]
                
                rerank_duration = time.perf_counter() - start_rerank_time
                yield {"type": "rerank_complete", "payload": {"results": final_results[:top_k_final], "duration": round(rerank_duration, 2)}}
        
        # --- ÉTAPE 4: GÉNÉRATION LLM (Optionnel) ---
        llm_duration = 0
        if request.action == 2 and final_results:
            yield {"type": "status", "payload": f"Génération de la réponse avec le LLM..."}
            
            # Préparation du contexte pour le LLM
            context_texts = [res['metadata']['entity']['text'] for res in final_results[:top_k_final]]
            context = "\n-----\n".join(context_texts)
            full_user_prompt = f"Contexte:\n{context}\n\nQuestion:\n{request.prompt}" # Template simplifié

            yield {"type": "llm_start"}
            start_llm_time = time.perf_counter()
            
            # Appel au microservice LLM en streaming
            # token_generator = await asyncio.to_thread(llm_prompt_stream, request, context_texts)
            token_generator = await asyncio.to_thread(llm_prompt, request, context_texts)
            # token_generator = llm_prompt(request, context_texts)
            yield {"type": "llm_chunk" if not token_generator.error else "error", "payload": token_generator.llm_response, "llm_response": token_generator.response}
            
            # for token in token_generator:
            #     yield {"type": "llm_chunk", "payload": token}
            
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
        
        
# ... (le reste de vos imports et fonctions reste inchangé) ...

async def search_in_milvus(request: SearchRequest) -> dict:
    """
    Orchestre une recherche complète en utilisant les microservices gRPC,
    et retourne un dictionnaire structuré comme l'implémentation originale.
    """
    logger.info(f"[gRPC] Recherche (non-stream): prompt='{request.prompt[:50]}...', sources={[s.source for s in request.source]}")
    start_total_time = time.perf_counter()

    # Initialisation des variables pour le dictionnaire de retour
    embed_duration, search_duration, rerank_duration, llm_duration = 0, 0, 0, 0
    llm_response_content = ""
    context = ""
    full_user_prompt = ""
    final_filter_expr_str = "" # Pour stocker une représentation du filtre appliqué
    llm_req = LLMPipeline(llm_response="", context="", full_user_prompt="", response={})
    
    try:
        # --- ÉTAPE 1: EMBEDDING ---
        start_embed = time.perf_counter()
        query_vector = await embedding_client.get_embedding(request.prompt)
        embed_duration = time.perf_counter() - start_embed
        if not query_vector:
            raise ValueError("Impossible de générer l'embedding pour la requête.")

        # --- ÉTAPE 2: RÉCUPÉRATION (VECTOR SEARCH) ---
        start_search = time.perf_counter()
        top_k_final = int(request.top_k)
        top_k_retrieval = top_k_final * 2 if request.options.use_reranker else top_k_final
        
        all_results = {} # Dictionnaire pour stocker les résultats par source, comme l'original

        # Boucle sur les sources demandées
        for item in request.source:
            source_name = item.source
            filtre = item.filtre

            # Construction de l'expression de filtre
            filters = []
            filter_expr_global = await filtre_source(request.filtre, source_name)
            if filter_expr_global:
                filters.append(" and ".join(filter_expr_global))
            
            filter_expr_source = await filtre_source(filtre, source_name) if filtre else []
            if filter_expr_source:
                filters.append(" and ".join(filter_expr_source))
            
            final_filter_expr = " and ".join(filters) if filters else ""
            final_filter_expr_str = final_filter_expr # Sauvegarde pour le retour

            logger.info(f"Recherche dans '{source_name}' avec le filtre: {final_filter_expr}")

            # Appel au microservice de base de données
            source_results = await database_client.search_vector(
                collection=source_name,
                vector=query_vector,
                k=top_k_retrieval,
                filter_expr=final_filter_expr
            )
            
            all_results[source_name] = [MessageToDict(res) for res in source_results]
        
        search_duration = time.perf_counter() - start_search
        # logger.info(f"all results : {all_results}")
        # --- ÉTAPE 3: RERANKING (Optionnel, par source comme l'original) ---
        if request.options.use_reranker and all_results:
            
            docs_to_rerank = []
            result_map = {}
            start_get_texte = time.perf_counter()
            
            logger.info("Début du reranking...")
            start_rerank_time = time.perf_counter()
            reranked_results_by_source = {}

            for source, matches in all_results.items():
                # Préparation des documents pour le reranker pour cette source
                docs_to_rerank = [match['metadata']['entity']['text'] for match in matches]
                
                # Appel au microservice de reranking
                logging.info(
                    f"Phase 2 (Rerank): Envoi de {len(docs_to_rerank)} documents au service de reranking."
                )
                start_reranking = time.perf_counter()
                ranked_texts = await reranking_client.rerank_documents(request.prompt, docs_to_rerank)
                logging.info(
                    f"Temps de reranking : {round((time.perf_counter() - start_reranking), 2)}"
                )
                # Reconstruction de la liste de résultats dans le nouvel ordre
                result_map = {res['metadata']['entity']['text']: res for res in matches}
                start_reconstruction = time.perf_counter()
                reranked_results_by_source[source] = [
                    result_map[text] for text in ranked_texts if text in result_map
                ]
                reranked_results_by_source[source] = reranked_results_by_source[source][:top_k_final]
                logging.info(
                    f"Temps de reconstruction : {round((time.perf_counter() - start_reconstruction), 2)}"
                )

            all_results = reranked_results_by_source
            rerank_duration = time.perf_counter() - start_rerank_time
            logger.info(f"Reranking terminé en {rerank_duration:.2f}s.")
        else:
            # Si pas de reranker, on tronque simplement les résultats de chaque source
            for source, matches in all_results.items():
                sorted_matches = sorted(matches, key=lambda x: x.get('score', 0.0), reverse=True)
                all_results[source] = sorted_matches[:top_k_final]


        # --- ÉTAPE 4: GÉNÉRATION LLM (Optionnel) ---
        # Reconstruire le contexte à partir des résultats finaux (potentiellement rerankés)
        context_texts = []
        for source, matches in all_results.items():
            for match in matches:
                context_texts.append(match['metadata']['entity']['text'])

        llm_req = llm_prompt(request, context_texts)

        # --- FIN: Construction du dictionnaire de retour ---
        total_duration = time.perf_counter() - start_total_time
        
        return {
            "database": "milvus",
            "user_query": request.prompt,
            "filter": final_filter_expr_str,
            "matches": all_results,
            "context": llm_req.context,
            "response": llm_req.llm_response,
            "embedding": round(embed_duration, 2),
            "fournisseur_non_vide": None, # Maintenu de l'original
            "full_user_prompt": llm_req.full_user_prompt,
            "chat_model": request.llm.chat_model,
            "temperature": request.llm.temperature,
            "vector_search": round(search_duration, 2),
            "rerank_duration": round(rerank_duration, 2), # Ajout pour information
            "llm_execution": round(llm_req.llm_duration, 2),
            "total_process": round(total_duration, 2),
            "import_duration": 0, # Maintenu de l'original, non calculé ici
            "llm_reponse": llm_req.response
        }

    except Exception as e:
        logger.error(f"Une erreur majeure est survenue dans la recherche (non-stream): {e}", exc_info=True)
        # En cas d'erreur, retourner une structure similaire mais avec une erreur
        return {
            "database": "milvus",
            "user_query": request.prompt,
            "filter": "",
            "matches": {},
            "context": "",
            "response": f"Erreur serveur: {e}",
            "embedding": round(embed_duration, 2),
            "fournisseur_non_vide": None,
            "full_user_prompt": "",
            "chat_model": request.llm.chat_model,
            "temperature": request.llm.temperature,
            "vector_search": round(search_duration, 2),
            "rerank_duration": round(rerank_duration, 2),
            "llm_execution": round(llm_duration, 2),
            "total_process": round(time.perf_counter() - start_total_time, 2),
            "import_duration": 0,
            "llm_reponse": llm_req.response
        }
        
async def search_in_milvus_classique_stream(request: SearchRequest):
    """
    Orchestre le flux de recherche CLASSIQUE (par filtre) en streaming.
    """
    start_total_time = time.perf_counter()
    
    try:
        # --- ÉTAPE 1: PAS D'EMBEDDING ---
        yield {"type": "status", "payload": "Lancement de la recherche par filtre..."}

        # --- ÉTAPE 2: RÉCUPÉRATION (QUERY) ---
        top_k_final = int(request.top_k)
        all_source_results = []
        search_duration = 0

        for item in request.source:
            source_name = item.source
            filtre = item.filtre
            yield {"type": "status", "payload": f"Recherche classique dans '{source_name}'..."}
            start_search_source = time.perf_counter()

            filters = []
            filter_expr_global = await filtre_source(request.filtre, source_name)
            if filter_expr_global:
                filters.append(" and ".join(filter_expr_global))
            
            filter_expr_source = await filtre_source(filtre, source_name) if filtre else ""
            if filter_expr_source:
                filters.append(" and ".join(filter_expr_source))
            
            final_filter_expr = " and ".join(filters) if filters else ""
            # if not final_filter_expr:
            #      yield {"type": "error", "payload": f"L'expression de filtre est obligatoire pour une recherche classique."}
            #      return

            # Appel au NOUVEAU client gRPC pour la recherche classique
            source_results = await database_client.classic_search_vector(
                collection=source_name,
                filter_expr=final_filter_expr,
                k=top_k_final
            )
            
            search_duration += time.perf_counter() - start_search_source
            
            if source_results is None:
                yield {"type": "warning", "payload": f"Erreur lors de la recherche dans '{source_name}'."}
                continue
            
            all_source_results.extend([MessageToDict(res) for res in source_results])

        # --- ÉTAPE 3: PAS DE RERANKING ---
        # Le reranking n'est pas applicable car il n'y a pas de score de similarité initial.
        final_results = all_source_results
        yield {"type": "initial_results", "payload": {"results": final_results, "duration": round(search_duration, 2)}}
        # --- ÉTAPE 4: GÉNÉRATION LLM (Optionnel) ---
        llm_duration = 0
        if request.action == 2 and final_results:
            yield {"type": "status", "payload": "Génération de la réponse avec le LLM..."}
            context_texts = [res['metadata']['entity']['text'] for res in final_results]
            
            yield {"type": "llm_start"}
            start_llm_time = time.perf_counter()
            
            # token_generator = await asyncio.to_thread(llm_prompt_stream, request, context_texts)
            token_generator = await asyncio.to_thread(llm_prompt, request, context_texts)
            # token_generator = llm_prompt(request, context_texts)
            yield {"type": "llm_chunk" if not token_generator.error else "error", "payload": token_generator.llm_response, "llm_response": token_generator.response}
            
            # for token in token_generator:
            #     yield {"type": "llm_chunk", "payload": token}
            
            llm_duration = time.perf_counter() - start_llm_time
        
        # --- FIN DU FLUX ---
        total_duration = time.perf_counter() - start_total_time
        final_summary = {
            "timings": {
                "embedding": 0, # Pas d'embedding
                "vector_search": round(search_duration, 2),
                "rerank": 0, # Pas de reranking
                "llm_execution": round(llm_duration, 2),
                "total_process": round(total_duration, 2),
            },
            "result_count": len(final_results)
        }
        yield {"type": "end_of_stream", "payload": final_summary}

    except Exception as e:
        logger.error(f"Erreur majeure dans le flux de recherche classique: {e}", exc_info=True)
        yield {"type": "error", "payload": f"Erreur serveur: {e}"}
    finally:
        logger.info("Flux de recherche classique terminé.")
        
async def search_in_milvus_classique(request: SearchRequest) -> dict:
    """
    Orchestre une recherche CLASSIQUE complète (non-streamée).
    """
    logger.info(f"[gRPC] Recherche classique (non-stream): filtre='{request.filtre}', sources={[s.source for s in request.source]}")
    start_total_time = time.perf_counter()

    search_duration, llm_duration = 0, 0
    llm_response_content, context, full_user_prompt, final_filter_expr_str = "", "", "", ""
    llm_req = LLMPipeline(llm_response="", context="", full_user_prompt="", response={})
    try:
        # --- ÉTAPE 1: PAS D'EMBEDDING ---

        # --- ÉTAPE 2: RÉCUPÉRATION (QUERY) ---
        start_search = time.perf_counter()
        top_k_final = int(request.top_k)
        all_results = {}

        for item in request.source:
            source_name = item.source
            filtre = item.filtre

            filters = []
            filter_expr_global = await filtre_source(request.filtre, source_name)
            if filter_expr_global:
                filters.append(" and ".join(filter_expr_global))
            
            filter_expr_source = await filtre_source(filtre, source_name) if filtre else []
            if filter_expr_source:
                filters.append(" and ".join(filter_expr_source))
            
            final_filter_expr = " and ".join(filters) if filters else ""
            final_filter_expr_str = final_filter_expr
            # if not final_filter_expr:
            #     raise ValueError("L'expression de filtre est obligatoire pour une recherche classique.")

            logger.info(f"Recherche classique dans '{source_name}' avec filtre: {final_filter_expr}")

            source_results = await database_client.classic_search_vector(
                collection=source_name,
                filter_expr=final_filter_expr,
                k=top_k_final
            )
            
            all_results[source_name] = [MessageToDict(res) for res in source_results]
        
        search_duration = time.perf_counter() - start_search

        # --- ÉTAPE 3: PAS DE RERANKING ---

        # --- ÉTAPE 4: GÉNÉRATION LLM (Optionnel) ---
        context_texts = [match['metadata']['entity']['text'] for matches in all_results.values() for match in matches]
        
        # llm_req = llm_prompt(request, context_texts)
        llm_req = await asyncio.to_thread(llm_prompt, request, context_texts)

        # --- FIN: Construction du dictionnaire de retour ---
        total_duration = time.perf_counter() - start_total_time
        
        return {
            "database": "milvus",
            "user_query": request.prompt,
            "filter": final_filter_expr_str,
            "matches": all_results,
            "context": llm_req.context,
            "response": llm_req.llm_response,
            "embedding": 0,
            "fournisseur_non_vide": None,
            "full_user_prompt": llm_req.full_user_prompt,
            "chat_model": request.llm.chat_model,
            "temperature": request.llm.temperature,
            "vector_search": round(search_duration, 2),
            "rerank_duration": 0,
            "llm_execution": round(llm_req.llm_duration, 2),
            "total_process": round(total_duration, 2),
            "import_duration": 0,
            "llm_reponse": llm_req.response
        }

    except Exception as e:
        logger.error(f"Erreur majeure dans la recherche classique (non-stream): {e}", exc_info=True)
        return {
            "database": "milvus",
            "user_query": request.prompt,
            "filter": final_filter_expr_str,
            "matches": {},
            "context": "",
            "response": f"Erreur serveur: {e}",
            "embedding": 0,
            "fournisseur_non_vide": None,
            "full_user_prompt": "",
            "chat_model": request.llm.chat_model,
            "temperature": request.llm.temperature,
            "vector_search": round(search_duration, 2),
            "rerank_duration": 0,
            "llm_execution": round(llm_duration, 2),
            "total_process": round(time.perf_counter() - start_total_time, 2),
            "import_duration": 0,
            "llm_reponse": llm_req.response
        }