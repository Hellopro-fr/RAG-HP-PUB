import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from common_utils.database.config.settings import Configuration, settings
from common_utils.database.Utils import Utils
from common_utils.database.milvus_lock import milvus_connection_lock

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
class ModelConfig:
    model_id: str = settings.MODEL
    collection_name: str = "produits_3"
    dimension: int = 1024


class MilvusProduitsCrud:
    _CONNECTION_ALIAS = "milvus_produits_3"

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
        self.logger.debug("Connexion sur Zilliz cloud...")
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
        self.logger.debug("Connexion sur Zilliz cloud avec succès.")

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
            self.logger.warning(
                f"[{model_key}] Collection déjà existante, suppression en cours : '{collection_name}'"
            )
            utility.drop_collection(collection_name, using=self._CONNECTION_ALIAS)

        if not utility.has_collection(collection_name, using=self._CONNECTION_ALIAS):
            self.logger.debug(f"Collection '{collection_name}' non trouvée. Création...")
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
                FieldSchema(name="id_produit", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=model_config.dimension,
                ),
                FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="nom_produit", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="page_type", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="fournisseur", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="id_fournisseur", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="id_categorie", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="fichier_source", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="etat", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="affichage", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="date_ajout", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="text",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                    enable_analyzer=True,
                ),
                FieldSchema(name="sku", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="ean", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="url_images", dtype=DataType.VARCHAR, max_length=4095),
                FieldSchema(name="reference", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="prix_ht", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="prix_ttc", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="statut", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="remise", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="stock", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="delai_livraison", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="marque", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fabricant", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="garantie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="normes", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="frais_de_port", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="caracteristique", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="type_produit", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(
                    name="montant_eco_participation",
                    dtype=DataType.VARCHAR,
                    max_length=65535,
                ),
                FieldSchema(
                    name="source_produits", dtype=DataType.VARCHAR, max_length=65535
                ),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="chunk_number", dtype=DataType.INT64),
                FieldSchema(name="total_chunks", dtype=DataType.INT64),
                FieldSchema(
                    name="sparse_embedding", dtype=DataType.SPARSE_FLOAT_VECTOR
                ),
            ]
            schema = CollectionSchema(
                fields, description=f"Collection de chunks de Produit pour {model_key}"
            )

            # Ajouter la fonction BM25 pour sparse_embedding
            bm25_function = Function(
                name="text_bm25_emb",
                input_field_names=["text"],
                output_field_names=["sparse_embedding"],
                function_type=FunctionType.BM25,
            )
            schema.add_function(bm25_function)

            collection = Collection(collection_name, schema, consistency_level="Bounded", using=self._CONNECTION_ALIAS)

            self.logger.info(f"[{model_key}] Création FLAT index pour l'embedding")

            # TODO : Vérifier les paramètres d'indexation
            # Exemple d'indexation HNSW pour les embeddings
            # index_params = {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": settings.M_PARAMS, "efConstruction": settings.EF_PARAMS}}
            # Index FLAT pour le champ embedding (dense vector)
            index_params = {"metric_type": "COSINE", "index_type": "FLAT", "params": {}}
            collection.create_index(field_name="embedding", index_params=index_params)

            # Index pour le champ sparse_embedding (BM25)
            sparse_index_params = {
                "index_type": "SPARSE_INVERTED_INDEX",
                "metric_type": "BM25",
                "params": {"drop_ratio_build": 0.2},
            }
            collection.create_index(
                field_name="sparse_embedding", index_params=sparse_index_params
            )

            # Optionnel: Créer des index scalaires pour les filtres fréquents
            collection.create_index(field_name="id_produit", index_name="idx_produit")
            # collection.create_index(field_name="categorie", index_name="idx_categorie")
            # collection.create_index(field_name="id_categorie", index_name="idx_id_categorie")
            # collection.create_index(field_name="fournisseur", index_name="idx_fournisseur")
            # collection.create_index(field_name="affichage", index_name="idx_affichage")
            # collection.create_index(field_name="etat", index_name="idx_etat")

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

    def insert_produits(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:
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

                # Truncate url_images to fit the VARCHAR(4095) schema limit (bytes, not chars)
                # This field is not used in RAG search, so truncation is safe
                url_images = data.get("url_images", "")
                if len(url_images.encode("utf-8")) > 4095:
                    data["url_images"] = url_images.encode("utf-8")[:4095].decode("utf-8", errors="ignore")

                sanitized_batch.append(data)

            result = self.collection.insert(sanitized_batch)

            self.logger.debug(f"Résultat insertion : {result}")
            self.logger.debug(f"Clé primaire : {result.primary_keys}")

            self.logger.info(f"[{model_key}] Insertion terminée avec succès.")

            return {
                "ids": (
                    ",".join(map(str, result.primary_keys))
                    if result.primary_keys
                    else ""
                ),
                "status": "success",
            }

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][Produits] Erreur Milvus lors de l'insertion : {e}"
            )
            self.logger.error(f"Data : {datas}")
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Produits] insertion de batch : {e}", exc_info=True
            )
            self.logger.error(f"Data : {datas}")
            raise

    def update_produits(
        self,
        produits: List[Dict[str, Any]],
        id_produit: str,
        correspondance_produit,
        origin: str = "bo",
    ) -> Dict[str, Any]:
        """
        Met à jour les produits pour un id_produit donné
        Logique: DELETE ancien + INSERT nouveau + MAJ correspondance

        Args:
            produits: Liste des nouveaux produits à insérer
            id_produit: L'identifiant du produit à mettre à jour
            correspondance_produit: Instance de MilvusProduitInserer pour gérer la correspondance
            origin: Source du produit (bo, siteweb, api, etc.)

        Returns:
            Dict avec status, data et flags (already_in_bdd, updated)
        """
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not produits or len(produits) == 0:
                return {"status": "error", "message": "Aucune donnée à mettre à jour."}

            self.logger.info(
                f"[{model_key}][Produits] Début mise à jour pour id_produit: {id_produit}"
            )

            # Déterminer la source à partir du premier produit
            source = (
                produits[0].get("source", origin.upper())
                if len(produits) > 0
                else origin.upper()
            )

            self.logger.info(
                f"[{model_key}][Produits] Suppression des anciens produits avec id_produit={id_produit} et source={source}"
            )

            # 1. Supprimer TOUS les produits avec ce id_produit ET cette source
            # Cette méthode est plus robuste car elle ne dépend pas de la table de correspondance
            delete_result = self.delete_produits_by_id_produit_and_source(
                id_produit, source
            )
            if delete_result["status"] == "error":
                self.logger.error(
                    f"[{model_key}][Produits] Erreur suppression: {delete_result['message']}"
                )
                return {
                    "status": "error",
                    "message": f"Échec suppression produits: {delete_result['message']}",
                }

            # 2. Supprimer dans la table de correspondance
            # Note: On utilise id_produit + origin (pas source) car la table de correspondance utilise origin
            delete_corr_result = (
                correspondance_produit.delete_correspondance_by_id_produit_and_origin(
                    id_produit, origin
                )
            )
            if delete_corr_result["status"] == "error":
                self.logger.error(
                    f"[{model_key}][Produits] Erreur suppression correspondance: {delete_corr_result['message']}"
                )
                return {
                    "status": "error",
                    "message": f"Échec suppression correspondance: {delete_corr_result['message']}",
                }

            self.logger.info(
                f"[{model_key}][Produits] Suppression réussie pour id_produit={id_produit}, source={source}. Réinsertion en cours..."
            )

            # 5. Ajouter date_maj à tous les produits avant réinsertion
            date_maj = datetime.now().isoformat()
            for produit in produits:
                produit["date_maj"] = date_maj

            # 6. Réinsérer les nouvelles données
            insert_result = self.insert_produits(produits)

            if insert_result and insert_result.get("status") == "success":
                # 7. Réinsérer dans la table de correspondance avec l'origin passé en paramètre
                data_bo_milvus = [
                    {
                        "embedding": [0.0] * 1024,
                        "id_produit_milvus": insert_result.get("ids", ""),
                        "id_produit": id_produit,
                        "origin": origin,  # Utilise l'origin passé en paramètre
                        "date_ajout": datetime.now().isoformat(),
                        "date_maj": datetime.now().isoformat(),
                    }
                ]
                correspondance_produit.insert_correpondance_produit(data_bo_milvus)

                self.logger.info(
                    f"[{model_key}][Produits] Mise à jour terminée avec succès."
                )

                return {
                    "status": "success",
                    "data": insert_result,
                    "already_in_bdd": True,
                    "updated": True,
                }
            else:
                return {
                    "status": "error",
                    "message": "Échec de la réinsertion après suppression",
                }

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][Produits] Erreur Milvus lors de mise à jour : {e}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Produits] Mise à jour : {e}", exc_info=True
            )
            raise

    def delete_produits(self, data: Dict[str, Any]) -> Dict[str, Any]:
        model_config = ModelConfig()
        model_key = model_config.model_id
        id_entity_milvus = data.get("id")

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not id_entity_milvus:
                self.logger.error(f"[{model_key}][Produits] Suppression sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la suppression.",
                }

            self.logger.info(
                f"[{model_key}][Produits] Suppression de l'entité avec ID {id_entity_milvus} dans '{self.collection.name}'..."
            )
            result = self.collection.delete(f"id == {id_entity_milvus}")
            self.collection.flush()
            self.logger.info(f"[{model_key}] Suppression terminée avec succès.")

            return {
                "status": "success",
                "message": f"Produit avec ID {id_entity_milvus} supprimé.",
            }

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][Produits] Erreur Milvus lors de la suppression : {e}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Produits] Suppression : {e}", exc_info=True
            )
            raise

    def delete_produits_by_ids(self, ids: List[int]) -> Dict[str, Any]:
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
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not ids or len(ids) == 0:
                self.logger.error(f"[{model_key}][Produits] Suppression sans IDs.")
                return {
                    "status": "error",
                    "message": "Liste d'IDs requise pour la suppression.",
                }

            self.logger.info(
                f"[{model_key}][Produits] Suppression de {len(ids)} entités avec IDs {ids} dans '{self.collection.name}'..."
            )

            # Construire l'expression pour Milvus
            ids_str = ", ".join(map(str, ids))
            expr = f"id in [{ids_str}]"

            self.collection.delete(expr)
            self.collection.flush()

            self.logger.info(f"[{model_key}] Suppression terminée avec succès.")

            return {"status": "success", "message": f"{len(ids)} produits supprimés."}

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][Produits] Erreur Milvus lors de la suppression : {e}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Produits] Suppression : {e}", exc_info=True
            )
            raise

    def delete_produits_by_id_produit_and_source(
        self, id_produit: str, source: str
    ) -> Dict[str, Any]:
        """
        Supprime tous les produits ayant un id_produit et une source donnés
        Cette méthode est plus sûre que delete_produits_by_ids car elle ne dépend pas de la table de correspondance

        Args:
            id_produit: L'identifiant du produit
            source: La source du produit (BO, SITEWEB, API, etc.)

        Returns:
            Dict avec status et message
        """
        model_config = ModelConfig()
        model_key = model_config.model_id

        try:
            self._ensure_connected()

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée."}

            if not id_produit or not source:
                self.logger.error(
                    f"[{model_key}][Produits] Suppression sans id_produit ou source."
                )
                return {
                    "status": "error",
                    "message": "id_produit et source requis pour la suppression.",
                }

            # Construire l'expression pour Milvus
            expr = f'id_produit == "{id_produit}" && source == "{source}"'

            self.logger.info(
                f"[{model_key}][Produits] Suppression avec expression: {expr}"
            )

            self.collection.delete(expr)
            self.collection.flush()

            self.logger.info(f"[{model_key}] Suppression terminée avec succès.")

            return {
                "status": "success",
                "message": f"Produits avec id_produit={id_produit} et source={source} supprimés.",
            }

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][Produits] Erreur Milvus lors de la suppression : {e}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Produits] Suppression : {e}", exc_info=True
            )
            raise

    def get_produit(self, id_produit: str) -> Dict[str, Any]:
        list_id_produit = [id_produit]
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

            if not id_produit:
                return {
                    "status": "error",
                    "message": "id_produit requise pour la récupération.",
                    "code": 400,
                }

            result = self.collection.query(
                expr=f"id_produit in {list_id_produit}",
                output_fields=[
                    "id",
                    "source",
                    "nom_produit",
                    "id_categorie",
                    "prix_ht",
                    "prix_ttc",
                    "type_produit",
                    "text",
                ],
                consistency_level="Bounded",
            )
            # self.collection.flush()
            self.logger.info(f"[{model_key}] Récupèration terminée avec succès.")

            return {"status": "success", "data": result}

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][Produit] Erreur Milvus lors de la récupération : {e}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Produit] Erreur de Récupèration du produit : {e}",
                exc_info=True,
            )
            raise

    def get_produit_by_field(
        self, field_name: str, search_value: str
    ) -> Dict[str, Any]:
        ALLOWED_FIELDS = {
            "id_produit", "nom_produit", "categorie", "id_categorie",
            "fournisseur", "id_fournisseur", "domaine", "source", "sku",
            "ean", "reference", "marque", "type_produit", "url",
            "page_type", "fichier_source", "etat", "affichage",
            "date_ajout", "date_maj", "text", "url_images", "prix_ht",
            "prix_ttc", "statut", "remise", "stock", "delai_livraison",
            "fabricant", "garantie", "normes", "frais_de_port",
            "caracteristique", "montant_eco_participation",
            "source_produits", "chunk_id",
        }
        if not field_name:
            field_name = "nom_produit"
        if field_name not in ALLOWED_FIELDS:
            raise ValueError(f"Invalid field name: {field_name}. Allowed: {ALLOWED_FIELDS}")

        list_search_value = [search_value]
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
            self.logger.info(f"[{model_key}] Récupèration terminée avec succès.")

            return {"status": "success", "data": result}

        except MilvusException as e:
            self.collection = None  # Force reconnection on next call
            self.logger.error(
                f"[{model_key}][Produit] Erreur Milvus lors de la récupération : {e}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"[{model_key}][Produit] Erreur de Récupèration du produit : {e}",
                exc_info=True,
            )
            raise
