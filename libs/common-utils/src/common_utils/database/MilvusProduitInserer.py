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
    model_id: str = settings.MODEL
    collection_name: str = "correspondance_produits_bo_milvus_3"
    dimension: int = 1024


class MilvusProduitInserer:
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
        self.logger = kwargs.get("logger", logging)

    def _connect_to_milvus(self):
        self.logger.info("Connexion sur Zilliz cloud...")
        try:
            connections.disconnect("default")
        except Exception:
            pass
        connections.connect(
            "default",
            host=self.config.ZILLIZ_URI,
            port=self.config.ZILLIZ_PORT,
            user=self.config.ZILLIZ_USER,
            password=self.config.ZILLIZ_PASSWORD,
        )
        self.logger.info("✓ Connexion sur Zilliz cloud avec succès.")

    def _ensure_connected(self):
        if self.collection is not None:
            return
        with milvus_connection_lock:
            if self.collection is not None:
                return
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(ModelConfig())

    # TODO : modification pour les autres collections
    def _get_or_create_collection(self, model_config: ModelConfig) -> Collection:
        collection_name = model_config.collection_name
        model_key = model_config.model_id

        if utility.has_collection(collection_name) and self.config.RECREATE_COLLECTIONS:
            logging.warning(
                f"[{model_key}] Collection déjà existante → suppréssion en cours : '{collection_name}'"
            )
            utility.drop_collection(collection_name)

        if not utility.has_collection(collection_name):
            self.logger.info(f"Collection '{collection_name}' non trouvée. Création...")
            # Définition du schéma détaillé
            fields = [
                # TODO a completer / verifier
                FieldSchema(
                    name="id",
                    dtype=DataType.INT64,
                    is_primary=True,
                    auto_id=True,
                    max_length=64,
                ),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=model_config.dimension,
                ),
                FieldSchema(name="id_produit", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(
                    name="id_produit_milvus", dtype=DataType.VARCHAR, max_length=512
                ),
                FieldSchema(name="origin", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="date_ajout", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=64),
            ]
            schema = CollectionSchema(
                fields, description=f"Collection de chunks de Produit pour {model_key}"
            )

            collection = Collection(collection_name, schema, consistency_level="Bounded")

            index_params = {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": {
                    "M": settings.M_PARAMS,
                    "efConstruction": settings.EF_PARAMS,
                },
            }
            collection.create_index(field_name="embedding", index_params=index_params)

        else:
            self.logger.info(
                f"[{model_key}] Connexion à la collection existante : '{collection_name}'"
            )
            collection = Collection(collection_name)

        collection.load()
        return collection

    def insert_correpondance_produit(
        self, datas: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        model_key = ModelConfig().model_id

        try:

            self._ensure_connected()

            if not datas or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à insérer ou collection non initialisée.",
                }

            self.logger.info(
                f"[{model_key}][Produits] Insertion de batch de {len(datas)} entités dans '{self.collection.name}'..."
            )

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

            result = self.collection.insert(sanitized_batch)
            # self.collection.flush()

            self.logger.info(f"Résultat insertion : {result}")
            self.logger.info(f"Clé primaire : {result.primary_keys}")

            self.logger.info(f"[{model_key}] ✓ Insertion terminée avec succès.")

            return {
                "ids": str(result.primary_keys[0]) if result.primary_keys else "",
                "status": "success",
            }

        except MilvusException as e:
            self.logger.error(
                f"[{model_key}][Correspondance produits BO-Milvus] Erreur Milvus lors de l'insertion : {e}"
            )
            self.logger.error(f"Data : {datas}")
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Correspondance produits BO-Milvus] insertion de batch : {e}",
                exc_info=True,
            )
            self.logger.error(f"Data : {datas}")
            raise

    def get_correspondance_by_id_produit(self, id_produit: str) -> Dict[str, Any]:
        """
        Récupère l'enregistrement de correspondance par id_produit

        Args:
            id_produit: L'identifiant du produit

        Returns:
            Dict avec status et data ou message d'erreur
        """

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not id_produit:
                return {
                    "status": "error",
                    "message": "id_produit requise pour la récupération.",
                }

            self.logger.info(
                f"[Correspondance Produit BO-Milvus] Récupération pour id_produit: {id_produit}"
            )

            result = self.collection.query(
                expr=f'id_produit == "{id_produit}"',
                output_fields=[
                    "id",
                    "id_produit_milvus",
                    "id_produit",
                    "origin",
                    "date_ajout",
                    "date_maj",
                ],
                consistency_level="Bounded",
            )

            if not result or len(result) == 0:
                return {
                    "status": "error",
                    "message": f"Aucune correspondance trouvée pour id_produit: {id_produit}",
                }

            self.logger.info(
                f"[Correspondance Produit BO-Milvus] ✓ Récupération terminée avec succès."
            )

            return {
                "status": "success",
                "data": result[
                    0
                ],  # Retourne le premier (et normalement unique) résultat
            }

        except MilvusException as e:
            self.logger.error(
                f"[Correspondance Produit BO-Milvus] Erreur Milvus lors de la récupération : {e}"
            )
            self.collection = None
            return {"status": "error", "message": f"Erreur Milvus: {str(e)}"}
        except Exception as e:
            self.logger.error(
                f"[Correspondance Produit BO-Milvus] Erreur de récupération : {e}",
                exc_info=True,
            )
            return {"status": "error", "message": f"Erreur: {str(e)}"}

    def delete_correspondance_by_id_produit_and_origin(
        self, id_produit: str, origin: str
    ) -> Dict[str, Any]:
        """
        Supprime l'enregistrement de correspondance par id_produit ET origin avec retry
        Méthode plus précise que delete_correspondance_by_id_produit

        Args:
            id_produit: L'identifiant du produit
            origin: La source du produit (bo, siteweb, api, etc.)

        Returns:
            Dict avec status success ou error
        """
        max_retries = 3
        retry_delay = 0.5  # 500ms

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not id_produit or not origin:
                return {
                    "status": "error",
                    "message": "id_produit et origin requis pour la suppression.",
                }

            self.logger.info(
                f"[Correspondance Produit BO-Milvus] Suppression pour id_produit: {id_produit}, origin: {origin}"
            )

            for attempt in range(max_retries):
                try:
                    expr = f'id_produit == "{id_produit}" && origin == "{origin}"'
                    self.collection.delete(expr)
                    self.collection.flush()

                    self.logger.info(
                        f"[Correspondance Produit BO-Milvus] ✓ Suppression terminée avec succès."
                    )

                    return {
                        "status": "success",
                        "message": f"Correspondance pour id_produit={id_produit} et origin={origin} supprimée.",
                    }
                except Exception as retry_error:
                    if attempt < max_retries - 1:
                        self.logger.warning(
                            f"[Correspondance Produit BO-Milvus] Tentative {attempt + 1}/{max_retries} échouée: {retry_error}. Retry dans {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                    else:
                        raise

        except MilvusException as e:
            self.logger.error(
                f"[Correspondance Produit BO-Milvus] Erreur Milvus lors de la suppression : {e}"
            )
            self.collection = None
            return {"status": "error", "message": f"Erreur Milvus: {str(e)}"}
        except Exception as e:
            self.logger.error(
                f"[Correspondance Produit BO-Milvus] Erreur de suppression : {e}",
                exc_info=True,
            )
            self.collection = None
            return {"status": "error", "message": f"Erreur: {str(e)}"}

    def delete_correspondance_by_id_produit(self, id_produit: str) -> Dict[str, Any]:
        """
        Supprime l'enregistrement de correspondance par id_produit avec retry

        Args:
            id_produit: L'identifiant du produit

        Returns:
            Dict avec status success ou error
        """
        max_retries = 3
        retry_delay = 0.5  # 500ms

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not id_produit:
                return {
                    "status": "error",
                    "message": "id_produit requise pour la suppression.",
                }

            self.logger.info(
                f"[Correspondance Produit BO-Milvus] Suppression pour id_produit: {id_produit}"
            )

            for attempt in range(max_retries):
                try:
                    expr = f'id_produit == "{id_produit}"'
                    self.collection.delete(expr)
                    self.collection.flush()

                    self.logger.info(
                        f"[Correspondance Produit BO-Milvus] ✓ Suppression terminée avec succès."
                    )

                    return {
                        "status": "success",
                        "message": f"Correspondance pour id_produit {id_produit} supprimée.",
                    }
                except Exception as retry_error:
                    if attempt < max_retries - 1:
                        self.logger.warning(
                            f"[Correspondance Produit BO-Milvus] Tentative {attempt + 1}/{max_retries} échouée: {retry_error}. Retry dans {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                    else:
                        raise

        except MilvusException as e:
            self.logger.error(
                f"[Correspondance Produit BO-Milvus] Erreur Milvus lors de la suppression : {e}"
            )
            self.collection = None
            return {"status": "error", "message": f"Erreur Milvus: {str(e)}"}
        except Exception as e:
            self.logger.error(
                f"[Correspondance Produit BO-Milvus] Erreur de suppression : {e}",
                exc_info=True,
            )
            self.collection = None
            return {"status": "error", "message": f"Erreur: {str(e)}"}
