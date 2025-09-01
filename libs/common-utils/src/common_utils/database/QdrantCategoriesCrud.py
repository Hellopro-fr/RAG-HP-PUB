import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from common_utils.database.config.settings import Configuration, settings

import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    PointStruct,
    HnswConfigDiff,
    PayloadSchemaType
)

@dataclass
class ModelConfig:
    model_id: str = settings.MODEL
    collection_name: str = "categories"
    dimension: int = 1024


class QdrantCategoriesCrud:
    def __init__(self, config: Configuration = settings, **kwargs: Any):
        self.config = config
        self.collection: Optional[str] = None
        # if not self.config.QDRANT_HOST_URL or not self.config.QDRANT_PORT:
        if not self.config.QDRANT_HOST_URL or not self.config.QDRANT_API_KEY:
            raise ValueError("Qdrant host et port/api_key doivent être définis dans l'environnement.")
        self.logger = kwargs.get('logger', logging)
        self.client = QdrantClient(
            url=self.config.QDRANT_HOST_URL,
            api_key=self.config.QDRANT_API_KEY
        )

    def _get_or_create_collection(self, model_config: ModelConfig):
        collection_name = model_config.collection_name
        model_key = model_config.model_id

        if self.config.RECREATE_COLLECTIONS:
            try:
                self.client.delete_collection(collection_name=collection_name)
                self.logger.warning(f"[{model_key}] Collection supprimée : '{collection_name}'")
            except Exception:
                pass

        # Création si non existante
        collections = [c.name for c in self.client.get_collections().collections]
        if collection_name not in collections:
            self.logger.info(f"Collection '{collection_name}' non trouvée. Création...")
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=model_config.dimension, distance=Distance.COSINE),
				hnsw_config=HnswConfigDiff(
					m=32,
					ef_construct=300
				),
                shard_number=2,
                replication_factor= 1 #normalement ça devrait être 3 mais pour l'insertion massive on le garde à 1 d'abord
            )
            self.logger.info(f"[{model_key}] ✓ Collection '{collection_name}' créée.")
        else:
            self.logger.info(f"[{model_key}] Connexion à la collection existante : '{collection_name}'")


        # self.client.create_payload_index(collection_name, field_name="categorie", field_schema=PayloadSchemaType.KEYWORD)
        self.client.create_payload_index(collection_name, field_name="id_categorie", field_schema=PayloadSchemaType.KEYWORD)
        # self.client.create_payload_index(collection_name, field_name="fournisseur", field_schema=PayloadSchemaType.KEYWORD)
        # self.client.create_payload_index(collection_name, field_name="affichage", field_schema=PayloadSchemaType.KEYWORD)
        # self.client.create_payload_index(collection_name, field_name="etat", field_schema=PayloadSchemaType.KEYWORD)
        # self.client.create_payload_index(collection_name, field_name="page_type", field_schema=PayloadSchemaType.KEYWORD)

        self.collection = collection_name
        return collection_name

    def insert_categories(self, categorie: Dict[str, Any]) -> Dict[str, Any]:
        datas = categorie
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            self._get_or_create_collection(model_config)

            if not datas or self.collection is None:
                return {"status": "error", "message": "Aucune donnée à insérer ou collection non initialisée."}

            self.logger.info(f"[{model_key}][categories] Insertion de {len(datas)} entités dans '{self.collection}'...")
            
            points = []

            for data in datas:
                data["date_ajout"] = datetime.now().isoformat()  # ex: "2025-08-18T14:23:45.123456"
                data["date_maj"] = None     
                
                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=data.get("embedding"),
                        payload={k: v for k, v in data.items() if k != "embedding"}
                    )
                )

            result = self.client.upsert(collection_name=self.collection, points=points)
            self.logger.info(f"[{model_key}] ✓ Insertion terminée avec succès.")

            return {"status": "success", "ids": [p.id for p in points if p.id]}
            
        except Exception as e:
            self.logger.error(f"[{model_key}][categories] Erreur Qdrant lors de l'insertion : {e}", exc_info=True)

    def update_categories(self, categorie: Dict[str, Any]) -> Dict[str, Any]:
        data = categorie
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            self._get_or_create_collection(model_config)

            if not data or self.collection is None:
                return {
                    "status": "error", 
                    "message": "Aucune donnée à mettre à jour ou collection non initialisée."
                }

            if not data.get("id"):
                return {
                    "status": "error", 
                    "message": "ID requis pour la mise à jour."
                }

            self.logger.info(f"[{model_key}][categories] Mise à jour de {len(data)} entités dans '{self.collection}'...")

            data["date_maj"] = datetime.now().isoformat()  # ex: "2025-08-18T14:23:45.123456"
           
            point = PointStruct(
                id=data["id"],
                vector=data["embedding"],
                payload={k: v for k, v in data.items() if k not in ["embedding"]}
            )
            self.client.upsert(collection_name=self.collection, points=[point])
            self.logger.info(f"[{model_key}] ✓ Mise à jour terminée.")

            return {
                "status": "success", 
                "ids": [data["id"]]
            }
        except Exception as e:
            self.logger.error(f"[{model_key}][categories] Erreur Qdrant lors de la mise à jour : {e}", exc_info=True)

    def delete_categories(self, categorie: Dict[str, Any]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id
        id_entity = categorie.get("id")

        try:
            # self._connect_to_milvus()
            self._get_or_create_collection(model_config)

            if not id_entity:
                return {
                    "status": "error", 
                    "message": "ID requis pour suppression."
                }

            self.client.delete(collection_name=self.collection, points_selector=[id_entity])
            self.logger.info(f"[{model_key}] ✓ categorie avec ID {id_entity} supprimé.")

            return {"status": "success", "message": f"categorie {id_entity} supprimé."}
        except Exception as e:
            self.logger.error(f"[{model_key}][categories] Erreur Qdrant lors de la suppression : {e}", exc_info=True)

    def get_categories(self, id_categorie: str) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            # self._connect_to_milvus()
            self._get_or_create_collection(model_config)
            
            if self.collection is None:
                return {"status": "error", "message": "Collection non initialisée.","code":404}

            if not id_categorie:
                return {"status": "error", "message": "ID id_categorie requis.", "code":400}

            filter_query = Filter(
                must=[FieldCondition(key="id_categorie", match=MatchValue(value=id_categorie))]
            )

            scroll_result, _ = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=filter_query,
                limit=1
            )

            return {"status": "success", "data": [p.payload for p in scroll_result] if scroll_result else []}
        except Exception as e:
            self.logger.error(f"[{model_key}][categories] Erreur Qdrant lors de la récupération : {e}", exc_info=True)
