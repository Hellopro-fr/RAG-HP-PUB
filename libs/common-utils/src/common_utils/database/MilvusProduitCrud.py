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
    collection_name: str = "produits_3"
    dimension: int = 1024

class MilvusProduitsCrud:
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
                #TODO a completer / verifier
                FieldSchema(name="id", dtype=DataType.INT64 , is_primary = True , auto_id = True ,max_length=64),
                FieldSchema(name="id_produit", dtype=DataType.VARCHAR , max_length=64),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=model_config.dimension),
                FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="nom_produit", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="page_type", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fichier_source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="etat", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="affichage", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="date_ajout", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="sku", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="ean", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="url_images", dtype=DataType.VARCHAR, max_length=4095),
                FieldSchema(name="reference", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="prix_ht", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="prix_ttc", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="statut", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="remise", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="stock", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="delai_livraison", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="marque", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fabricant", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="garantie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="normes", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="frais_de_port", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="caracteristique", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="type_produit", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="montant_eco_participation", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source_produits", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR , max_length=65535),
                FieldSchema(name="chunk_number", dtype=DataType.INT64),
                FieldSchema(name="total_chunks", dtype=DataType.INT64),

            ]
            schema = CollectionSchema(fields, description=f"Collection de chunks de Produit pour {model_key}")
            collection = Collection(
                collection_name, 
                schema,
                consistency_level="Strong"
            )
            
            self.logger.info(f"[{model_key}] Création HNSW index pour l'embedding")

            # TODO : Vérifier les paramètres d'indexation
            # Exemple d'indexation HNSW pour les embeddings
            index_params = {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": settings.M_PARAMS, "efConstruction": settings.EF_PARAMS}}
            collection.create_index(field_name="embedding", index_params=index_params)

            # Optionnel: Créer des index scalaires pour les filtres fréquents
            collection.create_index(field_name="id_produit", index_name="idx_produit")
            # collection.create_index(field_name="categorie", index_name="idx_categorie")
            # collection.create_index(field_name="id_categorie", index_name="idx_id_categorie")
            # collection.create_index(field_name="fournisseur", index_name="idx_fournisseur")
            # collection.create_index(field_name="affichage", index_name="idx_affichage")
            # collection.create_index(field_name="etat", index_name="idx_etat")

            self.logger.info(f"[{model_key}] ✓ Index créés.")
        else:
            self.logger.info(f"[{model_key}] Connexion à la collection existante : '{collection_name}'")
            collection = Collection(collection_name)
        
        collection.load()
        self.logger.info(f"[{model_key}] ✓ Collection '{collection_name}' chargée et prête.")
        return collection


    def insert_produits(self, datas: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            
            self.logger.info(f"[{model_key}][Produits] Insertion de batch de {len(datas)} entités dans '{self.collection.name}'...")
           
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
                "ids": ','.join(map(str, result.primary_keys)) if result.primary_keys else "",
                "status": "success",
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Produits] Erreur Milvus lors de l'insertion : {e}")
            self.logger.error(f"Data : {datas}")
        except Exception as e:
            self.logger.error(f"[{model_key}][Produits] insertion de batch : {e}", exc_info=True)
            self.logger.error(f"Data : {datas}")
    
    def update_produits(self, data: Dict[str, Any]) -> Dict[str, Any]:
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
                self.logger.error(f"[{model_key}][Produits] Mise à jour sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la mise à jour."
                }

            self.logger.info(f"[{model_key}][Produits] Mise à jour de batch de {len(data)} entités dans '{self.collection.name}'...")
            
            
            data["date_maj"] = datetime.now().isoformat()  # ex: "2025-08-18T14:23:45.123456"

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
            self.logger.error(f"[{model_key}][Produits] Erreur Milvus lors de mise à jour : {e}")
            self.logger.error(f"Data : {data}")
        except Exception as e:
            self.logger.error(f"[{model_key}][Produits] Mise à jour de batch : {e}", exc_info=True)
            self.logger.error(f"Data : {data}")

    def delete_produits(self,data: Dict[str, Any]) -> Dict[str, Any]:
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
                self.logger.error(f"[{model_key}][Produits] Suppression sans ID.")
                return {
                    "status": "error",
                    "message": "Clé primaire (ID) requise pour la suppression."
                }

            self.logger.info(f"[{model_key}][Produits] Suppression de l'entité avec ID {id_entity_milvus} dans '{self.collection.name}'...")
            result = self.collection.delete(f"id == {id_entity_milvus}")
            self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Suppression terminée avec succès.")

            return {
                "status": "success",
                "message": f"Echange avec ID {id_entity_milvus} supprimé."
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Produits] Erreur Milvus lors de la suppression : {e}")
        except Exception as e:
            self.logger.error(f"[{model_key}][Produits] Suppression : {e}", exc_info=True)

    def get_produit(self,id_produit: str) -> Dict[str, Any]:
        list_id_produit = [id_produit]
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

            if not id_produit:
                return {
                    "status": "error",
                    "message": "id_produit requise pour la récupération.",
                    "code" : 400
                }

            result = self.collection.query(
                expr=f"id_produit in {list_id_produit}",
                output_fields=["id"]
            )
            #self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Récupèration terminée avec succès.")

            return {
                "status": "success",
                "data": result
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Produit] Erreur Milvus lors de la récupération : {e}")
        except Exception as e:
            self.logger.error(f"[{model_key}][Produit] Erreur de Récupèration du produit : {e}", exc_info=True)
            
    def get_produit_by_field(self,field_name:str, search_value: str) -> Dict[str, Any]:
        list_search_value = [search_value]
        model_config = ModelConfig()
        model_key = model_config.model_id
        
        if not field_name :
            field_name = "nom_produit"
        
        try:
            self._connect_to_milvus()
            self.collection = self._get_or_create_collection(model_config)

            if not self.collection:
                return {
                    "status": "error",
                    "message": "Collection non initialisée.",
                    "code": 404
                }

            if not search_value:
                return {
                    "status": "error",
                    "message": "search_value requise pour la récupération.",
                    "code" : 400
                }

            result = self.collection.query(
                expr=f"{field_name} in {list_search_value}",
                output_fields=["id"]
            )
            #self.collection.flush()
            self.logger.info(f"[{model_key}] ✓ Récupèration terminée avec succès.")

            return {
                "status": "success",
                "data": result
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}][Produit] Erreur Milvus lors de la récupération : {e}")
        except Exception as e:
            self.logger.error(f"[{model_key}][Produit] Erreur de Récupèration du produit : {e}", exc_info=True)

    def get_produit_rest(self, id_produit_milvus: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        

        print("get_produit_rest - id_produit_milvus:", id_produit_milvus)
        print("get_produit_rest - metadata:", metadata)

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

            expr_parts = []

            # Filtrage par ID (clé primaire)
            if id_produit_milvus is not None:
                expr_parts.append(f"id == {id_produit_milvus}")

            # Filtrage par metadata (clé=valeur)
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, str):
                        expr_parts.append(f'{key} == "{value}"')
                    else:
                        expr_parts.append(f"{key} == {value}")
            print("expr_parts:", expr_parts)
            # Aucun filtre fourni ?
            if not expr_parts:
                return {
                    "status": "error",
                    "message": "Aucun critère de recherche fourni (id_produit_milvus ou metadata).",
                    "code": 400
                }

            # Construction de l'expression finale
            expr = " and ".join(expr_parts)

            # Champs à retourner (tu peux les adapter)
            output_fields = [
                "id",
                "id_produit",
                "nom_produit",
                "id_fournisseur",
                "fournisseur",
                "id_categorie",
                "categorie",
                "chunk_id"
            ]

            self.logger.info(f"[{model_key}] Requête Milvus : {expr}")

            results = self.collection.query(expr=expr, output_fields=output_fields)

            return {
                "status": "success",
                "filters": {
                    "id_produit_milvus": id_produit_milvus,
                    "metadata": metadata,
                    "expr" : expr
                },
                "data": results
            }

        except MilvusException as e:
            self.logger.error(f"[{model_key}] Erreur Milvus lors de la récupération : {e}")
            return {
                "status": "error",
                "message": str(e),
                "code": 500
            }

        except Exception as e:
            self.logger.error(f"[{model_key}] Erreur interne : {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "code": 500
            }
