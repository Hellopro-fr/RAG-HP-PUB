import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from common_utils.database.config.settings import Configuration, settings
from common_utils.database.Utils import Utils

from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
    MilvusException
)


@dataclass
class ModelConfig:
    collection_name: str = "correspondance_fournisseurs_bo_milvus"

class MilvusFournisseursInserer:
    def __init__(self, config: Configuration = settings , **kwargs: Any):
        self.config = config
        self.collection: Optional[Collection] = None
        if not self.config.ZILLIZ_URI or not self.config.ZILLIZ_PORT or not self.config.ZILLIZ_USER or not self.config.ZILLIZ_PASSWORD:
            raise ValueError("Zilliz Cloud URI and Port and User and Password must be set in the environment.")
        self.logger = kwargs.get('logger', logging)
        
    def _connect_to_milvus(self):
        connections.connect(
            "default",
            host=self.config.ZILLIZ_URI,
            port=self.config.ZILLIZ_PORT,
            user=self.config.ZILLIZ_USER,
            password=self.config.ZILLIZ_PASSWORD
        )
    
    # TODO : modification pour les autres collections
    def _get_or_create_collection(self, model_config: ModelConfig) -> Collection:
        collection_name = model_config.collection_name

        if utility.has_collection(collection_name) and self.config.RECREATE_COLLECTIONS:
            utility.drop_collection(collection_name)

        if not utility.has_collection(collection_name):
            # Définition du schéma détaillé
            fields = [
                # Todo : ce clé doit être unique
                FieldSchema(name="id", dtype=DataType.INT64 , is_primary = True , auto_id = True ,max_length=64),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
                FieldSchema(name="id_fournisseur_milvus", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_fournisseur", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="date_ajout", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=64)
            ]
            schema = CollectionSchema(fields, description=f"Collection de correspondance Milvus - BO Fournisseurs")
            
            collection = Collection(
                collection_name, 
                schema,
                consistency_level="Strong"
            )

            index_params = {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": settings.M_PARAMS, "efConstruction": settings.EF_PARAMS}}
            collection.create_index(field_name="embedding", index_params=index_params)

            # # Optionnel: Créer des index scalaires pour les filtres fréquents
            # collection.create_index(field_name="conversation_id", index_name="idx_conversation_id")
        else:
            collection = Collection(collection_name)
        
        collection.load()
        return collection


    def insert_correspondance_fournisseurs(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:
        model_config = ModelConfig()

        try:
            
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(model_config)
            
            if not datas or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à insérer ou collection non initialisée."
                }
            
            sanitized_batch = []
            for data in datas:
                data["date_ajout"] = datetime.now().isoformat()  # ex: "2025-08-18T14:23:45.123456"
                data["date_maj"] = None

                # Sanitize the record to ensure no None values
                # This is important for Milvus compatibility
                data = Utils.sanitize_record(data)  
                sanitized_batch.append(data)

            self.collection.insert(sanitized_batch)

            return {
                "status": "success",
            }

        except MilvusException as e:
            self.logger.error(f"[Correspondace Fournisseurs BO-Milvus] Erreur Milvus lors de l'insertion : {e}")
            self.logger.error(f"Data : {datas}")
        except Exception as e:
            self.logger.error(f"[Correspondace Fournisseurs BO-Milvus] insertion de batch : {e}", exc_info=True)
            self.logger.error(f"Data : {datas}")