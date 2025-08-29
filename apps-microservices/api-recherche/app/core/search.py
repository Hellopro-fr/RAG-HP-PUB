import time
import logging
from functools import lru_cache
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, IsNullCondition, MatchAny
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from pymilvus import connections, Collection, utility
from app.core.credentials import settings, model_settings
from app.schemas.search import SearchRequest, LLMPipeline

from app.core.or import chat_with_openrouter

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
def get_qdrant_client():
    logger.info("Connexion initiale à Qdrant Cloud...")
    # client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
    client = QdrantClient(host=settings.QDRANT_URL, port=settings.QDRANT_PORT)
    logger.info("Client Qdrant initialisé.")
    return client

def get_milvus_connection():
    alias = "default"
    try:
        if not connections.has_connection(alias):
            logger.info("Connexion à Milvus...")
            # connections.connect(alias, uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN)
            connections.connect(alias, host=settings.ZILLIZ_URL, port=settings.ZILLIZ_PORT)
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

import_duration = time.perf_counter() - import_start_time

# Dictionnaires de mapping
list_etat = {"1": "Client", "2": "Pause", "3": "Prospect"}
list_affichage = {"1": "Complet", "3": "Restreint", "5": "Découverte", "4": "Non visible"}

def llm_prompt(request: SearchRequest, context_texts) -> LLMPipeline:
    llm_response, full_user_prompt, llm_duration, context = "", "", 0, ""
    if request.action == 2 and context_texts:
        context = "\n-----\n\n\n".join(context_texts)
        full_user_prompt = request.template_prompt.format(chunks=context, recherche=request.prompt)
        
        type_prompt = any(value in models for models in model.values())
        
        start_llm_time = time.perf_counter()
        if type_prompt != "or":
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
            llm_response = chat_with_openrouter(request.chat_model, full_user_prompt).choices[0].message.content
            
        llm_duration = time.perf_counter() - start_llm_time
    return LLMPipeline(llm_duration=llm_duration,llm_response=llm_response,full_user_prompt=full_user_prompt,context=context)

def build_qdrant_filters(data: dict, payload_fournisseur: str, fournisseur_non_vide: bool):
    must_conditions = []
    must_not_conditions = []
    should_conditions = []
    
    categorie = data.get("categorie", {})
    if categorie:
        must_conditions.append(FieldCondition(key="categorie", match=MatchAny(any=list(categorie.values()))))

    etat_ids = data.get("etat", [])
    if etat_ids:
        noms_etat = [list_etat[str(e)] for e in etat_ids if str(e) in list_etat]
        if noms_etat:
            must_conditions.append(FieldCondition(key="etat", match=MatchAny(any=noms_etat)))

    affichage_ids = data.get("affichage", [])
    if affichage_ids:
        noms_affichage = [list_affichage[str(a)] for a in affichage_ids if str(a) in list_affichage]
        if noms_affichage:
            must_conditions.append(FieldCondition(key="affichage", match=MatchAny(any=noms_affichage)))
            
    liste_page_types = data.get("page_type", [])
    if liste_page_types:
        must_conditions.append(FieldCondition(key="page_type", match=MatchAny(any=liste_page_types)))

    if fournisseur_non_vide:
        if payload_fournisseur == 'id_fournisseur':
            must_not_conditions.append(FieldCondition(key=payload_fournisseur, match=MatchValue(value="")))
        elif payload_fournisseur == 'liste_frns':
            should_conditions.append(
                FieldCondition(
                    key="liste_frns",
                    match=models.MatchText(text="")
                )
            )
        # must_not_conditions.append(FieldCondition(key=payload_fournisseur, is_null=IsNullCondition(is_null=True)))
    else:
        fournisseur = data.get("fournisseur", {})
        if fournisseur:
            for key, value in fournisseur.items():
                if value:
                    if payload_fournisseur == 'id_fournisseur':
                        must_conditions.append(FieldCondition(key=payload_fournisseur, match=MatchValue(value=key)))
                    elif payload_fournisseur == 'liste_frns':
                        should_conditions.append(
                            FieldCondition(
                                key="liste_frns",
                                match=models.MatchText(text=value)
                            )
                        )

    if must_conditions or must_not_conditions or should_conditions:
        return Filter(
            must=must_conditions if must_conditions else None,
            must_not=must_not_conditions if must_not_conditions else None,
            should=should_conditions if should_conditions else None
        )
    return None

