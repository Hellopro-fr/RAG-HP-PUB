import math
import time
import os
import logging
from functools import lru_cache
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from sentence_transformers import SentenceTransformer, CrossEncoder
from pymilvus import connections, Collection, utility, DataType
from app.core.credentials import settings, model_settings
from app.schemas.search import SearchRequestWs as SearchRequest, LLMOptions
import asyncio
import torch
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
    """Charge le modèle CrossEncoder pour le reranking sur GPU si disponible."""
    logger.info(f"Chargement du modèle de reranking '{model_name}'...")
    
    # Détecte si un GPU est disponible, sinon utilise le CPU
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f"Utilisation du device : {device} pour le reranking.")
    
    # Si vous êtes sur CPU, 7 secondes est normal. Sur GPU, ce sera bien plus rapide.
    model = CrossEncoder(model_name, device=device, trust_remote_code=True)
    
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
        # Log the error and return an empty map if the collection doesn't exist
        # This prevents crashes if a non-existent source is requested.
        logger.error(f"Could not retrieve schema for collection '{collection_name}': {e}")
        return {}

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
                stream=True
            )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    except Exception as e:
        logger.error(f"Erreur durant le streaming LLM: {e}")
        yield f"\n\n--- ERREUR --- \n{e}"


def filtre_source (filtre: dict, source: str = "") -> list:
    clauses = []
    field_types = get_field_type_map(source)
    NUMERIC_DTYPES = {DataType.INT8, DataType.INT16, DataType.INT32, DataType.INT64, DataType.FLOAT, DataType.DOUBLE}
    for key, val in filtre.items():
        dtype = field_types.get(key)
        if key == 'id_categorie' and source == 'produits':
            key = 'categorie'
        
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
            if isinstance(val, list):
                numeric_vals = [int(v) if dtype in {DataType.INT8, DataType.INT16, DataType.INT32, DataType.INT64} else float(v) for v in val]
                clauses.append(f"{key} in {numeric_vals}")
            else:
                # Format as: field_name == 123
                numeric_val = int(val) if dtype in {DataType.INT8, DataType.INT16, DataType.INT32, DataType.INT64} else float(val)
                clauses.append(f"{key} == {numeric_val}")
        else:
            if isinstance(val, list):
                # Format as: field_name in ["val1", "val2"]
                quoted_vals = [repr(str(v)) for v in val]
                clauses.append(f"{key} in [{', '.join(quoted_vals)}]")
            else:
                # Format as: field_name == "value"
                clauses.append(f"{key} == {repr(str(val))}")
    return clauses

def _serialize_entity(entity, source: str = "produits") -> dict:
    """
    Converts a Milvus search result entity to a JSON-serializable dictionary.
    Handles special types like RepeatedScalarContainer for ARRAY fields by converting them to lists.
    """
    serializable_dict = {}
    fields = get_field_type_map(source)
    for key, value in entity.to_dict().items():
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes, dict)):
            serializable_dict[key] = list(value)
        else:
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if fields.get(sub_key) == DataType.ARRAY:
                        value[sub_key] = list(sub_value)
            serializable_dict[key] = value
    return serializable_dict

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
        filter_expr = filtre_source(request.filtre, source)
        if filter_expr:
            filters.append(" and ".join(filter_expr))
        
        filter_expr_source = filtre_source(filtre, source) if filtre else ""
        if filter_expr_source:
            filters.append(" and ".join(filter_expr_source))
        
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
                    entity_data = hit.entity.to_dict()
                    all_matches_for_reranking.append({
                        "id": hit.id, 
                        "score": hit.distance, 
                        "relevance_score": convert_score_to_percentage(float(hit.distance), score_type='cosine'), 
                        "metadata": _serialize_entity(hit.entity, source), 
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
        last_step_time = start_rerank_time
        reranker = await asyncio.to_thread(get_reranker_model, request.options.reranker_model)
        current_time = time.perf_counter()
        reranker_duration = current_time - last_step_time
        last_step_time = current_time  # Mettre à jour le marqueur de temps
        logger.info(f"Temps de chargement du modele : {reranker_duration:.4f} secondes.")

        # *** CORRECTION 1 : Utilisation de .get() pour le reranker ***
        start_predict_time = time.perf_counter()
        pairs = [[request.prompt, match["metadata"]["entity"]["text"]] for match in all_matches_for_reranking]
        logger.info(f"top k recherche : {top_k} - top k reranking : {reranking_top_k}")
        current_time = time.perf_counter()
        pairs_duration = current_time - last_step_time
        last_step_time = current_time  # Mettre à jour le marqueur de temps
        logger.info(f"Temps de préparation des paires : {pairs_duration:.4f} secondes.")

        # scores = await asyncio.to_thread(reranker.predict, pairs, show_progress_bar=False)
        with torch.inference_mode(), torch.autocast("cuda"):
            scores = await asyncio.to_thread(
                reranker.predict, 
                pairs, 
                show_progress_bar=False,
                batch_size=128 # Voir Étape 2
            )
        prediction_duration = time.perf_counter() - start_predict_time
        logger.info(f"Temps de prédiction du reranker (FP16) : {prediction_duration:.3f} secondes.")
        current_time = time.perf_counter()
        prediction_duration = current_time - last_step_time
        last_step_time = current_time # Mettre à jour le marqueur de temps
        logger.info(f"Temps de prédiction du reranker : {prediction_duration:.2f} secondes.")

        for match, score in zip(all_matches_for_reranking, scores):
            match["rerank_score"] = float(score)
            match['relevance_score'] = convert_score_to_percentage(float(score), score_type='reranker')
        current_time = time.perf_counter()
        match_duration = current_time - last_step_time
        last_step_time = current_time # Mettre à jour le marqueur de temps
        logger.info(f"Temps de match : {match_duration:.4f} secondes.")
        
        reranked_matches = sorted(all_matches_for_reranking, key=lambda x: x["rerank_score"], reverse=True)
        current_time = time.perf_counter()
        processing_sort_duration = current_time - last_step_time
        last_step_time = current_time # Mettre à jour le marqueur de temps
        logger.info(f"Temps de traitement et tri : {processing_sort_duration:.4f} secondes.")

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
        context_texts = [res["metadata"]["entity"].get("text", "") for res in final_results]
        
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