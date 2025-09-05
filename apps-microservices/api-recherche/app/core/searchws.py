import time
import os
import logging
from functools import lru_cache
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, IsNullCondition, MatchAny
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from sentence_transformers import SentenceTransformer, CrossEncoder
from pymilvus import connections, Collection, utility
from app.core.credentials import settings, model_settings
from app.schemas.search import SearchRequest, LLMPipeline
import asyncio

from app.core.openrouter import chat_with_openrouter

class DeepSeek:
	def __init__(self, config=None):
		config = config or {}
		self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
		self.BASE_URL = "https://api.deepseek.com"
		self.MODEL = "deepseek-chat"
		self.TEMPERATURE = 0.4
		self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

	def chat(self, message):
		response = self.client.chat.completions.create(
			model=self.MODEL,
			messages=[
				{"role": "system", "content": "Tu es un assistant intelligent et serviable."},
				{"role": "user", "content": message},
			],
			temperature=self.TEMPERATURE
		)
		return {"content": response.choices[0].message.content, "response": response}

	def set_temperature(self, temperature):
		self.TEMPERATURE = float(temperature)

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mesurer le temps d'import initial
import_start_time = time.perf_counter()

@lru_cache(maxsize=None)
def get_embedding_model(model_name: str = "dangvantuan/sentence-camembert-large"):
    logger.info(f"Chargement initial du modèle d'embedding '{model_name}'...")
    model = SentenceTransformer(model_name)
    logger.info("Modèle d'embedding chargé.")
    return model

@lru_cache(maxsize=None)
def get_reranker_model(model_name: str = "BAAI/bge-reranker-v2-m3"):
    """Charge le modèle CrossEncoder pour le reranking."""
    logger.info(f"Chargement du modèle de reranking '{model_name}'...")
    model = CrossEncoder(model_name, trust_remote_code=True)
    logger.info("Modèle de reranking chargé.")
    return model

def get_milvus_connection():
    alias = "default"
    try:
        if not connections.has_connection(alias):
            logger.info("Connexion à Milvus...")
            # connections.connect(alias, uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN)
            connections.connect(alias, host=settings.ZILLIZ_URI, port=settings.ZILLIZ_PORT)
            print(settings.ZILLIZ_URI, settings.ZILLIZ_PORT)
            # 2. List all collections
            collection_names = utility.list_collections()

            # 3. Print the list of collection names
            print("Collections in Milvus:", collection_names)
            logger.info(f"Connecté à Milvus.")
    except Exception as e:
        logger.error(f"❌ Erreur de connexion à Milvus: {e}")
        raise e

@lru_cache(maxsize=None)
def get_openai_client():
    logger.info("Initialisation du client OpenAI...")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    logger.info("Client OpenAI initialisé.")
    return client

def _search_params(request: SearchRequest) -> dict | None:
    ef_search = request.params.get("ef_search") if request.params else None
    m_params  = request.params.get("m") if request.params else None
    
    if ef_search and m_params:
        return {
            "ef": int(ef_search),
            "m": int(m_params),
            "source": f"_{m_params}_{ef_search}"
        }
    
    return None
def _ef_search(nb_chunk: int) -> int:
    """Calcule la valeur ef_search pour Qdrant/Milvus en fonction du nombre de chunks."""
    return 300 if nb_chunk <= 150 else nb_chunk * 2

import_duration = time.perf_counter() - import_start_time

# Dictionnaires de mapping
list_etat = {"1": "Client", "2": "Pause", "3": "Prospect"}
list_affichage = {"1": "Complet", "3": "Restreint", "5": "Découverte", "4": "Non visible"}

