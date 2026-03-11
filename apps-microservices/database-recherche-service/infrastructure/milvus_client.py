from dataclasses import field
from functools import lru_cache
import os
import logging
from pymilvus import (
    connections,
    Collection,
    DataType,
    utility,
    AnnSearchRequest,
    WeightedRanker,
    RRFRanker,
)
from domain.search_result import SearchResultEntity

MILVUS_HOST = os.getenv("ZILLIZ_URI")
MILVUS_PORT = os.getenv("ZILLIZ_PORT", "19530")
MILVUS_USER = os.getenv("ZILLIZ_USER")
MILVUS_PASSWORD = os.getenv("ZILLIZ_PASSWORD")

# Configuration des collections (inchangée)
COLLECTION_CONFIG = {
    "pjechanges": {
        "group_field": "fichier_source",  # Identifiant du document
        "seq_field": "chunk_number",  # Identifiant de la séquence (0, 1, 2...)
    },
    "produits_3": {"group_field": "id_produit", "seq_field": "chunk_number"},
    "devis": {"group_field": "lead_id", "seq_field": "chunk_number"},
    "echanges": {"group_field": "conversation_id", "seq_field": "chunk_number"},
    "siteweb_2": {"group_field": "url", "seq_field": "chunk_number"},
}


class MilvusClient:
    def __init__(self):
        self._loaded_collections = {}
        try:
            logging.info(f"Connexion à Milvus sur {MILVUS_HOST}:{MILVUS_PORT}")
            logging.info(f"Connexion à Milvus sur {MILVUS_USER}:{MILVUS_PASSWORD}")
            connections.connect(
                "default",
                host=MILVUS_HOST,
                port=MILVUS_PORT,
                user=MILVUS_USER,
                password=MILVUS_PASSWORD,
            )
        except Exception as e:
            logging.error(f"Impossible de se connecter à Milvus: {e}", exc_info=True)
            # Dans une application réelle, une stratégie de retry serait appropriée.
            raise

    def _ensure_collection_loaded(self, collection_name: str):
        """
        Vérifie si une collection est chargée en mémoire, et la charge si ce n'est pas le cas.
        C'est la fonction clé pour éviter les rechargements coûteux.
        """
        if collection_name not in self._loaded_collections:
            if utility.has_collection(collection_name):
                logging.info(
                    f"Chargement de la collection '{collection_name}' en mémoire..."
                )
                collection = Collection(name=collection_name)
                collection.load()
                self._loaded_collections[collection_name] = collection
                logging.info(f"Collection '{collection_name}' chargée.")
            else:
                raise ValueError(
                    f"La collection '{collection_name}' n'existe pas dans Milvus."
                )
        return self._loaded_collections[collection_name]

    @lru_cache(maxsize=32)
    def get_field_type_map(self, collection_name: str) -> dict:
        """
        Retrieves the schema for a given collection and returns a dictionary
        mapping field names to their pymilvus DataType.
        """
        try:
            collection = Collection(name=collection_name)
            return {
                str(field.name): str(field.dtype) for field in collection.schema.fields
            }
        except Exception as e:
            logging.error(
                f"Erreur lors de la récupération de champs de la collection '{collection_name}': {e}",
                exc_info=True,
            )
            return {}

    def _serialize_entity(self, entity, source: str = "produits") -> dict:
        """
        Converts a Milvus search result entity to a JSON-serializable dictionary.
        Handles special types like RepeatedScalarContainer for ARRAY fields by converting them to lists.
        """
        if hasattr(entity, "to_dict"):
            entity = entity.to_dict()

        serializable_dict = {}
        fields = self.get_field_type_map(source)
        for key, value in entity.items():
            if hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
                serializable_dict[key] = list(value)
            else:
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if fields.get(sub_key) == DataType.ARRAY:
                            value[sub_key] = list(sub_value)
                serializable_dict[key] = value
        return serializable_dict

    def _ef_search(self, nb_chunk: int) -> int:
        """Calcule la valeur ef_search pour Qdrant/Milvus en fonction du nombre de chunks."""
        return 300 if nb_chunk <= 150 else nb_chunk * 2
        # return 5000

    @lru_cache(maxsize=32)
    def _get_embedding_index_type(
        self, collection_name: str, field_name: str = "embedding"
    ) -> str:
        """
        Retrieves the index type for the specified vector field of a collection.
        Returns the index type string (e.g., 'HNSW', 'IVF_FLAT', 'FLAT', 'AUTOINDEX', 'DISKANN', 'SCANN').
        Returns 'UNKNOWN' if the index type cannot be determined.
        """
        try:
            collection = Collection(name=collection_name)
            indexes = collection.indexes
            for index in indexes:
                if index.field_name == field_name:
                    index_type = index.params.get("index_type", "UNKNOWN")
                    logging.info(
                        f"[_get_embedding_index_type] Collection '{collection_name}', "
                        f"field '{field_name}': index_type='{index_type}'"
                    )
                    return index_type
            logging.warning(
                f"[_get_embedding_index_type] No index found for field '{field_name}' "
                f"in collection '{collection_name}'"
            )
            return "UNKNOWN"
        except Exception as e:
            logging.error(
                f"[_get_embedding_index_type] Error retrieving index type for "
                f"'{collection_name}.{field_name}': {e}",
                exc_info=True,
            )
            return "UNKNOWN"

    def _build_dense_search_params(
        self,
        collection_name: str,
        top_k: int,
        ef: int | None = None,
        radius: float | None = None,
        range_filter: float | None = None,
    ) -> dict:
        """
        Builds the dense search params dict based on the detected index type
        of the 'embedding' field.

        Supported index types and their params:
        - HNSW       → {"ef": value}
        - IVF_FLAT / IVF_SQ8 / IVF_PQ → {"nprobe": value}
        - FLAT       → {} (brute-force, no special params)
        - AUTOINDEX  → {} (Milvus/Zilliz auto-tunes)
        - DISKANN    → {"search_list": value}
        - SCANN      → {"nprobe": value, "reorder_k": value}
        - GPU_CAGRA  → {"itopk_size": value, "search_width": 4}
        """
        index_type = self._get_embedding_index_type(collection_name, "embedding")

        if index_type == "HNSW":
            effective_ef = ef if ef is not None else self._ef_search(top_k)
            inner_params = {"ef": effective_ef}
        elif index_type in ("IVF_FLAT", "IVF_SQ8", "IVF_PQ"):
            # nprobe: number of clusters to search. Higher = better recall, slower.
            nprobe = ef if ef is not None else max(16, min(top_k * 2, 1024))
            inner_params = {"nprobe": nprobe}
        elif index_type == "SCANN":
            nprobe = ef if ef is not None else max(16, min(top_k * 2, 1024))
            reorder_k = max(top_k * 10, 200)
            inner_params = {"nprobe": nprobe, "reorder_k": reorder_k}
        elif index_type == "DISKANN":
            search_list = ef if ef is not None else max(top_k * 2, 100)
            inner_params = {"search_list": search_list}
        elif index_type == "GPU_CAGRA":
            itopk_size = ef if ef is not None else max(top_k * 2, 128)
            inner_params = {"itopk_size": itopk_size, "search_width": 4}
        elif index_type in ("FLAT", "AUTOINDEX"):
            inner_params = {}
        else:
            # UNKNOWN or unsupported: default to HNSW-like params as safe fallback
            logging.warning(
                f"[_build_dense_search_params] Unknown index type '{index_type}' "
                f"for collection '{collection_name}'. Falling back to HNSW params."
            )
            effective_ef = ef if ef is not None else self._ef_search(top_k)
            inner_params = {"ef": effective_ef}

        dense_search_params = {
            "metric_type": "COSINE",
            "params": inner_params,
        }

        if radius is not None:
            dense_search_params["radius"] = radius
        if range_filter is not None:
            dense_search_params["range_filter"] = range_filter

        logging.info(
            f"[_build_dense_search_params] Collection '{collection_name}', "
            f"index_type='{index_type}', params={dense_search_params}"
        )

        return dense_search_params

    def classic_search(
        self, collection_name: str, expr: str, limit: int, output_fields: list[str]
    ) -> list[SearchResultEntity]:
        """
        Exécute une requête de type 'query' sur Milvus en utilisant une expression de filtre.
        """
        try:
            if not connections.has_connection("default"):
                self.__init__()

            collection = self._ensure_collection_loaded(collection_name)

            # Si output_fields n'est pas spécifié, on récupère tout sauf l'embedding
            if not output_fields:
                all_fields = [field.name for field in collection.schema.fields]
                output_fields = [
                    f for f in all_fields if f not in ("embedding", "sparse_embedding")
                ]

            if "text" not in output_fields:
                output_fields.append("text")

            results = collection.query(
                expr=expr, limit=limit, output_fields=output_fields
            )

            # Formatage des résultats en entités du domaine (sans score, car query n'en retourne pas)
            domain_results = []
            for hit in results:
                domain_results.append(
                    SearchResultEntity(
                        id=hit.pop(
                            collection.primary_field.name, ""
                        ),  # Gère le cas où la clé primaire est retournée
                        score=0.0,  # Pas de score de similarité pour une requête classique
                        metadata={
                            "id": hit.pop(collection.primary_field.name, ""),
                            "entity": self._serialize_entity(hit, collection_name),
                        },
                        source=collection_name,
                    )
                )
            return domain_results

        except Exception as e:
            logging.error(
                f"Erreur lors de la recherche classique dans Milvus sur '{collection_name}': {e}",
                exc_info=True,
            )
            return []

    def search(
        self, collection_name: str, vector: list[float], top_k: int, **kwargs
    ) -> list[SearchResultEntity]:
        try:
            if not connections.has_connection("default"):
                self.__init__()

            collection = self._ensure_collection_loaded(collection_name)

            # Gestion des champs de sortie
            fields_without_embedding = []
            if kwargs.get("output_fields"):
                fields_without_embedding = [
                    f
                    for f in kwargs.get("output_fields")
                    if f not in ("embedding", "sparse_embedding")
                ]
            else:
                all_fields = [field.name for field in collection.schema.fields]
                fields_without_embedding = [
                    f for f in all_fields if f not in ("embedding", "sparse_embedding")
                ]

            if "text" not in fields_without_embedding:
                fields_without_embedding.append("text")

            # --- 1. Recherche Vectorielle ---
            search_params = self._build_dense_search_params(
                collection_name=collection_name,
                top_k=top_k,
            )

            results = collection.search(
                data=[vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=kwargs.get("fields", fields_without_embedding),
                expr=kwargs.get("expr", None),
            )

            domain_results = []

            # Mode de contexte : 'adjacent', 'full', ou None
            context_mode = kwargs.get("context_mode")
            col_conf = COLLECTION_CONFIG.get(collection_name)

            # Si pas de contexte demandé ou config inexistante, retour simple
            if not context_mode or not col_conf:
                for hit in results[0]:
                    domain_results.append(
                        SearchResultEntity(
                            id=hit.id,
                            score=hit.distance,
                            metadata=self._serialize_entity(
                                hit.entity, collection_name
                            ),
                            source=collection_name,
                        )
                    )
                return domain_results

            # --- 2. Préparation du contexte ---
            group_field = col_conf["group_field"]
            seq_field = col_conf["seq_field"]

            seen_ids = set()
            candidates = []
            context_queries = set()  # Pour stocker les IDs ou tuples à récupérer

            for hit in results[0]:
                if hit.id in seen_ids:
                    continue
                seen_ids.add(hit.id)

                if len(candidates) >= top_k:
                    break

                entity_data = hit.entity
                group_val = entity_data.get(group_field)
                seq_val = entity_data.get(seq_field)

                candidate = {"hit": hit, "group_val": group_val, "seq_val": seq_val}
                candidates.append(candidate)

                if group_val is not None:
                    if context_mode == "adjacent" and seq_val is not None:
                        # Cas N-1 et N+1
                        if seq_val > 0:
                            context_queries.add((group_val, seq_val - 1))
                        context_queries.add((group_val, seq_val + 1))

                    elif context_mode == "full":
                        # Cas Full : on veut tout le document identifié par group_val
                        context_queries.add(group_val)

            # --- 3. Récupération Batch des Contextes ---
            context_map = {}

            if context_queries:
                query_list = list(context_queries)
                BATCH_SIZE = 50

                for i in range(0, len(query_list), BATCH_SIZE):
                    batch = query_list[i : i + BATCH_SIZE]
                    full_expr = ""

                    # Construction de la requête Milvus
                    if context_mode == "adjacent":
                        expr_parts = []
                        for g_val, s_val in batch:
                            safe_g_val = (
                                str(g_val).replace("'", "\\'")
                                if isinstance(g_val, str)
                                else g_val
                            )
                            g_str = (
                                f"'{safe_g_val}'"
                                if isinstance(g_val, str)
                                else safe_g_val
                            )
                            expr_parts.append(
                                f"({group_field} == {g_str} && {seq_field} == {s_val})"
                            )
                        full_expr = " || ".join(expr_parts)

                    elif context_mode == "full":
                        expr_parts = []
                        for g_val in batch:
                            safe_g_val = (
                                str(g_val).replace("'", "\\'")
                                if isinstance(g_val, str)
                                else g_val
                            )
                            g_str = (
                                f"'{safe_g_val}'"
                                if isinstance(g_val, str)
                                else safe_g_val
                            )
                            expr_parts.append(f"{group_field} == {g_str}")
                        full_expr = " || ".join(expr_parts)

                    # Exécution
                    if full_expr:
                        try:
                            context_hits = collection.query(
                                expr=full_expr, output_fields=fields_without_embedding
                            )

                            for c in context_hits:
                                c_group = c.get(group_field)
                                c_seq = c.get(seq_field)

                                if context_mode == "adjacent":
                                    key = (c_group, c_seq)
                                    context_map[key] = c.get("text")

                                elif context_mode == "full":
                                    # On groupe tous les chunks par ID de document
                                    if c_group not in context_map:
                                        context_map[c_group] = []
                                    context_map[c_group].append(c)

                        except Exception as e:
                            logging.warning(
                                f"Erreur batch contexte ({context_mode}): {e}"
                            )

            # --- 4. Assemblage Final ---
            for item in candidates:
                hit = item["hit"]
                metadata = self._serialize_entity(hit.entity, collection_name)

                g_val = item["group_val"]
                s_val = item["seq_val"]

                if context_mode == "adjacent":
                    # Ajout simple de n-1 et n+1
                    metadata["context_pre"] = context_map.get((g_val, s_val - 1))
                    metadata["context_post"] = context_map.get((g_val, s_val + 1))

                elif context_mode == "full":
                    # Récupération de tous les chunks associés à ce fichier
                    all_chunks = context_map.get(g_val, [])

                    # On itère sur tous les chunks trouvés pour ce document
                    for chunk in all_chunks:
                        # On récupère le numéro (ex: 1, 2, 3...)
                        c_num = chunk.get(seq_field)
                        c_txt = chunk.get("text")

                        if c_num is not None:
                            # Création dynamique : context_1, context_2, etc.
                            metadata[f"context_{c_num}"] = c_txt

                domain_results.append(
                    SearchResultEntity(
                        id=hit.id,
                        score=hit.distance,
                        metadata=metadata,
                        source=collection_name,
                    )
                )

            return domain_results

        except Exception as e:
            logging.error(f"Search failed: {e}")
            return []

    def hybrid_search(
        self,
        collection_name: str,
        dense_vector: list[float],
        query_text: str,
        top_k: int,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        # --- Paramètres d'exploration pour optimiser la pertinence ---
        ef: int | None = None,
        radius: float | None = None,
        range_filter: float | None = None,
        drop_ratio_search: float = 0.0,
        dense_limit_multiplier: int = 1,
        ranker_type: str = "weighted",
        rrf_k: int = 60,
        **kwargs,
    ) -> list[SearchResultEntity]:
        """
        Recherche hybride combinant recherche vectorielle dense (COSINE) et
        recherche full-text BM25 via le champ sparse de Milvus.

        Prérequis collection:
        - Champ 'embedding' (FLOAT_VECTOR) pour la recherche dense
        - Champ 'sparse_embedding' (SPARSE_FLOAT_VECTOR) avec Function(BM25)
          liée au champ 'text' (VARCHAR)

        Paramètres d'exploration (sacrifier le temps calcul pour la pertinence):
        ----------
        ef : int | None
            Contrôle la largeur d'exploration du graphe HNSW.
            - None  → utilise _ef_search(top_k) [défaut actuel, ~300]
            - 2000+ → explore bien plus de nœuds, meilleur rappel
            - 10000+→ rappel quasi-exhaustif, latence élevée
            IMPORTANT: C'est le levier principal pour la pertinence sur 1.8M docs.
            Avec ef=300, HNSW ne considère que ~300 candidats depuis le point
            d'entrée du graphe, ce qui explique pourquoi des résultats pertinents
            plus profonds dans le graphe ne remontent pas.

        radius : float | None
            Seuil de similarité minimum (COSINE: 0.0 à 1.0).
            Seuls les résultats avec score >= radius sont retournés.
            Ex: radius=0.5 élimine les résultats peu similaires.

        range_filter : float | None
            Seuil de similarité maximum (COSINE: 0.0 à 1.0).
            Combiné avec radius, crée une bande de scores [radius, range_filter].
            Pour COSINE: range_filter > radius requis.
            Ex: radius=0.3, range_filter=0.9 → résultats entre 0.3 et 0.9.

        drop_ratio_search : float
            Pour la recherche BM25 sparse : proportion des poids de termes les
            plus faibles à ignorer dans le vecteur de requête.
            - 0.0 → garde tous les termes (précision max, défaut)
            - 0.1 → ignore les 10% de termes les plus faibles (plus rapide)

        dense_limit_multiplier : int
            Facteur de sur-récupération pour chaque sous-requête.
            Chaque AnnSearchRequest récupère top_k * multiplier candidats.
            Le résultat final est toujours limité à top_k après fusion.
            - 1  → comportement actuel
            - 3+ → donne au ranker plus de candidats pour une meilleure fusion

        ranker_type : str
            Stratégie de fusion des résultats:
            - "weighted" → WeightedRanker (fusion par scores pondérés, défaut)
            - "rrf"      → RRFRanker (Reciprocal Rank Fusion, fusion par rangs,
                           souvent plus robuste quand on mélange des métriques
                           hétérogènes comme COSINE + BM25)

        rrf_k : int
            Constante de lissage pour RRFRanker (utilisé seulement si ranker_type="rrf").
            - 60  → défaut, bon équilibre
            - 10  → favorise fortement les résultats en haut de chaque liste
            - 100 → lissage plus fort, poids plus égal entre les rangs
        """
        try:
            if not connections.has_connection("default"):
                self.__init__()

            collection = self._ensure_collection_loaded(collection_name)

            # Gestion des champs de sortie
            fields_without_embedding = []
            if kwargs.get("output_fields"):
                fields_without_embedding = [
                    f
                    for f in kwargs.get("output_fields")
                    if f not in ("embedding", "sparse_embedding")
                ]
            else:
                all_fields = [field.name for field in collection.schema.fields]
                fields_without_embedding = [
                    f for f in all_fields if f not in ("embedding", "sparse_embedding")
                ]

            if "text" not in fields_without_embedding:
                fields_without_embedding.append("text")

            # Calcul du limit pour les sous-requêtes (sur-récupération)
            sub_limit = top_k * dense_limit_multiplier

            # --- 1. Requête de recherche dense (COSINE sur le champ 'embedding') ---
            dense_search_params = self._build_dense_search_params(
                collection_name=collection_name,
                top_k=sub_limit,
                ef=ef,
                radius=radius,
                range_filter=range_filter,
            )

            logging.info(
                f"[hybrid_search] Dense params: {dense_search_params}, "
                f"sub_limit={sub_limit}"
            )

            dense_request = AnnSearchRequest(
                data=[dense_vector],
                anns_field="embedding",
                param=dense_search_params,
                limit=sub_limit,
                expr=kwargs.get("expr", None),
            )

            # --- 2. Requête de recherche sparse / full-text BM25 ---
            sparse_search_params = {
                "metric_type": "BM25",
                "params": {"drop_ratio_search": drop_ratio_search},
            }

            logging.info(
                f"[hybrid_search] Sparse params: drop_ratio_search={drop_ratio_search}, "
                f"sub_limit={sub_limit}"
            )

            sparse_request = AnnSearchRequest(
                data=[query_text],
                anns_field="sparse_embedding",
                param=sparse_search_params,
                limit=sub_limit,
                expr=kwargs.get("expr", None),
            )

            # --- 3. Recherche hybride avec fusion ---
            if ranker_type == "rrf":
                ranker = RRFRanker(k=rrf_k)
                logging.info(f"[hybrid_search] Ranker: RRFRanker(k={rrf_k})")
            else:
                ranker = WeightedRanker(dense_weight, sparse_weight)
                logging.info(
                    f"[hybrid_search] Ranker: WeightedRanker("
                    f"dense={dense_weight}, sparse={sparse_weight})"
                )

            results = collection.hybrid_search(
                reqs=[dense_request, sparse_request],
                rerank=ranker,
                limit=top_k,
                output_fields=fields_without_embedding,
            )

            # --- 4. Construction des résultats du domaine ---
            domain_results = []
            for hit in results[0]:
                domain_results.append(
                    SearchResultEntity(
                        id=hit.id,
                        score=hit.distance,
                        metadata=self._serialize_entity(hit.entity, collection_name),
                        source=collection_name,
                    )
                )

            logging.info(
                f"[hybrid_search] Returned {len(domain_results)} results "
                f"(requested top_k={top_k})"
            )

            return domain_results

        except Exception as e:
            logging.error(
                f"Hybrid search failed on '{collection_name}': {e}", exc_info=True
            )
            return []
