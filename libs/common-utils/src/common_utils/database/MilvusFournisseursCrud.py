import logging
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
    collection_name: str = "fournisseurs"
    dimension: int = 1024


class MilvusFournisseursCrud:
    _CONNECTION_ALIAS = "milvus_fournisseurs"

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
        try:
            connections.disconnect(self._CONNECTION_ALIAS)
        except Exception:
            pass
        self.logger.info("Connexion sur Zilliz cloud...")
        connections.connect(
            self._CONNECTION_ALIAS,
            host=self.config.ZILLIZ_URI,
            port=self.config.ZILLIZ_PORT,
            user=self.config.ZILLIZ_USER,
            password=self.config.ZILLIZ_PASSWORD,
        )
        self.logger.info("Connexion sur Zilliz cloud avec succès.")

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
        model_key = model_config.model_id

        if utility.has_collection(collection_name, using=self._CONNECTION_ALIAS) and self.config.RECREATE_COLLECTIONS:
            logging.warning(
                f"[{model_key}] Collection déjà existante → suppréssion en cours : '{collection_name}'"
            )
            utility.drop_collection(collection_name, using=self._CONNECTION_ALIAS)

        if not utility.has_collection(collection_name, using=self._CONNECTION_ALIAS):
            self.logger.info(f"Collection '{collection_name}' non trouvée. Création...")
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
                FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=model_config.dimension,
                ),
                FieldSchema(name="page_type", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine2", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine3", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine4", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine5", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine6", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="fournisseur", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="id_fournisseur", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="fichier_source", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="etat", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="affichage", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="nom_categorie_phare_1",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(
                    name="id_categorie_phare_1",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(
                    name="nom_categorie_phare_2",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(
                    name="id_categorie_phare_2",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(
                    name="nom_categorie_phare_3",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(
                    name="id_categorie_phare_3",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="chunk_number", dtype=DataType.INT64),
                FieldSchema(name="total_chunks", dtype=DataType.INT64),
                FieldSchema(name="date_ajout", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=64),
            ]
            schema = CollectionSchema(
                fields,
                description=f"Collection de chunks de categories pour {model_key}",
            )
            collection = Collection(collection_name, schema, consistency_level="Bounded", using=self._CONNECTION_ALIAS)

            self.logger.info(f"[{model_key}] Création HNSW index pour l'embedding")

            # TODO : Vérifier les paramètres d'indexation
            # Exemple d'indexation HNSW pour les embeddings
            index_params = {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": {
                    "M": settings.M_PARAMS,
                    "efConstruction": settings.EF_PARAMS,
                },
            }
            collection.create_index(field_name="embedding", index_params=index_params)

            # Optionnel: Créer des index scalaires pour les filtres fréquents
            # collection.create_index(field_name="fournisseur", index_name="idx_fournisseur")
            collection.create_index(
                field_name="id_fournisseur", index_name="idx_id_fournisseur"
            )
            # collection.create_index(field_name="affichage", index_name="idx_affichage")
            # collection.create_index(field_name="etat", index_name="idx_etat")
            # collection.create_index(field_name="page_type", index_name="idx_page_type")
            # collection.create_index(field_name="domaine", index_name="idx_domaine")
            # collection.create_index(field_name="domaine2", index_name="idx_domaine2")
            # collection.create_index(field_name="domaine3", index_name="idx_domaine3")
            # collection.create_index(field_name="domaine4", index_name="idx_domaine4")
            # collection.create_index(field_name="domaine5", index_name="idx_domaine5")
            # collection.create_index(field_name="domaine6", index_name="idx_domaine6")

            self.logger.info(f"[{model_key}] ✓ Index créés.")
        else:
            self.logger.info(
                f"[{model_key}] Connexion à la collection existante : '{collection_name}'"
            )
            collection = Collection(collection_name, using=self._CONNECTION_ALIAS)

        collection.load()
        self.logger.info(
            f"[{model_key}] ✓ Collection '{collection_name}' chargée et prête."
        )
        return collection

    def insert_fournisseurs(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:

        model_config = ModelConfig()
        model_key = model_config.model_id

        try:

            self._ensure_connected()

            if not datas or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à insérer ou collection non initialisée.",
                }

            self.logger.info(
                f"[{model_key}][fournisseurs] Insertion de batch de {len(datas)} entités dans '{self.collection.name}'..."
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
                "ids": (
                    ",".join(map(str, result.primary_keys))
                    if result.primary_keys
                    else ""
                ),
                "status": "success",
            }

        except MilvusException as e:
            self.logger.error(
                f"[{model_key}][fournisseurs] Erreur Milvus lors de l'insertion : {e}"
            )
            self.logger.error(f"Data : {data}")
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][fournisseurs] insertion de batch : {e}", exc_info=True
            )
            self.logger.error(f"Data : {data}")
            self.collection = None
            raise

    def update_fournisseurs(self, data: Dict[str, Any]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:

            self._ensure_connected()

            if not data or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à mettre à jour ou collection non initialisée.",
                }

            if not data.get("id"):
                self.logger.error(f"[{model_key}][fournisseurs] Mise à jour sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la mise à jour.",
                }

            self.logger.info(
                f"[{model_key}][fournisseurs] Mise à jour de batch de {len(data)} entités dans '{self.collection.name}'..."
            )

            data["date_maj"] = (
                datetime.now().isoformat()
            )  # ex: "2025-08-18T14:23:45.123456"

            # Sanitize the record to ensure no None values
            # This is important for Milvus compatibility
            data = Utils.sanitize_record(data)

            result = self.collection.upsert(data)
            self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Mise à jour terminée avec succès.")

            return {
                "ids": str(result.primary_keys[0]) if result.primary_keys else "",
                "status": "success",
            }

        except MilvusException as e:
            self.logger.error(
                f"[{model_key}][fournisseurs] Erreur Milvus lors de mise à jour : {e}"
            )
            self.logger.error(f"Data : {data}")
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][fournisseurs] Mise à jour de batch : {e}", exc_info=True
            )
            self.logger.error(f"Data : {data}")
            self.collection = None
            raise

    def delete_fournisseurs(self, data: Dict[str, Any]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id
        id_entity_milvus = data.get("id")

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not id_entity_milvus:
                self.logger.error(f"[{model_key}][fournisseurs] Suppression sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la suppression.",
                }

            self.logger.info(
                f"[{model_key}][fournisseurs] Suppression de l'entité avec ID {id_entity_milvus} dans '{self.collection.name}'..."
            )
            result = self.collection.delete(f"id == {id_entity_milvus}")
            self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Suppression terminée avec succès.")

            return {
                "status": "success",
                "message": f"fournisseur avec ID {id_entity_milvus} supprimé.",
            }

        except MilvusException as e:
            self.logger.error(
                f"[{model_key}][fournisseurs] Erreur Milvus lors de la suppression : {e}"
            )
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][fournisseurs] Suppression : {e}", exc_info=True
            )
            self.collection = None
            raise

    def get_fournisseurs(self, id_fournisseur: str) -> Dict[str, Any]:
        list_id_fournisseur = [id_fournisseur]
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            self._ensure_connected()

            if not self.collection:
                return {
                    "status": "error",
                    "message": "Collection non initialisée.",
                    "code": 404,
                }

            if not id_fournisseur:
                return {
                    "status": "error",
                    "message": "id_fournisseur requise pour la récupération.",
                    "code": 400,
                }

            result = self.collection.query(
                expr=f"id_fournisseur in {list_id_fournisseur}",
                output_fields=["id"],
                consistency_level="Bounded",
            )
            # self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Récupèration terminée avec succès.")

            return {"status": "success", "data": result}

        except MilvusException as e:
            self.logger.error(
                f"[{model_key}][Fournisseur] Erreur Milvus lors de la récupération : {e}"
            )
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Fournisseur] Erreur de Récupèration de Fournisseur : {e}",
                exc_info=True,
            )
            self.collection = None
            raise

    ALLOWED_FIELDS = {
        "url", "page_type", "domaine", "domaine2", "domaine3",
        "domaine4", "domaine5", "domaine6", "fournisseur",
        "id_fournisseur", "source", "fichier_source", "etat",
        "affichage", "nom_categorie_phare_1", "id_categorie_phare_1",
        "nom_categorie_phare_2", "id_categorie_phare_2",
        "nom_categorie_phare_3", "id_categorie_phare_3",
        "text", "chunk_id", "date_ajout", "date_maj",
    }

    def get_fournisseur_by_field(
        self, field_name: str, search_value: str
    ) -> Dict[str, Any]:
        list_search_value = [search_value]
        model_config = ModelConfig()
        model_key = model_config.model_id

        if not field_name:
            field_name = "fournisseur"

        if field_name not in self.ALLOWED_FIELDS:
            raise ValueError(f"Invalid field name: {field_name}. Allowed: {self.ALLOWED_FIELDS}")

        try:
            self._ensure_connected()

            if not self.collection:
                return {
                    "status": "error",
                    "message": "Collection non initialisée.",
                    "code": 404,
                }

            if not search_value:
                return {
                    "status": "error",
                    "message": "search_value requise pour la récupération.",
                    "code": 400,
                }

            result = self.collection.query(
                expr=f"{field_name} in {list_search_value}",
                output_fields=["id"],
                consistency_level="Bounded",
            )
            # self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Récupèration terminée avec succès.")

            return {"status": "success", "data": result}

        except MilvusException as e:
            self.logger.error(
                f"[{model_key}][Fournisseur] Erreur Milvus lors de la récupération : {e}"
            )
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Fournisseur] Erreur de Récupèration Fournisseur : {e}",
                exc_info=True,
            )
            self.collection = None
            raise
