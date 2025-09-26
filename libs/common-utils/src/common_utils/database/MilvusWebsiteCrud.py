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
    model_id: str = settings.MODEL
    collection_name: str = "siteweb_2"
    dimension: int = 1024

class MilvusWebsiteCrud:
    def __init__(self, config: Configuration = settings , **kwargs: Any):
        self.config = config
        self.collection: Optional[Collection] = None
        # if not self.config.ZILLIZ_URI or not self.config.ZILLIZ_API_KEY:
        if not self.config.ZILLIZ_URI or not self.config.ZILLIZ_PORT:
            raise ValueError("Zilliz Cloud URI and API Key/Port must be set in the environment.")
        self.logger = kwargs.get('logger', logging)
        
    def _connect_to_milvus(self):
        # Check if a connection with the alias 'default' already exists.
        if not connections.has_connection("default"):
            print("Connexion sur Zilliz cloud...")
            # connections.connect("default", uri=self.config.ZILLIZ_URI, token=self.config.ZILLIZ_API_KEY)
            connections.connect(
                alias="default",
                host=self.config.ZILLIZ_URI, 
                port=self.config.ZILLIZ_PORT,
                timeout=10 # Add a 10-second timeout to prevent indefinite hanging
            )
            print("✓ Connexion sur Zilliz cloud avec succès.")
    
    def _get_or_create_collection(self, model_config: ModelConfig) -> Collection:
        collection_name = model_config.collection_name
        model_key = model_config.model_id

        try:
            print(f"Vérification de l'existence de la collection '{collection_name}'...")
            collection_exists = utility.has_collection(collection_name, using="default", timeout=20)
            print(f" -> La collection '{collection_name}' existe: {collection_exists}")
        except Exception as e:
            print(f"!!! ERREUR LORS DE LA VÉRIFICATION DE LA COLLECTION: {e}")
            raise

        if collection_exists and self.config.RECREATE_COLLECTIONS:
            print(f"[{model_key}] Collection '{collection_name}' existante → suppression en cours...")
            utility.drop_collection(collection_name, using="default", timeout=20)
            collection_exists = False

        if not collection_exists:
            self.logger.info(f"Collection '{collection_name}' non trouvée. Création...")
            # Définition du schéma détaillé
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64 , is_primary = True , auto_id = True),
                FieldSchema(name="url", dtype=DataType.VARCHAR , max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=model_config.dimension),
                FieldSchema(name="page_type", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="etat", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="affichage", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fichier_source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR , max_length=65535),
                FieldSchema(name="chunk_number", dtype=DataType.INT64),
                FieldSchema(name="total_chunks", dtype=DataType.INT64),
                FieldSchema(name="date_ajout",  dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="date_maj",  dtype=DataType.VARCHAR, max_length=65535)
            ]
            schema = CollectionSchema(fields, description=f"Collection de chunks de siteweb pour {model_key}")
            
            collection = Collection(
                name=collection_name, 
                schema=schema,
                using="default",
                consistency_level="Strong"
            )
            
            index_params = {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": settings.M_PARAMS, "efConstruction": settings.EF_PARAMS}}
            collection.create_index(field_name="embedding", index_params=index_params, timeout=60)

            # # Optionnel: Créer des index scalaires pour les filtres fréquents
            collection.create_index(field_name="url", index_name="idx_url", timeout=60)
            # collection.create_index(field_name="categorie", index_name="idx_categorie")
            # collection.create_index(field_name="id_categorie", index_name="idx_id_categorie")
            # collection.create_index(field_name="fournisseur", index_name="idx_fournisseur")
            # collection.create_index(field_name="id_fournisseur", index_name="idx_id_fournisseur")
            # collection.create_index(field_name="affichage", index_name="idx_affichage")
            # collection.create_index(field_name="etat", index_name="idx_etat")
            collection.create_index(field_name="page_type", index_name="idx_page_type", timeout=60)

            self.logger.info(f"[{model_key}] ✓ Index créés.")
        else:
            self.logger.info(f"[{model_key}] Connexion à la collection existante : '{collection_name}'")
            collection = Collection(name=collection_name, using="default")
        
        print(f"Chargement de la collection '{collection_name}' en mémoire...")
        collection.load(timeout=60)
        print(f"[{model_key}] ✓ Collection '{collection_name}' chargée et prête.")
        return collection


    def insert_website(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(model_config)
            
            if not datas or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à insérer ou collection non initialisée."
                }
            
            self.logger.info(f"[{model_key}][siteweb] Insertion de batch de {len(datas)} entités dans '{self.collection.name}'...")
           
            sanitized_batch = []
            for data in datas:
                data["date_ajout"] = datetime.now().isoformat()  # ex: "2025-08-18T14:23:45.123456"
                data["date_maj"] = None  

                # Sanitize the record to ensure no None values
                # This is important for Milvus compatibility
                data = Utils.sanitize_record(data)
                sanitized_batch.append(data)  
            
            result = self.collection.insert(sanitized_batch, timeout=30)

            self.logger.info(f"Résultat insertion : {result}") 
            self.logger.info(f"Clé primaire : {result.primary_keys}") 
            
            self.logger.info(f"[{model_key}] ✓ Insertion terminée avec succès.")
            
            return {
                "ids": str(result.primary_keys[0]) if result.primary_keys else "",
                "status": "success",
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][siteweb] Erreur Milvus lors de l'insertion : {e}")
            self.logger.error(f"Data : {datas}")
        except Exception as e:
            self.logger.error(f"[{model_key}][siteweb] insertion de batch : {e}", exc_info=True)
            self.logger.error(f"Data : {datas}")
    
    def update_website(self, data: Dict[str, Any]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(model_config)
            
            if not data or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à mettre à jour ou collection non initialisée."
                }
            
            if not data.get("id"):
                self.logger.error(f"[{model_key}][siteweb] Mise à jour sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la mise à jour."
                }

            self.logger.info(f"[{model_key}][siteweb] Mise à jour de batch de {len(data)} entités dans '{self.collection.name}'...")
            
            
            data["date_maj"] = datetime.now().isoformat()  # ex: "2025-08-18T14:23:45.123456"

            # Sanitize the record to ensure no None values
            # This is important for Milvus compatibility
            data = Utils.sanitize_record(data)  

            result = self.collection.upsert(data, timeout=30)
            self.collection.flush(timeout=30)
            self.logger.info(f"[{model_key}] ✓ Mise à jour terminée avec succès.")
            
            return {
                "ids": str(result.primary_keys[0]) if result.primary_keys else "",
                "status": "success",
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][siteweb] Erreur Milvus lors de mise à jour : {e}")
            self.logger.error(f"Data : {data}")
        except Exception as e:
            self.logger.error(f"[{model_key}][siteweb] Mise à jour de batch : {e}", exc_info=True)
            self.logger.error(f"Data : {data}")

    def delete_website(self,data: Dict[str, Any]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id
        id_entity_milvus = data.get("id")
        
        try:
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(model_config)

            if not self.collection:
                return {
                    "status": "error",
                    "message": "Collection non initialisée."
                }

            if not id_entity_milvus:
                self.logger.error(f"[{model_key}][siteweb] Suppression sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la suppression."
                }

            self.logger.info(f"[{model_key}][siteweb] Suppression de l'entité avec ID {id_entity_milvus} dans '{self.collection.name}'...")
            result = self.collection.delete(f"id == {id_entity_milvus}", timeout=30)
            self.collection.flush(timeout=30)
            self.logger.info(f"[{model_key}] ✓ Suppression terminée avec succès.")

            return {
                "status": "success",
                "message": f"siteweb avec ID {id_entity_milvus} supprimé."
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][siteweb] Erreur Milvus lors de la suppression : {e}")
        except Exception as e:
            self.logger.error(f"[{model_key}][siteweb] Suppression : {e}", exc_info=True)

    def get_website(self, url: str, page_type: str) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id
        
        try:
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(model_config)

            if not self.collection:
                return {
                    "status": "error",
                    "message": "Collection non initialisée.",
                    "code": 404
                }

            if not url:
                return {
                    "status": "error",
                    "message": "Url requise pour la récupération.",
                    "code" : 400
                }
                
            if not page_type:
                return {
                    "status": "error",
                    "message": "Page type requise pour la récupération.",
                    "code" : 400
                }

            result = self.collection.query(
                expr=f'url == "{url}" && page_type == "{page_type}"',
                output_fields=["id"],
                timeout=20
            )

            self.logger.info(f"[{model_key}] ✓ Récupèration terminée avec succès.")

            return {
                "status": "success",
                "data": result
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Website] Erreur Milvus lors de la récupération : {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            self.logger.error(f"[{model_key}][Website] Erreur de Récupèration de siteweb : {e}", exc_info=True)
            return {"status": "error", "message": str(e)}