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
    collection_name: str = "echanges"
    dimension: int = 1024

class MilvusEchangeCrud:
    def __init__(self, config: Configuration = settings , **kwargs: Any):
        self.config = config
        self.collection: Optional[Collection] = None
        # if not self.config.ZILLIZ_URI or not self.config.ZILLIZ_API_KEY:
        if not self.config.ZILLIZ_URI or not self.config.ZILLIZ_PORT:
            raise ValueError("Zilliz Cloud URI and API Key/Port must be set in the environment.")
        self.logger = kwargs.get('logger', logging)
        
    def _connect_to_milvus(self):
        self.logger.info("Connexion sur Zilliz cloud...")
        # connections.connect("default", uri=self.config.ZILLIZ_URI, token=self.config.ZILLIZ_API_KEY)
        connections.connect("default", host=self.config.ZILLIZ_URI, port=self.config.ZILLIZ_PORT)
        self.logger.info("✓ Connexion sur Zilliz cloud avec succès.")
    
    # TODO : modification pour les autres collections
    def _get_or_create_collection(self, model_config: ModelConfig) -> Collection:
        collection_name = model_config.collection_name
        model_key = model_config.model_id

        if utility.has_collection(collection_name) and self.config.RECREATE_COLLECTIONS:
            logging.warning(f"[{model_key}] Collection déjà existante → suppréssion en cours : '{collection_name}'")
            utility.drop_collection(collection_name)

        if not utility.has_collection(collection_name):
            self.logger.info(f"Collection '{collection_name}' non trouvée. Création...")
            # Définition du schéma détaillé
            fields = [
                # Todo : ce clé doit être unique
                FieldSchema(name="id", dtype=DataType.INT64 , is_primary = True , auto_id = True),
                FieldSchema(name="id_demande", dtype=DataType.VARCHAR , max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=model_config.dimension),
                FieldSchema(name="produit", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_produit", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="etat", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="affichage", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="acheteur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_acheteur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="conversation_id", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR , max_length=65535),
                FieldSchema(name="chunk_number", dtype=DataType.INT64),
                FieldSchema(name="total_chunks", dtype=DataType.INT64),
                FieldSchema(name="date_ajout",  dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="date_maj",  dtype=DataType.VARCHAR, max_length=65535)
            ]
            schema = CollectionSchema(fields, description=f"Collection de chunks de Echange pour {model_key}")
            
            collection = Collection(
                collection_name, 
                schema,
                consistency_level="Strong"
            )
            
            # self.logger.info(f"[{model_key}] Création HNSW index pour l'embedding")

            # TODO : Vérifier les paramètres d'indexation
            # Exemple d'indexation HNSW pour les embeddings
            index_params = {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": settings.M_PARAMS, "efConstruction": settings.EF_PARAMS}}
            collection.create_index(field_name="embedding", index_params=index_params)

            # # Optionnel: Créer des index scalaires pour les filtres fréquents
            collection.create_index(field_name="conversation_id", index_name="idx_conversation_id")
            # collection.create_index(field_name="categorie", index_name="idx_categorie")
            # collection.create_index(field_name="id_categorie", index_name="idx_id_categorie")
            # collection.create_index(field_name="fournisseur", index_name="idx_fournisseur")
            # collection.create_index(field_name="id_fournisseur", index_name="idx_id_fournisseur")
            # collection.create_index(field_name="affichage", index_name="idx_affichage")
            # collection.create_index(field_name="etat", index_name="idx_etat")

            self.logger.info(f"[{model_key}] ✓ Index créés.")
        else:
            self.logger.info(f"[{model_key}] Connexion à la collection existante : '{collection_name}'")
            collection = Collection(collection_name)
        
        collection.load()
        self.logger.info(f"[{model_key}] ✓ Collection '{collection_name}' chargée et prête.")
        return collection


    def insert_echange(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            
            self.logger.info(f"[{model_key}][Echange] Insertion de batch de {len(datas)} entités dans '{self.collection.name}'...")
           
            sanitized_batch = []
            for data in datas:
                data["date_ajout"] = datetime.now().isoformat()  # ex: "2025-08-18T14:23:45.123456"
                data["date_maj"] = None

                # Sanitize the record to ensure no None values
                # This is important for Milvus compatibility
                data = Utils.sanitize_record(data)  
                sanitized_batch.append(data)

            result = self.collection.insert(sanitized_batch)
            # self.collection.flush()

            self.logger.info(f"Résultat insertion : {result}") 
            self.logger.info(f"Clé primaire : {result.primary_keys}") 
            
            self.logger.info(f"[{model_key}] ✓ Insertion terminée avec succès.")
            
            return {
                "ids": ",".join(map(str,result.primary_keys)) if result.primary_keys else "",
                "status": "success",
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Echange] Erreur Milvus lors de l'insertion : {e}")
            self.logger.error(f"Data : {data}")
        except Exception as e:
            self.logger.error(f"[{model_key}][Echange] insertion de batch : {e}", exc_info=True)
            self.logger.error(f"Data : {data}")
    
    def update_echange(self, echanges: List[Dict[str, Any]], conversation_id: str, correspondance_echange=None) -> Dict[str, Any]:
        """
        Met à jour les échanges pour une conversation_id donnée.
        Supprime les anciennes données et réinsère les nouvelles.

        Args:
            echanges: Liste des nouveaux échanges à insérer
            conversation_id: L'identifiant de la conversation
            correspondance_echange: Instance de MilvusEchangeInserer pour gérer la table de correspondance

        Returns:
            Dict avec status, data et flags (already_in_bdd, updated)
        """
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(model_config)

            if not echanges or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à mettre à jour ou collection non initialisée."
                }

            if not conversation_id:
                return {
                    "status": "error",
                    "message": "Conversation ID requise pour la mise à jour."
                }

            self.logger.info(f"[{model_key}][Echange] Mise à jour pour conversation_id: {conversation_id}")

            # 1. Récupérer la correspondance
            if correspondance_echange is None:
                from common_utils.database.MilvusEchangeInserer import MilvusEchangeInserer
                correspondance_echange = MilvusEchangeInserer()

            correspondance_result = correspondance_echange.get_correspondance_by_conversation_id(conversation_id)
            if correspondance_result["status"] == "error":
                self.logger.error(f"[{model_key}][Echange] Erreur récupération correspondance: {correspondance_result['message']}")
                return {
                    "status": "error",
                    "message": f"Échec récupération correspondance: {correspondance_result['message']}"
                }

            # 2. Parser les IDs
            ids_str = correspondance_result["data"].get("id_echange_milvus", "")
            if not ids_str:
                self.logger.error(f"[{model_key}][Echange] Aucun ID trouvé dans la correspondance")
                return {
                    "status": "error",
                    "message": "Aucun ID trouvé dans la correspondance"
                }

            ids = [int(x.strip()) for x in ids_str.split(",") if x.strip()]
            self.logger.info(f"[{model_key}][Echange] IDs à supprimer: {ids}")

            # 3. Supprimer les anciennes données dans 'echanges'
            delete_result = self.delete_echanges_by_ids(ids)
            if delete_result["status"] == "error":
                self.logger.error(f"[{model_key}][Echange] Erreur suppression: {delete_result['message']}")
                return {
                    "status": "error",
                    "message": f"Échec suppression echanges: {delete_result['message']}"
                }

            # 4. Supprimer dans la table de correspondance (avec retry)
            delete_corr_result = correspondance_echange.delete_correspondance_by_conversation_id(conversation_id)
            if delete_corr_result["status"] == "error":
                self.logger.error(f"[{model_key}][Echange] Erreur suppression correspondance: {delete_corr_result['message']}")
                return {
                    "status": "error",
                    "message": f"Échec suppression correspondance: {delete_corr_result['message']}"
                }

            self.logger.info(f"[{model_key}][Echange] Suppression réussie. Réinsertion en cours...")

            # 5. Réinsérer les nouvelles données
            insert_result = self.insert_echange(echanges)

            if insert_result and insert_result.get("status") == "success":
                # 6. Réinsérer dans la table de correspondance
                data_bo_milvus = [{
                    "embedding": [0.0]*1024,
                    "id_echange_milvus": insert_result.get("ids", ""),
                    "conversation_id": conversation_id,
                    "date_ajout": datetime.now().isoformat(),
                    "date_maj": ""
                }]
                correspondance_echange.insert_correspondance_echange(data_bo_milvus)

                self.logger.info(f"[{model_key}][Echange] ✓ Mise à jour terminée avec succès.")

                return {
                    "status": "success",
                    "data": insert_result,
                    "already_in_bdd": True,
                    "updated": True
                }
            else:
                return {
                    "status": "error",
                    "message": "Échec de la réinsertion après suppression"
                }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Echange] Erreur Milvus lors de mise à jour : {e}")
            return {
                "status": "error",
                "message": f"Erreur Milvus: {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"[{model_key}][Echange] Mise à jour : {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Erreur: {str(e)}"
            }

    def delete_echange(self,data: Dict[str, Any]) -> Dict[str, Any]:
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
                self.logger.error(f"[{model_key}][Echange] Suppression sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la suppression."
                }

            self.logger.info(f"[{model_key}][Echange] Suppression de l'entité avec ID {id_entity_milvus} dans '{self.collection.name}'...")
            result = self.collection.delete(f"id == {id_entity_milvus}")
            self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Suppression terminée avec succès.")

            return {
                "status": "success",
                "message": f"Echange avec ID {id_entity_milvus} supprimé."
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Echange] Erreur Milvus lors de la suppression : {e}")
        except Exception as e:
            self.logger.error(f"[{model_key}][Echange] Suppression : {e}", exc_info=True)

    def get_echange(self,conversation_id: str) -> Dict[str, Any]:
        list_conversation_id = [conversation_id]
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

            if not conversation_id:
                return {
                    "status": "error",
                    "message": "Conversation ID requise pour la récupération.",
                    "code" : 400
                }

            result = self.collection.query(
                expr=f"conversation_id in {list_conversation_id}",
                output_fields=["id"]
            )
            # self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Récupèration terminée avec succès.")

            return {
                "status": "success",
                "data": result
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Echange] Erreur Milvus lors de la récupération : {e}")
        except Exception as e:
            self.logger.error(f"[{model_key}][Echange] Erreur de Récupèration de siteweb : {e}", exc_info=True)

    def delete_echanges_by_ids(self, ids: List[int]) -> Dict[str, Any]:
        """
        Supprime plusieurs entités par leurs IDs

        Args:
            ids: Liste des IDs à supprimer

        Returns:
            Dict avec status success ou error
        """
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(model_config)

            if not self.collection:
                return {
                    "status": "error",
                    "message": "Collection non initialisée."
                }

            if not ids or len(ids) == 0:
                self.logger.error(f"[{model_key}][Echange] Suppression sans IDs.")
                return {
                    "status": "error",
                    "message": "Liste d'IDs requise pour la suppression."
                }

            self.logger.info(f"[{model_key}][Echange] Suppression de {len(ids)} entités avec IDs {ids} dans '{self.collection.name}'...")

            # Construire l'expression pour Milvus
            ids_str = ", ".join(map(str, ids))
            expr = f"id in [{ids_str}]"

            self.collection.delete(expr)
            self.collection.flush()

            self.logger.info(f"[{model_key}] ✓ Suppression terminée avec succès.")

            return {
                "status": "success",
                "message": f"{len(ids)} échanges supprimés."
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Echange] Erreur Milvus lors de la suppression : {e}")
            return {
                "status": "error",
                "message": f"Erreur Milvus: {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"[{model_key}][Echange] Suppression : {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Erreur: {str(e)}"
            }
