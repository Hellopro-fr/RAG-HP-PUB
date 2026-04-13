import logging
import asyncio
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
    MilvusException,
)

from common_utils.database.milvus_lock import milvus_connection_lock


@dataclass
class ModelConfig:
    model_id: str = settings.MODEL
    collection_name: str = "document"
    dimension: int = 1024


class MilvusDocumentCrud:
    _CONNECTION_ALIAS = "milvus_document"

    # Must match FieldSchema definitions in _get_or_create_collection()
    _VARCHAR_MAX_LENGTHS = {
        "id_demande": 65535,
        "id_fournisseur": 65535,
        "text": 65535,
        "fichier_source": 65535,
        "date_ajout": 65535,
        "date_maj": 65535,
    }

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

    def _validate_varchar_lengths(self, record: dict) -> None:
        for field_name, max_len in self._VARCHAR_MAX_LENGTHS.items():
            value = record.get(field_name)
            if isinstance(value, str):
                byte_len = len(value.encode("utf-8"))
                if byte_len > max_len:
                    raise ValueError(
                        f"Field '{field_name}' exceeds VARCHAR limit: "
                        f"{byte_len} bytes > max {max_len}. "
                        f"Preview: {value[:100]!r}..."
                    )

    def _connect_to_milvus(self):
        # Called with milvus_connection_lock already held
        try:
            connections.disconnect(self._CONNECTION_ALIAS)
        except Exception:
            pass
        self.logger.debug("Connexion sur Zilliz cloud...")
        connections.connect(
            self._CONNECTION_ALIAS,
            host=self.config.ZILLIZ_URI,
            port=self.config.ZILLIZ_PORT,
            user=self.config.ZILLIZ_USER,
            password=self.config.ZILLIZ_PASSWORD,
        )
        self.logger.debug("Connexion sur Zilliz cloud avec succès.")

    def _is_connection_alive(self) -> bool:
        """Verify the gRPC channel is actually usable, not just registered."""
        if not connections.has_connection(self._CONNECTION_ALIAS):
            return False
        try:
            utility.list_collections(using=self._CONNECTION_ALIAS, timeout=5)
            return True
        except Exception:
            return False

    def _ensure_connected(self):
        if self.collection is not None and self._is_connection_alive():
            return
        with milvus_connection_lock:
            if self.collection is not None and self._is_connection_alive():
                return
            self.collection = None  # Reset stale collection reference
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(ModelConfig())

    # TODO : modification pour les autres collections
    def _get_or_create_collection(self, model_config: ModelConfig) -> Collection:
        collection_name = model_config.collection_name
        model_key = model_config.model_id

        if utility.has_collection(collection_name, using=self._CONNECTION_ALIAS) and self.config.RECREATE_COLLECTIONS:
            self.logger.warning(
                f"[{model_key}] Collection déjà existante, suppression en cours : '{collection_name}'"
            )
            utility.drop_collection(collection_name, using=self._CONNECTION_ALIAS)

        if not utility.has_collection(collection_name, using=self._CONNECTION_ALIAS):
            self.logger.debug(f"Collection '{collection_name}' non trouvée. Création...")
            # Définition du schéma détaillé
            fields = [
                FieldSchema(
                    name="id", dtype=DataType.INT64, is_primary=True, auto_id=True
                ),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=model_config.dimension,
                ),
                # FieldSchema(name="page_type", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="id_demande", dtype=DataType.VARCHAR, max_length=65535
                ),
                # FieldSchema(name="categorie", dtype=DataType.VARCHAR, max_length=65535),
                # FieldSchema(name="id_categorie", dtype=DataType.VARCHAR, max_length=65535),
                # FieldSchema(name="produit", dtype=DataType.VARCHAR, max_length=65535),
                # FieldSchema(name="id_produit", dtype=DataType.VARCHAR, max_length=65535),
                # FieldSchema(name="acheteur", dtype=DataType.VARCHAR, max_length=65535),
                # FieldSchema(name="id_acheteur", dtype=DataType.VARCHAR, max_length=65535),
                # FieldSchema(name="fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="id_fournisseur", dtype=DataType.VARCHAR, max_length=65535
                ),
                # FieldSchema(name="etat", dtype=DataType.VARCHAR, max_length=65535),
                # FieldSchema(name="affichage", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                # FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="fichier_source", dtype=DataType.VARCHAR, max_length=65535
                ),
                # FieldSchema(name="chunk_id", dtype=DataType.VARCHAR , max_length=65535),
                # FieldSchema(name="chunk_number", dtype=DataType.INT64),
                # FieldSchema(name="total_chunks", dtype=DataType.INT64),
                FieldSchema(
                    name="date_ajout", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=65535),
            ]
            schema = CollectionSchema(
                fields, description=f"Collection de chunks de document pour {model_key}"
            )

            collection = Collection(collection_name, schema, consistency_level="Bounded", using=self._CONNECTION_ALIAS)

            # # Exemple d'indexation HNSW pour les embeddings
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
            collection.create_index(
                field_name="fichier_source", index_name="idx_fichier_source"
            )
            # collection.create_index(field_name="categorie", index_name="idx_categorie")
            # collection.create_index(field_name="id_categorie", index_name="idx_id_categorie")
            # collection.create_index(field_name="fournisseur", index_name="idx_fournisseur")
            # collection.create_index(field_name="id_fournisseur", index_name="idx_id_fournisseur")
            # collection.create_index(field_name="id_produit", index_name="idx_id_produit")

            self.logger.info(f"[{model_key}] Index créés.")
        else:
            self.logger.debug(
                f"[{model_key}] Connexion à la collection existante : '{collection_name}'"
            )
            collection = Collection(collection_name, using=self._CONNECTION_ALIAS)

        collection.load()
        self.logger.debug(
            f"[{model_key}] Collection '{collection_name}' chargée et prête."
        )
        return collection

    async def insert_document(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:

            await asyncio.to_thread(self._ensure_connected)

            if not datas or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à insérer ou collection non initialisée.",
                }

            self.logger.info(
                f"[{model_key}][document] Insertion de batch de {len(datas)} entités dans '{self.collection.name}'..."
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
                self._validate_varchar_lengths(data)
                sanitized_batch.append(data)

            result = await asyncio.to_thread(self.collection.insert, sanitized_batch)

            self.logger.debug(f"Clé primaire : {result.primary_keys}")

            self.logger.info(f"[{model_key}] Insertion terminée avec succès.")

            return {
                "ids": str(result.primary_keys[0]) if result.primary_keys else "",
                "status": "success",
            }

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][document] Erreur Milvus lors de l'insertion : {e}"
            )
            raise RuntimeError(
                f"[{model_key}][document] Milvus insert failed: {e}"
            ) from e
        except Exception as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][document] insertion de batch : {e}", exc_info=True
            )
            raise

    async def update_document(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:

            await asyncio.to_thread(self._ensure_connected)

            if not datas or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à mettre à jour ou collection non initialisée.",
                }

            sanitized_batch = []
            for data in datas:
                if "date_ajout" not in data.keys():
                    data["date_ajout"] = datetime.now().isoformat()

                data["date_maj"] = datetime.now().isoformat()

                # Sanitize the record to ensure no None values
                # This is important for Milvus compatibility
                data = Utils.sanitize_record(data)
                self._validate_varchar_lengths(data)
                sanitized_batch.append(data)

            result = await asyncio.to_thread(self.collection.upsert, sanitized_batch)
            self.logger.info(f"[{model_key}] Mise à jour terminée avec succès.")
            # self.logger.info(f"Résultat : {result}.")

            return {"status": "success", "data": "updated"}

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][document] Erreur Milvus lors de mise à jour : {e}"
            )
            self.logger.error(f"Data : {datas}")
            raise RuntimeError(
                f"[{model_key}][document] Milvus upsert failed: {e}"
            ) from e
        except Exception as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][document] Mise à jour de batch : {e}", exc_info=True
            )
            self.logger.error(f"Data : {datas}")
            raise

    async def delete_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id
        id_entity_milvus = data.get("id")

        try:
            await asyncio.to_thread(self._ensure_connected)

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not id_entity_milvus:
                self.logger.error(f"[{model_key}][document] Suppression sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la suppression.",
                }

            self.logger.info(
                f"[{model_key}][document] Suppression de l'entité avec ID {id_entity_milvus} dans '{self.collection.name}'..."
            )
            if not isinstance(id_entity_milvus, int):
                try:
                    id_entity_milvus = int(id_entity_milvus)
                except (ValueError, TypeError):
                    return {"status": "error", "message": f"ID invalide (non-entier): {id_entity_milvus}"}
            result = await asyncio.to_thread(
                self.collection.delete, f"id == {id_entity_milvus}"
            )
            self.collection.flush()
            self.logger.info(f"[{model_key}] Suppression terminée avec succès.")

            return {
                "status": "success",
                "message": f"document avec ID {id_entity_milvus} supprimé.",
            }

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][document] Erreur Milvus lors de la suppression : {e}"
            )
            raise RuntimeError(
                f"[{model_key}][document] Milvus delete failed: {e}"
            ) from e
        except Exception as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][document] Suppression : {e}", exc_info=True
            )
            raise

    async def get_document(self, fichier_source: str) -> Dict[str, Any]:
        # Sanitize to prevent expression injection
        sanitized = fichier_source.replace("'", "\\'").replace('"', '\\"')
        list_fichier_source = [sanitized]
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            await asyncio.to_thread(self._ensure_connected)

            if not self.collection:
                return {
                    "status": "error",
                    "message": "Collection non initialisée.",
                    "code": 404,
                }

            if not fichier_source:
                return {
                    "status": "error",
                    "message": "Fichier source requis pour la récupération.",
                    "code": 400,
                }

            result = await asyncio.to_thread(
                self.collection.query,
                expr=f"fichier_source in {list_fichier_source}",
                output_fields=["id", "text", "date_ajout"],
                consistency_level="Bounded",
            )
            # self.collection.flush()
            self.logger.info(f"[{model_key}] Récupèration terminée avec succès.")

            data = None
            # Cas 1 : result est déjà la liste de data
            if isinstance(result, list):
                data = result

            # Cas 2 : le HybridExtraList contient un dict avec une clé "data"
            elif hasattr(result, "data"):
                data = result.data

            # Cas 3 : il contient un dict au premier niveau
            elif isinstance(result, dict) and "data" in result:
                data = result["data"]

            return {"status": "success", "data": data}

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][document] Erreur Milvus lors de la récupération : {e}"
            )
            raise RuntimeError(
                f"[{model_key}][document] Milvus query failed: {e}"
            ) from e
        except Exception as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][document] Erreur de Récupèration de document : {e}",
                exc_info=True,
            )
            raise
