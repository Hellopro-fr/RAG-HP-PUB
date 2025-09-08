import math
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
from app.schemas.search import SearchRequestWs as SearchRequest, LLMOptions
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

def convert_score_to_percentage(score: float, score_type: str = 'cosine') -> float:
    """Convertit un score de similarité ou de reranker en pourcentage."""
    if score_type == 'reranker':
        # Applique la fonction sigmoïde pour mapper le logit à une plage de 0-1
        prob = 1 / (1 + math.exp(-score))
        return round(prob * 100, 2)
    else: # Par défaut, traite le score comme une similarité cosinus (déjà entre 0 et 1)
        return round(score * 100, 2)
    
import_duration = time.perf_counter() - import_start_time

# Dictionnaires de mapping
list_etat = {"1": "Client", "2": "Pause", "3": "Prospect"}
list_affichage = {"1": "Complet", "3": "Restreint", "5": "Découverte", "4": "Non visible"}

def llm_prompt_stream(request: SearchRequest, context_texts):
    """
    Génère une réponse LLM en streaming et yield chaque token.
    """
    context = "\n-----\n\n\n".join(context_texts)
    full_user_prompt = request.llm.template_prompt.format(chunks=context, recherche=request.prompt)
    
    type_prompt = next((key for key, values in model_settings.items() if request.chat_model in values), "openai")

    try:
        if type_prompt == "openai":
            if request.chat_model == "deepseek":
                deepseek = DeepSeek()
                deepseek.set_temperature(request.temperature)
                stream = deepseek.chat(full_user_prompt, stream=True)
            else:
                openai_client = get_openai_client()
                stream = openai_client.chat.completions.create(
                    model=request.chat_model,
                    messages=[{"role": "user", "content": full_user_prompt}],
                    temperature=float(request.temperature),
                    stream=True
                )
        else: # OpenRouter
            client_or = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )
            stream = client_or.chat.completions.create(
                model=request.chat_model,
                messages=[{"role": "user", "content": full_user_prompt}],
                stream=True
            )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    except Exception as e:
        logger.error(f"Erreur durant le streaming LLM: {e}")
        yield f"\n\n--- ERREUR --- \n{e}"


def filtre_source (filtre: dict) -> str:
    clauses = []
    for key, val in filtre.items():
        if isinstance(val, list):
            clauses.append(f"{key} in [{','.join(val)}]")
        elif isinstance(val, str):
            clauses.append(f'{key} == "{val}"')
    return " and ".join(clauses)

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
    
    top_k = int(request.top_k)
    reranking_top_k = top_k * 3 if request.options.use_reranker else top_k

    all_results = {}
    context_texts = []
    
    collection_metadata = {
        "produits": {"payload_fournisseur": "id_fournisseur"},
    }
    
    all_matches_for_reranking = []
    
    start_search = time.perf_counter()
    for item in request.source:
        source = item.source
        filtre = item.filtre
        logger.info(f"Processing source: '{source}' with filtre: {filtre}")
        
        yield {"type": "status", "payload": f"Recherche dans {source}..."}

        if not utility.has_collection(source):
            yield {"type": "warning", "payload": f"Collection '{source}' n'existe pas."}
            all_results[source] = []
            continue

        collection = Collection(name=source)
        collection.load()

        search_params = {"metric_type": "COSINE", "params": {"ef": _ef_search(reranking_top_k)}}
        metadata = collection_metadata.get(source, {"payload_fournisseur": "id_fournisseur"})
        
        filters = []
        filter_expr = build_milvus_expression(request.filtre, metadata["payload_fournisseur"], "1000000" in request.filtre.get("fournisseur", {}))
        if filter_expr:
            filters.append(filter_expr)
        filter_expr_source = filtre_source(filtre) if filtre else ""
        if filter_expr_source:
            filters.append(filter_expr_source)
        
        filter_expr = " and ".join(filters) if filters else ""
        
        logger.info(f"Filtre expression : {filter_expr}")
        
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
                        "id": hit.id, 
                        "score": hit.distance, 
                        "relevance_score": convert_score_to_percentage(float(hit.distance), score_type='cosine'), 
                        "metadata": dict(hit.entity), 
                        "source": source
                    })
            
        except Exception as e:
            yield {"type": "error", "payload": f"Error searching in {source}: {e}"}
            all_results[source] = []

    search_duration = time.perf_counter() - start_search
    rerank_duration = 0
    final_results = []
    if request.options.use_reranker and all_matches_for_reranking:
        yield {"type": "status", "payload": "Reclassement (reranking) des résultats..."}
        start_rerank_time = time.perf_counter()
        reranker = await asyncio.to_thread(get_reranker_model, request.options.reranker_model)
        
        # *** CORRECTION 1 : Utilisation de .get() pour le reranker ***
        pairs = [[request.prompt, match["metadata"].get("text", "")] for match in all_matches_for_reranking]
        scores = await asyncio.to_thread(reranker.predict, pairs, show_progress_bar=False)
        
        for match, score in zip(all_matches_for_reranking, scores):
            match["rerank_score"] = float(score)
            match['relevance_score'] = convert_score_to_percentage(float(score), score_type='reranker')
        
        reranked_matches = sorted(all_matches_for_reranking, key=lambda x: x["rerank_score"], reverse=True)
        final_results = reranked_matches[:top_k]
        rerank_duration = time.perf_counter() - start_rerank_time
        yield {"type": "rerank_complete", "payload": {"results": final_results, "duration": round(rerank_duration, 2)}}
    else:
        all_matches_for_reranking.sort(key=lambda x: x['score'], reverse=True)
        final_results = all_matches_for_reranking[:top_k]
        yield {"type": "rerank_complete", "payload": {"results": final_results, "duration": 0}}
        
    llm_generation_started = False
    llm_duration = 0
    if request.action == 2 and final_results:
        yield {"type": "status", "payload": f"Génération de la réponse avec le LLM : {request.llm.chat_model}..."}
        
        # *** CORRECTION 2 : Utilisation de .get() pour le contexte du LLM ***
        context_texts = [res["metadata"].get("text", "") for res in final_results]
        
        yield {"type": "llm_start"}
        llm_generation_started = True
        start_llm_time = time.perf_counter()
        
        token_generator = await asyncio.to_thread(llm_prompt_stream, request, context_texts)
        
        for token in token_generator:
            yield {"type": "llm_chunk", "payload": token}
        
        llm_duration = time.perf_counter() - start_llm_time
    
    total_duration = time.perf_counter() - start_total_time
        
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