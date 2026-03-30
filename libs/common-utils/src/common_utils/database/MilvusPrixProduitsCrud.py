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
    Function,
    FunctionType,
    MilvusException,
)


@dataclass
class PrixModelConfig:
    model_id: str = settings.MODEL
    collection_name: str = "prix"
    dimension: int = 1024


class MilvusPrixProduitsCrud:
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
            connections.disconnect("default")
        except Exception:
            pass
        self.logger.info("Connexion sur Zilliz cloud...")
        connections.connect(
            "default",
            host=self.config.ZILLIZ_URI,
            port=self.config.ZILLIZ_PORT,
            user=self.config.ZILLIZ_USER,
            password=self.config.ZILLIZ_PASSWORD,
        )
        self.logger.info("Connexion sur Zilliz cloud avec succès.")

    def _ensure_connected(self):
        if self.collection is not None:
            return
        with milvus_connection_lock:
            if self.collection is not None:
                return
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(PrixModelConfig())

    def _get_or_create_collection(self, model_config: PrixModelConfig) -> Collection:
        collection_name = model_config.collection_name
        model_key = model_config.model_id

        if utility.has_collection(collection_name) and self.config.RECREATE_COLLECTIONS:
            logging.warning(
                f"[{model_key}] Collection déjà existante → suppression en cours : '{collection_name}'"
            )
            utility.drop_collection(collection_name)

        if not utility.has_collection(collection_name):
            self.logger.info(f"Collection '{collection_name}' non trouvée. Création...")

            # Définition du schéma pour la collection prix
            fields = [
                # --- Champ clé primaire ---
                FieldSchema(
                    name="id", dtype=DataType.INT64, is_primary=True, auto_id=True
                ),
                # --- Champs obligatoires ---
                FieldSchema(
                    name="description_produit", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="nom_produit", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="valeur_prix", dtype=DataType.VARCHAR, max_length=255),
                # --- Champs optionnels ---
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(
                    name="caracteristique", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="id_categorie", dtype=DataType.VARCHAR, max_length=255
                ),
                FieldSchema(
                    name="nom_categorie", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="date_prix", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="id_lead", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_produit", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="domaine", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="id_societe_ia", dtype=DataType.VARCHAR, max_length=255
                ),
                FieldSchema(
                    name="valeur_reponse_q1", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="prix_original", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="structure_prix", dtype=DataType.VARCHAR, max_length=255
                ),
                FieldSchema(name="unite", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="devise", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="taxe", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(
                    name="type_transaction", dtype=DataType.VARCHAR, max_length=255
                ),
                FieldSchema(name="perimetre", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(
                    name="id_fournisseur", dtype=DataType.VARCHAR, max_length=255
                ),
                FieldSchema(
                    name="fournisseur", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="source_chunk_id", dtype=DataType.VARCHAR, max_length=65535
                ),
                # --- Champs chunking ---
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="chunk_number", dtype=DataType.INT64),
                FieldSchema(name="total_chunks", dtype=DataType.INT64),
                # --- Champ texte pour embedding et BM25 ---
                FieldSchema(
                    name="text",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                    enable_analyzer=True,
                ),
                # --- Champs vectoriels ---
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=model_config.dimension,
                ),
                FieldSchema(
                    name="sparse_embedding", dtype=DataType.SPARSE_FLOAT_VECTOR
                ),
                # --- Champs système ---
                FieldSchema(name="date_ajout", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=64),
            ]

            schema = CollectionSchema(
                fields,
                description=f"Collection de prix produits pour {model_key}",
                enable_dynamic_field=False,
            )

            # Ajouter la fonction BM25 pour sparse_embedding
            bm25_function = Function(
                name="text_bm25_emb",
                input_field_names=["text"],
                output_field_names=["sparse_embedding"],
                function_type=FunctionType.BM25,
            )
            schema.add_function(bm25_function)

            collection = Collection(collection_name, schema, consistency_level="Bounded")

            self.logger.info(f"[{model_key}] Création HNSW index pour l'embedding")

            # Index HNSW pour le champ embedding (dense vector)
            # index_params = {
            #     "metric_type": "COSINE",
            #     "index_type": "HNSW",
            #     "params": {
            #         "M": settings.M_PARAMS,
            #         "efConstruction": settings.EF_PARAMS,
            #     },
            # }
            # collection.create_index(field_name="embedding", index_params=index_params)
            index_params = {"metric_type": "COSINE", "index_type": "FLAT", "params": {}}
            collection.create_index(field_name="embedding", index_params=index_params)

            # Index pour le champ sparse_embedding (BM25)
            sparse_index_params = {
                "metric_type": "BM25",
                "index_type": "AUTOINDEX",
            }
            collection.create_index(
                field_name="sparse_embedding", index_params=sparse_index_params
            )

            # Index scalaires pour les filtres fréquents
            collection.create_index(field_name="source", index_name="idx_source")
            collection.create_index(
                field_name="id_produit", index_name="idx_id_produit"
            )

            self.logger.info(f"[{model_key}] ✓ Index créés.")
        else:
            self.logger.info(
                f"[{model_key}] Connexion à la collection existante : '{collection_name}'"
            )
            collection = Collection(collection_name)

        collection.load()
        self.logger.info(
            f"[{model_key}] ✓ Collection '{collection_name}' chargée et prête."
        )
        return collection

    def insert_prix_produits(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:
        model_config = PrixModelConfig()
        model_key = model_config.model_id

        try:
            self._ensure_connected()

            if not datas or self.collection is None:
                return {
                    "status": "error",
                    "message": "Aucune donnée à insérer ou collection non initialisée.",
                }

            self.logger.info(
                f"[{model_key}][PrixProduits] Insertion de batch de {len(datas)} entités dans '{self.collection.name}'..."
            )

            # Champs autorisés dans le schéma de la collection (hors auto_id et vecteurs)
            # allowed_fields = {
            #     "description_produit", "nom_produit", "valeur_prix",
            #     "source", "id_categorie", "nom_categorie", "date_prix",
            #     "id_lead", "id_produit", "domaine", "id_societe_ia",
            #     "valeur_reponse_q1", "prix_original", "structure_prix",
            #     "unite", "devise", "taxe", "type_transaction", "perimetre",
            #     "id_fournisseur", "fournisseur",
            #     "chunk_id", "chunk_number", "total_chunks",
            #     "text", "embedding",
            #     "date_ajout", "date_maj",
            # }

            sanitized_batch = []
            for data in datas:
                data["date_ajout"] = datetime.now().isoformat()
                data["date_maj"] = None

                # Filtrer les champs non présents dans le schéma
                # data = {k: v for k, v in data.items()}

                # Sanitize the record to ensure no None values
                # This is important for Milvus compatibility
                data = Utils.sanitize_record(data)
                sanitized_batch.append(data)

            result = self.collection.insert(sanitized_batch)

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
                f"[{model_key}][PrixProduits] Erreur Milvus lors de l'insertion : {e}"
            )
            self.logger.error(f"Data : {datas}")
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][PrixProduits] insertion de batch : {e}", exc_info=True
            )
            self.logger.error(f"Data : {datas}")
            self.collection = None
            raise

    def get_prix_produit(self, id_produit: int) -> Dict[str, Any]:
        list_id_produit = [id_produit]
        model_config = PrixModelConfig()
        model_key = model_config.model_id

        try:
            self._ensure_connected()

            if not self.collection:
                return {
                    "status": "error",
                    "message": "Collection non initialisée.",
                    "code": 404,
                }

            result = self.collection.query(
                expr=f"id_produit in {list_id_produit}",
                output_fields=[
                    "id",
                    "description_produit",
                    "nom_produit",
                    "valeur_prix",
                    "source",
                    "caracteristique",
                    "id_categorie",
                    "nom_categorie",
                    "date_prix",
                    "id_lead",
                    "id_produit",
                    "domaine",
                    "id_societe_ia",
                    "valeur_reponse_q1",
                    "prix_original",
                    "structure_prix",
                    "unite",
                    "devise",
                    "taxe",
                    "type_transaction",
                    "perimetre",
                    "id_fournisseur",
                    "fournisseur",
                    "text",
                ],
                consistency_level="Bounded",
            )
            self.logger.info(f"[{model_key}] ✓ Récupération terminée avec succès.")

            return {"status": "success", "data": result}

        except MilvusException as e:
            self.logger.error(
                f"[{model_key}][PrixProduit] Erreur Milvus lors de la récupération : {e}"
            )
            self.collection = None
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][PrixProduit] Erreur de Récupération du prix produit : {e}",
                exc_info=True,
            )
            self.collection = None
            raise