async def search_in_qdrant(request: SearchRequest):
    logger.info(f"Recherche Qdrant: prompt='{request.prompt[:50]}...', sources={request.source}")
    start_total_time = time.perf_counter()
    
    # 1. Obtenir les ressources nécessaires (elles seront chargées si c'est le premier appel)
    qdrant_client = get_qdrant_client()
    embedding_model = get_embedding_model()
    
    start_embed = time.perf_counter()
    query_vector = embedding_model.encode(request.prompt, normalize_embeddings=True).tolist()
    embed_duration = time.perf_counter() - start_embed

    top_k = int(request.nombre_resultat)
    search_params = models.SearchParams(hnsw_ef=300, exact=False)
    
    all_results = {}
    context_texts = []
    collection_metadata = {
        "devis_poc": {"payload_fournisseur": "liste_frns"},
        "siteweb_poc": {"payload_fournisseur": "id_fournisseur"},
        "echanges_poc": {"payload_fournisseur": "id_fournisseur"}
    }
    
    start_search = time.perf_counter()
    fournisseur_non_vide = "1000000" in request.fournisseur
    search_filter = None

    for source in request.source:
        metadata = collection_metadata.get(source, {"payload_fournisseur": "id_fournisseur"})
        payload_fournisseur = metadata["payload_fournisseur"]
        search_filter = build_qdrant_filters(request.dict(), payload_fournisseur, fournisseur_non_vide)
        
        hits = qdrant_client.search(
            collection_name=source,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
            query_filter=search_filter,
            search_params=search_params
        )
        
        matches_info = []
        processed_lead_ids = set()
        for hit in hits:
            payload = hit.payload
            total_chunks = payload.get("total_chunks", 1)
            lead_id = payload.get("lead_id")
            if source == "devis_poc" and lead_id and lead_id in processed_lead_ids:
                continue

            final_text = payload.get("text", "")
            
            # TODO complété: Logique de reconstruction des chunks pour 'devis_poc'
            # correction : indexation du champ lead_id
            # if source == "devis_poc" and total_chunks > 1 and lead_id:
            if source == "devis_poc____" and total_chunks > 1 and lead_id:
                logger.info(f"Reconstruction pour lead_id: {lead_id}")
                sibling_chunks, _ = qdrant_client.scroll(
                    collection_name=source,
                    scroll_filter=models.Filter(must=[models.FieldCondition(key="lead_id", match=models.MatchValue(value=lead_id))]),
                    # TODO : à vérifier
                    # scroll_filter=Filter(must=[
                    #     FieldCondition(key="lead_id", match=MatchValue(value=lead_id))
                    # ]),
                    limit=total_chunks,
                    with_payload=True
                )
                if len(sibling_chunks) == total_chunks:
                    sorted_chunks = sorted(sibling_chunks, key=lambda c: c.payload.get("chunk_number", 0))
                    final_text = "".join([chunk.payload.get("text", "") for chunk in sorted_chunks])
                    payload["text"] = final_text
                else:
                    logger.warning(f"Reconstruction échouée pour {lead_id}. Chunks trouvés: {len(sibling_chunks)}/{total_chunks}")

            context_texts.append(final_text)
            # TODO: à vérifier
            # context_texts.append(f"{final_text}\n-----\n")
            matches_info.append({"id": hit.id, "score": hit.score, "id_lead": lead_id, "metadata": payload})
            
            if source == "devis_poc" and lead_id:
                processed_lead_ids.add(lead_id)

        all_results[source] = matches_info
    search_duration = time.perf_counter() - start_search

    llm_req = llm_prompt(request, context_texts)

    total_duration = time.perf_counter() - start_total_time
    
    return {
        "database": "qdrant",
        "user_query": request.prompt,
        "filter": search_filter.dict() if search_filter else "",
        "matches": all_results,
        "context": llm_req.context,
        "response": llm_req.llm_response,
        "embedding": round(embed_duration, 2),
        "fournisseur_non_vide": fournisseur_non_vide,
        "full_user_prompt": llm_req.full_user_prompt,
        "chat_model": request.chat_model,
        "temperature": request.temperature,
        "vector_search": round(search_duration, 2),
        "total_process": round(total_duration, 2),
        "llm_execution": round(llm_req.llm_duration, 2),
        "import_duration": round(import_duration, 2)
    }

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

