from dataclasses import field
from functools import lru_cache
import os
import logging
from pymilvus import connections, Collection, DataType, utility
from domain.search_result import SearchResultEntity

MILVUS_HOST = os.getenv("ZILLIZ_URI")
MILVUS_PORT = os.getenv("ZILLIZ_PORT", "19530")

class MilvusClient:
    def __init__(self):
        self._loaded_collections = {}
        try:
            logging.info(f"Connexion à Milvus sur {MILVUS_HOST}:{MILVUS_PORT}")
            connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
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
                logging.info(f"Chargement de la collection '{collection_name}' en mémoire...")
                collection = Collection(name=collection_name)
                collection.load()
                self._loaded_collections[collection_name] = collection
                logging.info(f"Collection '{collection_name}' chargée.")
            else:
                raise ValueError(f"La collection '{collection_name}' n'existe pas dans Milvus.")
        return self._loaded_collections[collection_name]

    @lru_cache(maxsize=32)
    def get_field_type_map(self, collection_name: str) -> dict:
        """
        Retrieves the schema for a given collection and returns a dictionary
        mapping field names to their pymilvus DataType.
        """
        try:
            collection = Collection(name=collection_name)
            return {str(field.name): str(field.dtype) for field in collection.schema.fields}
        except Exception as e:
            logging.error(f"Erreur lors de la récupération de champs de la collection '{collection_name}': {e}", exc_info=True)
            return {}
    def _serialize_entity(self, entity, source: str = "produits") -> dict:
        """
        Converts a Milvus search result entity to a JSON-serializable dictionary.
        Handles special types like RepeatedScalarContainer for ARRAY fields by converting them to lists.
        """
        if hasattr(entity, 'to_dict'):
            entity = entity.to_dict()

        serializable_dict = {}
        fields = self.get_field_type_map(source)
        for key, value in entity.items():
            if hasattr(value, '__iter__') and not isinstance(value, (str, bytes, dict)):
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
    
    def classic_search(self, collection_name: str, expr: str, limit: int, output_fields: list[str]) -> list[SearchResultEntity]:
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
                output_fields = [f for f in all_fields if f != "embedding"]
                
            if 'text' not in output_fields:
                output_fields.append('text')


            results = collection.query(
                expr=expr,
                limit=limit,
                output_fields=output_fields
            )

            # Formatage des résultats en entités du domaine (sans score, car query n'en retourne pas)
            domain_results = []
            for hit in results:
                domain_results.append(SearchResultEntity(
                    id=hit.pop(collection.primary_field.name, ""), # Gère le cas où la clé primaire est retournée
                    score=0.0, # Pas de score de similarité pour une requête classique
                    metadata={"id": hit.pop(collection.primary_field.name, ""), "entity": self._serialize_entity(hit, collection_name)},
                    source=collection_name
                ))
            return domain_results

        except Exception as e:
            logging.error(f"Erreur lors de la recherche classique dans Milvus sur '{collection_name}': {e}", exc_info=True)
            return []
    
    def search(self, collection_name: str, vector: list[float], top_k: int, **kwargs) -> list[SearchResultEntity]:
        try:
            if not connections.has_connection("default"):
                self.__init__() # Tentative de reconnexion

            if collection_name == "pjechanges":
                logging.info(f"Param search : {kwargs}")

            collection = self._ensure_collection_loaded(collection_name)

            fields_without_embedding = []
            if kwargs.get("output_fields"):
                fields_without_embedding = [f for f in kwargs.get("output_fields") if f != "embedding"]
            else:
                all_fields = [field.name for field in collection.schema.fields]
                fields_without_embedding = [f for f in all_fields if f != "embedding"]
                
            if 'text' not in fields_without_embedding:
                fields_without_embedding.append('text')
            
            # Définition des paramètres de recherche
            search_params = {"metric_type": "COSINE", "params": {"ef": self._ef_search(top_k)}}
            
            results = collection.search(
                data=[vector],
                anns_field="embedding", # Le nom du champ contenant les vecteurs
                param=search_params,
                limit=top_k,
                output_fields=kwargs.get("fields", fields_without_embedding), # Le champ contenant l'ID du document
                expr=kwargs.get("expr", None)
            )


            # Formatage des résultats en entités du domaine
            domain_results = []
            
            is_context_collection = (collection_name == "pjechanges" and kwargs.get("get_n_chunks_pj", False))

            if is_context_collection:
                seen_ids = set()
                candidates = []       # Liste temporaire pour garder l'ordre et les infos
                context_targets = []  # Liste des tuples (fichier_source, chunk_number) à aller chercher
                

                for hit in results[0]:
                    # Dédoublonnage par ID Milvus
                    if hit.id in seen_ids:
                        continue
                    seen_ids.add(hit.id)
                    
                    # On s'arrête dès qu'on a atteint le top_k désiré après dédoublonnage
                    if len(candidates) >= top_k:
                        break

                    entity_data = hit.entity
                    
                    # Stockage intermédiaire
                    candidate = {
                        "hit": hit,
                        "fichier_source": entity_data.get('fichier_source'),
                        "chunk_number": entity_data.get('chunk_number'),
                        "context_pre": None,
                        "context_post": None
                    }
                    candidates.append(candidate)

                    # Calcul des cibles pour le contexte (seulement pour pjechanges)
                    if is_context_collection:
                        src = candidate["fichier_source"]
                        num = candidate["chunk_number"]
                        
                        if src is not None and num is not None:
                            # Préparer la récupération de n-1 (si n > 0)
                            if num > 0:
                                context_targets.append((src, num - 1))
                            # Préparer la récupération de n+1
                            context_targets.append((src, num + 1))

                # 5. Récupération des chunks adjacents (Batch Query)
                # Uniquement si on a des cibles et qu'on est sur la bonne collection
                context_map = {} # Clé: (fichier_source, chunk_number) -> Valeur: Texte

                if context_targets:
                    # Pour gérer le top_k=200, on batch les requêtes pour éviter
                    # l'erreur "expression too long" de Milvus.
                    BATCH_SIZE = 50 
                    
                    # On déduplique les cibles de contexte (au cas où deux résultats demandent le même voisin)
                    unique_targets = list(set(context_targets))
                    
                    for i in range(0, len(unique_targets), BATCH_SIZE):
                        batch = unique_targets[i : i + BATCH_SIZE]
                        expr_parts = []
                        
                        for src, num in batch:
                            # Echappement des quotes simples dans le nom de fichier au cas où
                            safe_src = src.replace("'", "\\'")
                            expr_parts.append(f"(fichier_source == '{safe_src}' && chunk_number == {num})")
                        
                        full_expr = " || ".join(expr_parts)
                        
                        try:
                            context_hits = collection.query(
                                expr=full_expr,
                                output_fields=fields_without_embedding
                            )
                            
                            for c in context_hits:
                                key = (c['fichier_source'], c['chunk_number'])
                                context_map[key] = c['text']
                        except Exception as e:
                            logging.warning(f"Erreur lors de la récupération d'un batch de contexte : {e}")
                            # On continue même si un batch échoue

                # 6. Formatage final des entités
                for item in candidates:
                    hit = item['hit']
                    
                    # Injection du contexte si disponible
                    if is_context_collection:
                        src = item['fichier_source']
                        num = item['chunk_number']
                        
                        # Récupération depuis la map (renvoie None si non trouvé)
                        txt_pre = context_map.get((src, num - 1))
                        txt_post = context_map.get((src, num + 1))
                    else:
                        txt_pre = None
                        txt_post = None

                    # Construction des métadonnées
                    metadata = self._serialize_entity(hit.entity, collection_name)
                    
                    # Vous pouvez soit les mettre dans metadata, soit passer des arguments au constructeur
                    # Option A : Dans metadata
                    metadata['context_pre'] = txt_pre
                    metadata['context_post'] = txt_post

                    domain_results.append(SearchResultEntity(
                        id=hit.id,
                        score=hit.distance,
                        metadata=metadata,
                        source=collection_name
                    ))
            else:
                for hit in results[0]:
                    domain_results.append(SearchResultEntity(
                        id=hit.id,
                        score=hit.distance,
                        metadata=self._serialize_entity(hit.entity, collection_name),
                        source=collection_name
                    ))

            return domain_results

        except Exception as e:
            logging.error(f"Erreur lors de la recherche dans Milvus sur la collection '{collection_name}': {e}", exc_info=True)
            return []