def llm_prompt(request: SearchRequest, context_texts) -> LLMPipeline:
    llm_response, full_user_prompt, llm_duration, context = "", "", 0, ""
    if request.action == 2 and context_texts:
        context = "\n-----\n\n\n".join(context_texts)
        full_user_prompt = request.template_prompt.format(chunks=context, recherche=request.prompt)
        
        type_prompt = next((key for key, values in model_settings.items() if request.chat_model in values), "openai")
            
        start_llm_time = time.perf_counter()
        if type_prompt == "openai":
            if request.chat_model == "deepseek":
                deepseek = DeepSeek()
                deepseek.set_temperature(request.temperature)
                llm_response = deepseek.chat(full_user_prompt)['content']
            else:
                openai_client = get_openai_client()
                completion = openai_client.chat.completions.create(
                    model=request.chat_model,
                    messages=[{"role": "user", "content": full_user_prompt}],
                    temperature=float(request.temperature)
                )
                llm_response = completion.choices[0].message.content
        else:
            client_or = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )
            completion = client_or.chat.completions.create(
                extra_body={},
                model=request.chat_model,
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
            # llm_response = chat_with_openrouter(request.chat_model, full_user_prompt).choices[0].message.content
            
        llm_duration = time.perf_counter() - start_llm_time
    return LLMPipeline(llm_duration=llm_duration,llm_response=llm_response,full_user_prompt=full_user_prompt,context=context)

def build_milvus_expression(data: dict, payload_fournisseur_key: str, fournisseur_non_vide: bool) -> str:
	"""Traduit les filtres de la requête en une chaîne d'expression pour Milvus."""
	clauses = []

	# Catégories (ex: 'categorie in ["Bungalows", "Container"]')
	categorie_dict = data.get("categorie", {})
	if categorie_dict:
		vals = [f'"{v}"' for v in categorie_dict.values()] # Ajouter des guillemets pour les chaînes
		if vals: 
			clauses.append(f'categorie in [{",".join(vals)}]')

	# Fournisseurs
	fournisseur_dict = data.get("fournisseur", {})
	if fournisseur_dict:
		vals = list(map(lambda v: f'"{v}"', fournisseur_dict.keys() if payload_fournisseur_key == "id_fournisseur" else fournisseur_dict.values()))
		if vals: 
			clauses.append(f'{payload_fournisseur_key} in [{",".join(vals)}]')

	# État
	etat_ids = data.get("etat", [])
	if etat_ids:
		vals = [f'"{list_etat[str(e)]}"' for e in etat_ids if str(e) in list_etat]
		if vals: 
			clauses.append(f'etat in [{",".join(vals)}]')

	# Affichage
	affichage_ids = data.get("affichage", [])
	if affichage_ids:
		vals = [f'"{list_affichage[str(a)]}"' for a in affichage_ids if str(a) in list_affichage]
		if vals: 
			clauses.append(f'affichage in [{",".join(vals)}]')

	# Fournisseur non vide
	if fournisseur_non_vide:
		clauses.append(f'{payload_fournisseur_key} != "" and {payload_fournisseur_key} is not null')

	return " and ".join(clauses)

# async def search_in_milvus(request: SearchRequest):
#     # Implémentation complète de la recherche Milvus
#     logger.info(f"[MILVUS] Recherche: prompt='{request.prompt[:50]}...', sources={request.source}")
#     start_total_time = time.perf_counter()

#     # 1. Obtenir les ressources nécessaires
#     get_milvus_connection()
#     embedding_model = get_embedding_model()

#     start_embed = time.perf_counter()
#     query_vector = [embedding_model.encode(request.prompt, normalize_embeddings=True).tolist()]
#     embed_duration = time.perf_counter() - start_embed

#     top_k = int(request.nombre_resultat)
#     _search_params_verification = _search_params(request)
#     _top_k = top_k
#     if _search_params_verification:
#         _top_k = int(_search_params_verification["ef"])
#         logger.info(f"Utilisation des paramètres de recherche personnalisés: {_search_params_verification}")
        
#     reranking_top_k = top_k
#     if request.use_reranker:
#         reranking_top_k = top_k * 3
#         logger.info(f"Reranker activé. Récupération de {_top_k} documents pour reranker à {top_k}.")
        
#     all_results = {}
#     context_texts = []

#     filter_expr = "" # Placeholder
#     collection_metadata = {
#         "devis_poc": {"payload_fournisseur": "liste_frns"},
#         "siteweb_poc": {"payload_fournisseur": "id_fournisseur"},
#         "echanges_poc": {"payload_fournisseur": "id_fournisseur"}
#     }

#     start_search = time.perf_counter()
#     for source in request.source:
#         _source = source
#         if _search_params_verification:
#             _source = f"{source}{_search_params_verification['source']}" 
            
        
#         if not utility.has_collection(_source):
#             logger.warning(f"La collection Milvus '{source}' n'existe pas.")
#             all_results[source] = []
#             continue

#         collection = Collection(name=_source)
#         collection.load()

#         search_params = {"metric_type": "COSINE", "params": {"ef": _top_k if _search_params_verification else _ef_search(top_k)}}
#         output_fields = settings.MILVUS_OUTPUT_FIELDS_CONFIG.get(source, ["*"])

#         metadata = collection_metadata.get(source, {"payload_fournisseur": "id_fournisseur"})
#         filter_expr = build_milvus_expression(request.dict(), metadata["payload_fournisseur"], "1000000" in request.fournisseur)

#         all_fields = [field.name for field in collection.schema.fields]
#         fields_without_embedding = [f for f in all_fields if f != "embedding"]
        
#         search_results = collection.search(
#             data=query_vector,
#             anns_field="embedding",
#             param=search_params,
#             limit=reranking_top_k,
#             expr=filter_expr,
#             # output_fields=output_fields
#             output_fields=fields_without_embedding
#         )
      
#         # Récupérer le payload complet pour les IDs trouvés
#         hit_ids = [hit.id for hit in search_results[0]]
#         if not hit_ids:
#             all_results[source] = []
#             continue
        
#         # Mapper les distances de recherche aux entités complètes
#         id_to_distance = {hit.id: hit.distance for hit in search_results[0]}

#         matches_info = []
#         if search_results and search_results[0]:
#             for hit in search_results[0]:
#                 entity = {field: hit.entity.get(field) for field in output_fields}
#                 context_texts.append(entity.get("text", ""))
#                 matches_info.append({
#                     "id": hit.id, "score": hit.distance, "id_lead": entity.get("lead_id"), "metadata": entity
#                 })
#         all_results[source] = matches_info
#     search_duration = time.perf_counter() - start_search
    
#     rerank_duration = 0
#     if request.use_reranker:
#         logger.info("Début du reranking...")
#         start_rerank_time = time.perf_counter()
#         reranker = get_reranker_model(request.reranker_model)
#         reranked_results = {}
#         for source, matches in all_results.items():
#             if not matches:
#                 reranked_results[source] = []
#                 continue
            
#             pairs = [[request.prompt, match["metadata"]["text"]] for match in matches]
#             scores = reranker.predict(pairs, show_progress_bar=False)
            
#             for match, score in zip(matches, scores):
#                 match["rerank_score"] = float(score)
            
#             reranked_matches = sorted(matches, key=lambda x: x["rerank_score"], reverse=True)
#             reranked_results[source] = reranked_matches[:top_k]
        
#         all_results = reranked_results
#         rerank_duration = time.perf_counter() - start_rerank_time
#         logger.info(f"Reranking terminé en {rerank_duration:.2f}s.")

#         # ### AJOUT ###: Reconstruire le contexte à partir des résultats (potentiellement rerankés)
#         logger.info("Reconstruction du contexte après reranking...")
#         context_texts = []
#         for source, matches in all_results.items():
#             for match in matches:
#                 context_texts.append(match["metadata"].get("text", ""))

#     # TODO complété: Logique LLM pour Milvus
#     llm_req = llm_prompt(request, context_texts)
    
#     total_duration = time.perf_counter() - start_total_time
    
#     return {
#         "database": "milvus",
#         "user_query": request.prompt,
#         "filter": filter_expr,
#         "matches": all_results,
#         "context": llm_req.context,
#         "response": llm_req.llm_response,
#         "embedding": round(embed_duration, 2),
#         "fournisseur_non_vide": None, # Non implémenté pour Milvus dans le code d'origine
#         "full_user_prompt": llm_req.full_user_prompt,
#         "chat_model": request.chat_model,
#         "temperature": request.temperature,
#         "vector_search": round(search_duration, 2),
#         "total_process": round(total_duration, 2),
#         "llm_execution": round(llm_req.llm_duration, 2),
#         "import_duration": round(import_duration, 2)
#     }

async def search_in_milvus_stream(request: SearchRequest):
    start_total_time = time.perf_counter()
    
    try:
        await asyncio.to_thread(get_milvus_connection)
    except Exception as e:
        yield {"type": "error", "payload": f"Milvus connexion avec erreur: {e}"}
        return
    
    embedding_model = await asyncio.to_thread(get_embedding_model)
    yield {"type": "status", "payload": "Chargement modèle d'embedding avec succès..."}
    start_embed = time.perf_counter()
    query_vector = await asyncio.to_thread(
        embedding_model.encode, request.prompt, normalize_embeddings=True
    )
    query_vector_list = [query_vector.tolist()]
    embed_duration = time.perf_counter() - start_embed
    yield {"type": "embedding_complete", "payload": {"duration": round(embed_duration, 2)}}
    
    top_k = int(request.nombre_resultat)
    reranking_top_k = top_k * 3 if request.use_reranker else top_k

    all_results = {}
    context_texts = []
    
    collection_metadata = {
        # TODO:
        # ajouter metadata pour les autres collections si besoin
        "produits": {"payload_fournisseur": "id_fournisseur"},
        # "devis_poc": {"payload_fournisseur": "liste_frns"},
        # "siteweb_poc": {"payload_fournisseur": "id_fournisseur"},
        # "echanges_poc": {"payload_fournisseur": "id_fournisseur"}
    }
    
    all_matches_for_reranking = []
    
    start_search = time.perf_counter()
    for source in request.source:
        yield {"type": "status", "payload": f"Recherche dans {source}..."}

        if not utility.has_collection(source):
            yield {"type": "warning", "payload": f"Collection '{source}' n'existe pas."}
            all_results[source] = []
            continue

        collection = Collection(name=source)
        collection.load()

        search_params = {"metric_type": "COSINE", "params": {"ef": _ef_search(reranking_top_k)}}
        metadata = collection_metadata.get(source, {"payload_fournisseur": "id_fournisseur"})
        filter_expr = build_milvus_expression(request.dict(), metadata["payload_fournisseur"], "1000000" in request.fournisseur)
        
        all_fields = [field.name for field in collection.schema.fields]
        fields_without_embedding = [f for f in all_fields if f != "embedding"]

        try:
            search_results = await asyncio.to_thread(
                collection.search,
                data=query_vector_list,
                anns_field="embedding",
                param=search_params,
                limit=reranking_top_k,
                expr=filter_expr,
                output_fields=fields_without_embedding
            )

            if search_results and search_results[0]:
                for hit in search_results[0]:
                    all_matches_for_reranking.append({
                        "id": hit.id, "score": hit.distance, "metadata": hit.entity, "source": source
                    })
            # yield {"type": "partial_result", "payload": {"source": source, "matches": matches_info, "filter": filter_expr}}
            
        except Exception as e:
            yield {"type": "error", "payload": f"Error searching in {source}: {e}"}
            all_results[source] = []

    search_duration = time.perf_counter() - start_search
    rerank_duration = 0
    final_results = []
    if request.use_reranker and all_matches_for_reranking:
        yield {"type": "status", "payload": "Reclassement (reranking) des résultats..."}
        start_rerank_time = time.perf_counter()
        reranker = get_reranker_model(request.reranker_model)
        
        pairs = [[request.prompt, match["metadata"]["text"]] for match in all_matches_for_reranking]
        scores = await asyncio.to_thread(reranker.predict, pairs, show_progress_bar=False)
        
        for match, score in zip(all_matches_for_reranking, scores):
            match["rerank_score"] = float(score)
        
        reranked_matches = sorted(all_matches_for_reranking, key=lambda x: x["rerank_score"], reverse=True)
        final_results = reranked_matches[:top_k]
        rerank_duration = time.perf_counter() - start_rerank_time
        yield {"type": "rerank_complete", "payload": {"results": final_results, "duration": round(rerank_duration, 2)}}
    else:
        # Si le reranker n'est pas utilisé, on prend simplement les meilleurs résultats bruts
        all_matches_for_reranking.sort(key=lambda x: x['score'], reverse=True) # COSINE: plus haut = mieux
        final_results = all_matches_for_reranking[:top_k]
        yield {"type": "rerank_complete", "payload": {"results": final_results, "duration": 0}}
        
    llm_generation_started = False
    if request.action == 2 and final_results:
        yield {"type": "status", "payload": f"Génération de la réponse avec le LLM : {request.chat_model}..."}
        context_texts = [res["metadata"].get("text", "") for res in final_results]
        
        # Le stream LLM commence
        yield {"type": "llm_start"}
        llm_generation_started = True
        start_llm_time = time.perf_counter()
        token_generator = llm_prompt_stream(request, context_texts)
        for token in token_generator:
            yield {"type": "llm_chunk", "payload": token}
        
        llm_duration = time.perf_counter() - start_llm_time
    else:
        llm_duration = 0
        
    final_summary = {
        "timings": {
            "embedding": round(embed_duration, 2),
            "vector_search": round(search_duration, 2),
            "rerank": round(rerank_duration, 2),
            "llm_execution": round(llm_duration, 2) if llm_generation_started else 0,
            "total_process": round(total_duration, 2),
        },
        "result_count": len(final_results)
    }
    yield {"type": "end_of_stream", "payload": final_summary}