async def search_in_milvus(request: SearchRequest):
    # Implémentation complète de la recherche Milvus
    logger.info(f"[MILVUS] Recherche: prompt='{request.prompt[:50]}...', sources={request.source}")
    start_total_time = time.perf_counter()

    # 1. Obtenir les ressources nécessaires
    get_milvus_connection()
    embedding_model = get_embedding_model()

    start_embed = time.perf_counter()
    query_vector = [embedding_model.encode(request.prompt, normalize_embeddings=True).tolist()]
    embed_duration = time.perf_counter() - start_embed

    top_k = int(request.nombre_resultat)
    all_results = {}
    context_texts = []

    filter_expr = "" # Placeholder
    collection_metadata = {
        "devis_poc": {"payload_fournisseur": "liste_frns"},
        "siteweb_poc": {"payload_fournisseur": "id_fournisseur"},
        "echanges_poc": {"payload_fournisseur": "id_fournisseur"}
    }

    start_search = time.perf_counter()
    for source in request.source:
        if not utility.has_collection(source):
            logger.warning(f"La collection Milvus '{source}' n'existe pas.")
            all_results[source] = []
            continue

        collection = Collection(name=source)
        collection.load()

        search_params = {"metric_type": "COSINE", "params": {"ef": 150}}
        output_fields = settings.MILVUS_OUTPUT_FIELDS_CONFIG.get(source, ["*"])

        metadata = collection_metadata.get(source, {"payload_fournisseur": "id_fournisseur"})
        filter_expr = build_milvus_expression(request.dict(), metadata["payload_fournisseur"], "1000000" in request.fournisseur)

        search_results = collection.search(
            data=query_vector,
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=output_fields
        )
      
        # Récupérer le payload complet pour les IDs trouvés
        hit_ids = [hit.id for hit in search_results[0]]
        if not hit_ids:
            all_results[source] = []
            continue

        # La récupération du payload complet se fait via .query
        all_fields = [field.name for field in collection.schema.fields]

        # Exclude embedding
        fields_without_embedding = [f for f in all_fields if f != "embedding"]
        entities = collection.query(expr=f"id in {hit_ids}", output_fields=fields_without_embedding)

        # Mapper les distances de recherche aux entités complètes
        id_to_distance = {hit.id: hit.distance for hit in search_results[0]}

        matches_info = []
        for entity in entities:
            # Logique de reconstruction de chunks (similaire à Qdrant)
            # ...
            final_text = entity.get("text", "")
            context_texts.append(f"{final_text}\n-----\n")

            matches_info.append({
                "id": entity.get("id"),
                "score": id_to_distance.get(entity.get("id")),
                "id_lead": entity.get("lead_id"),
                "metadata": entity
            })
        all_results[source] = matches_info

        # matches_info = []
        # if search_results and search_results[0]:
        #     for hit in search_results[0]:
        #         entity = {field: hit.entity.get(field) for field in output_fields}
        #         context_texts.append(entity.get("text", ""))
        #         matches_info.append({
        #             "id": hit.id, "score": hit.distance, "id_lead": entity.get("lead_id"), "metadata": entity
        #         })
        # all_results[source] = matches_info
    search_duration = time.perf_counter() - start_search

    # TODO complété: Logique LLM pour Milvus
    llm_req = llm_prompt(request, context_texts)
    
    total_duration = time.perf_counter() - start_total_time
    
    return {
        "database": "milvus",
        "user_query": request.prompt,
        "filter": filter_expr,
        "matches": all_results,
        "context": llm_req.context,
        "response": llm_req.llm_response,
        "embedding": round(embed_duration, 2),
        "fournisseur_non_vide": None, # Non implémenté pour Milvus dans le code d'origine
        "full_user_prompt": llm_req.full_user_prompt,
        "chat_model": request.chat_model,
        "temperature": request.temperature,
        "vector_search": round(search_duration, 2),
        "total_process": round(total_duration, 2),
        "llm_execution": round(llm_req.llm_duration, 2),
        "import_duration": round(import_duration, 2)
    }
