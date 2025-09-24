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
        serializable_dict = {}
        fields = self.get_field_type_map(source)
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
                    metadata=self._serialize_entity(hit.entity, collection_name),
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

            collection = self._ensure_collection_loaded(collection_name)

            all_fields = [field.name for field in collection.schema.fields]
            fields_without_embedding = [f for f in all_fields if f != "embedding"]
            
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
