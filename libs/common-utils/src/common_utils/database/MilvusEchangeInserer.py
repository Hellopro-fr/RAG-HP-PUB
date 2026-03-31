import logging
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from common_utils.database.config.settings import Configuration, settings
from common_utils.database.milvus_lock import milvus_connection_lock
from common_utils.database.Utils import Utils

from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
    MilvusException,
)


@dataclass
class ModelConfig:
    collection_name: str = "correspondance_echanges_bo_milvus"


class MilvusEchangeInserer:
    _CONNECTION_ALIAS = "milvus_correspondance_echanges"

    def __init__(self, config: Configuration = settings, **kwargs: Any):
        self.config = config
        self.collection: Optional[Collection] = None
        if (
            not self.config.ZILLIZ_URI
            or not self.config.ZILLIZ_PORT
            or not self.config.ZILLIZ_USER
            or not self.config.ZILLIZ_PASSWORD
        ):
            raise ValueError(
                "Zilliz Cloud URI and Port and User and Password must be set in the environment."
            )
        self.logger = kwargs.get("logger", logging.getLogger(__name__))

    def _connect_to_milvus(self):
        try:
            connections.disconnect(self._CONNECTION_ALIAS)
        except Exception:
            pass
        connections.connect(
            self._CONNECTION_ALIAS,
            host=self.config.ZILLIZ_URI,
            port=self.config.ZILLIZ_PORT,
            user=self.config.ZILLIZ_USER,
            password=self.config.ZILLIZ_PASSWORD,
        )

    def _ensure_connected(self):
        if self.collection is not None and connections.has_connection(self._CONNECTION_ALIAS):
            return
        with milvus_connection_lock:
            if self.collection is not None and connections.has_connection(self._CONNECTION_ALIAS):
                return
            self.collection = None
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(ModelConfig())

    # TODO : modification pour les autres collections
    def _get_or_create_collection(self, model_config: ModelConfig) -> Collection:
        collection_name = model_config.collection_name

        if utility.has_collection(collection_name, using=self._CONNECTION_ALIAS) and self.config.RECREATE_COLLECTIONS:
            utility.drop_collection(collection_name, using=self._CONNECTION_ALIAS)

        if not utility.has_collection(collection_name, using=self._CONNECTION_ALIAS):
            # Définition du schéma détaillé
            fields = [
                # Todo : ce clé doit être unique
                FieldSchema(
                    name="id",
                    dtype=DataType.INT64,
                    is_primary=True,
                    auto_id=True,
                    max_length=64,
                ),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
                FieldSchema(
                    name="id_echange_milvus", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="conversation_id", dtype=DataType.VARCHAR, max_length=64
                ),
                FieldSchema(name="date_ajout", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=64),
            ]
            schema = CollectionSchema(
                fields,
                description=f"Collection de correspondance Milvus - BO Echange MCF/MCA",
            )

            collection = Collection(collection_name, schema, consistency_level="Bounded", using=self._CONNECTION_ALIAS)

            index_params = {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": {
                    "M": settings.M_PARAMS,
                    "efConstruction": settings.EF_PARAMS,
                },
            }
            collection.create_index(field_name="embedding", index_params=index_params)

            # # Optionnel: Créer des index scalaires pour les filtres fréquents
            # collection.create_index(field_name="conversation_id", index_name="idx_conversation_id")
        else:
            collection = Collection(collection_name, using=self._CONNECTION_ALIAS)

        collection.load()
        return collection

    def insert_correspondance_echange(
        self, datas: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        try:

            self._ensure_connected()

            if not datas or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à insérer ou collection non initialisée.",
                }

            sanitized_batch = []
            for data in datas:
                data["date_ajout"] = (
                    datetime.now().isoformat()
                )  # ex: "2025-08-18T14:23:45.123456"
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
            self.logger.error(
                f"[Correspondace Echange BO-Milvus] Erreur Milvus lors de l'insertion : {e}"
            )
            self.logger.error(f"Data : {datas}")
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[Correspondace Echange BO-Milvus] insertion de batch : {e}",
                exc_info=True,
            )
            self.logger.error(f"Data : {datas}")
            raise

    def get_correspondance_by_conversation_id(
        self, conversation_id: str
    ) -> Dict[str, Any]:
        """
        Récupère l'enregistrement de correspondance par conversation_id

        Args:
            conversation_id: L'identifiant de la conversation

        Returns:
            Dict avec status et data ou message d'erreur
        """

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not conversation_id:
                return {
                    "status": "error",
                    "message": "Conversation ID requise pour la récupération.",
                }

            self.logger.info(
                f"[Correspondance Echange BO-Milvus] Récupération pour conversation_id: {conversation_id}"
            )

            result = self.collection.query(
                expr=f'conversation_id == "{conversation_id}"',
                output_fields=[
                    "id",
                    "id_echange_milvus",
                    "conversation_id",
                    "date_ajout",
                    "date_maj",
                ],
                consistency_level="Bounded",
            )

            if not result or len(result) == 0:
                return {
                    "status": "error",
                    "message": f"Aucune correspondance trouvée pour conversation_id: {conversation_id}",
                }

            self.logger.info(
                f"[Correspondance Echange BO-Milvus] Récupération terminée avec succès."
            )

            return {
                "status": "success",
                "data": result[
                    0
                ],  # Retourne le premier (et normalement unique) résultat
            }

        except MilvusException as e:
            self.logger.error(
                f"[Correspondance Echange BO-Milvus] Erreur Milvus lors de la récupération : {e}"
            )
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[Correspondance Echange BO-Milvus] Erreur de récupération : {e}",
                exc_info=True,
            )
            raise

    def delete_correspondance_by_conversation_id(
        self, conversation_id: str
    ) -> Dict[str, Any]:
        """
        Supprime l'enregistrement de correspondance par conversation_id avec retry

        Args:
            conversation_id: L'identifiant de la conversation

        Returns:
            Dict avec status success ou error
        """
        max_retries = 3
        retry_delay = 0.5  # 500ms

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not conversation_id:
                return {
                    "status": "error",
                    "message": "Conversation ID requise pour la suppression.",
                }

            # Retry logic
            for attempt in range(max_retries):
                try:
                    self.logger.info(
                        f"[Correspondance Echange BO-Milvus] Suppression pour conversation_id: {conversation_id} (tentative {attempt + 1}/{max_retries})"
                    )

                    self.collection.delete(f'conversation_id == "{conversation_id}"')
                    self.collection.flush()

                    self.logger.info(
                        f"[Correspondance Echange BO-Milvus] Suppression terminée avec succès."
                    )

                    return {
                        "status": "success",
                        "message": f"Correspondance supprimée pour conversation_id: {conversation_id}",
                    }

                except MilvusException as e:
                    if attempt < max_retries - 1:  # Pas le dernier essai
                        self.logger.warning(
                            f"[Correspondance Echange BO-Milvus] Tentative {attempt + 1} échouée, retry dans {retry_delay}s : {e}"
                        )
                        time.sleep(retry_delay)
                    else:
                        # Dernier essai, on lève l'exception
                        self.logger.error(
                            f"[Correspondance Echange BO-Milvus] Erreur Milvus après {max_retries} tentatives : {e}"
                        )
                        self.collection = None
                        raise

        except Exception as e:
            self.logger.error(
                f"[Correspondance Echange BO-Milvus] Erreur de suppression : {e}",
                exc_info=True,
            )
            self.collection = None
            raise
