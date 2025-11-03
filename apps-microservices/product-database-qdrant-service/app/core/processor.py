from common_utils.database.QdrantProduitCrud import QdrantProduitsCrud
from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud
from common_utils.database.MilvusProduitInserer import MilvusProduitInserer

from common_utils.autres.CollectionName import CollectionName
import logging
from datetime import datetime
import difflib

def insertion_data(produits_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel

    Logique d'insertion/mise à jour :
    - Si id_produit n'existe pas → Insertion
    - Si id_produit existe ET source différente → Insertion nouvelle source
    - Si id_produit existe ET source identique (Milvus uniquement) :
        → Vérifier conditions de mise à jour :
            1. Si au moins 1 champ critique différent (nom_produit, id_categorie, prix_ht, prix_ttc, type_produit) → UPDATE
            2. Si tous champs identiques → Calculer similarité text avec difflib
                - Si ratio < 0.85 → UPDATE
                - Si ratio >= 0.85 → SKIP

    Retourne: Un dictionnaire prêt à être publié.
    """
    produits   = produits_data.get("data",[])
    collection = produits_data.get("collection", CollectionName.PRODUIT)
    bdd        = produits_data.get("database", "qdrant")
    origin     = produits_data.get("origin", "bo")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None


    if(bdd.lower() == "milvus"):
        base_vectorielle = MilvusProduitsCrud()
    else:
        base_vectorielle = QdrantProduitsCrud()

    processing_functions = {
        CollectionName.PRODUIT: base_vectorielle.insert_produits,
    }

    func = processing_functions.get(collection_enum)
    result = []

    if func and len(produits) > 0:
        id_produit = produits[0].get('id_produit', 'ID produit inconnu')
        res = base_vectorielle.get_produit(id_produit=id_produit)
        correspondance_produit = MilvusProduitInserer()

        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")
        data_bo_milvus = []

        # CAS 1 : Produit n'existe pas (404)
        if status == "error":
            if code == 404:
                result = func(produits)
                if not result:  # None, {}, ou False
                    id_produit_milvus = ""
                else:
                    id_produit_milvus = result.get("ids", "")
                output_message = {
                    "database"      : bdd,
                    "collection"    : collection,
                    "data"          : result,
                    "id_produit"    : id_produit,
                    "already_in_bdd": False,
                    "updated"       : False,
                    "origin"        : origin
                }
                data_bo_milvus.append({
                    "embedding"       : [0.0]*1024,
                    "id_produit"       : id_produit,
                    "id_produit_milvus": result.get("ids", ""),
                    "date_ajout"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date_maj"         : "",
                    "origin"           : origin
                })
            else:
                logging.error("Erreur lors de la vérification du produit ID  %s : %s", id_produit, message)
                output_message = {
                    "database"  : bdd,
                    "collection": collection,
                    "data"      : [],
                    "id_produit": id_produit,
                    "error"     : message,
                    "origin"    : origin
                }

        # CAS 2 : Produit existe déjà
        elif status == "success":
            if len(data) > 0:
                # Récupérer la source du produit existant en base
                existing_sources = [item.get('source', '') for item in data]
                existing_sources_set = set(existing_sources)

                # Normaliser la source à insérer
                source_to_insert = origin.upper()

                # SOUS-CAS A : Source DIFFÉRENTE - Insérer nouvelle source
                if source_to_insert not in existing_sources_set:
                    logging.info(f"Le produit ID {id_produit} : source {source_to_insert} n'existe pas. Insertion autorisée.")
                    result = func(produits)
                    if not result:
                        id_produit_milvus = ""
                    else:
                        id_produit_milvus = result.get("ids", "")

                    output_message = {
                        "database"      : bdd,
                        "collection"    : collection,
                        "data"          : result,
                        "id_produit"    : id_produit,
                        "already_in_bdd": True,
                        "updated"       : False,
                        "origin"        : origin
                    }

                    data_bo_milvus.append({
                        "embedding"       : [0.0]*1024,
                        "id_produit"       : id_produit,
                        "id_produit_milvus": id_produit_milvus,
                        "date_ajout"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "date_maj"         : "",
                        "origin"           : origin
                    })

                # SOUS-CAS B : Source IDENTIQUE - Vérifier conditions de mise à jour (Milvus uniquement)
                else:
                    # Trouver le record exact avec la même source
                    existing_record = next(
                        (item for item in data if item.get('source', '').upper() == source_to_insert),
                        None
                    )

                    if bdd.lower() == "milvus" and existing_record:
                        # Définir les 5 champs critiques à comparer
                        critical_fields = ["nom_produit", "id_categorie", "prix_ht", "prix_ttc", "type_produit"]

                        # Comparer les champs critiques
                        fields_changed = []
                        for field in critical_fields:
                            old_value = existing_record.get(field, "")
                            new_value = produits[0].get(field, "")

                            # Conversion en string pour comparaison uniforme
                            if str(old_value) != str(new_value):
                                fields_changed.append(field)

                        should_update = False
                        update_reason = ""

                        # CONDITION 1 : Au moins un champ critique a changé
                        if len(fields_changed) > 0:
                            should_update = True
                            update_reason = f"field_change: {', '.join(fields_changed)}"
                            logging.info(f"Produit ID {id_produit} : champs critiques différents ({', '.join(fields_changed)}). Mise à jour requise.")

                        # CONDITION 2 : Tous champs identiques, vérifier similarité du texte
                        else:
                            old_text = existing_record.get("text", "")
                            new_text = produits[0].get("text", "")

                            # Calculer la similarité avec difflib
                            similarity_ratio = difflib.SequenceMatcher(None, old_text, new_text).ratio()

                            if similarity_ratio < 0.85:
                                should_update = True
                                update_reason = f"text_similarity: {similarity_ratio:.2f}"
                                logging.info(f"Produit ID {id_produit} : similarité text {similarity_ratio:.2f} < 0.85. Mise à jour requise.")
                            else:
                                logging.info(f"Produit ID {id_produit} : similarité text {similarity_ratio:.2f} >= 0.85. Pas de mise à jour.")

                        # Exécuter la mise à jour si nécessaire
                        if should_update:
                            logging.info(f"Mise à jour du produit ID {id_produit}. Raison: {update_reason}")
                            result = base_vectorielle.update_produits(
                                produits,
                                id_produit,
                                correspondance_produit
                            )

                            output_message = {
                                "database"      : bdd,
                                "collection"    : collection,
                                "data"          : result.get("data"),
                                "id_produit"    : id_produit,
                                "already_in_bdd": True,
                                "updated"       : True,
                                "update_reason" : update_reason,
                                "origin"        : origin
                            }
                        else:
                            # SKIP - données identiques
                            logging.info(f"Le produit ID {id_produit} : source {source_to_insert} existe déjà et données identiques. Insertion ignorée.")
                            result = data
                            output_message = {
                                "database"      : bdd,
                                "collection"    : collection,
                                "data"          : result,
                                "id_produit"    : id_produit,
                                "already_in_bdd": True,
                                "updated"       : False,
                                "origin"        : origin
                            }

                    # Qdrant : garder l'ancien comportement (skip)
                    else:
                        logging.info(f"Le produit ID {id_produit} : source {source_to_insert} existe déjà. Insertion ignorée.")
                        result = data
                        output_message = {
                            "database"      : bdd,
                            "collection"    : collection,
                            "data"          : result,
                            "id_produit"    : id_produit,
                            "already_in_bdd": True,
                            "updated"       : False,
                            "origin"        : origin
                        }
            else:
                # Cas où data est vide mais status success (ne devrait pas arriver)
                result = func(produits)
                if not result:  # None, {}, ou False
                    id_produit_milvus = ""
                else:
                    id_produit_milvus = result.get("ids", "")
                data_bo_milvus.append({
                    "embedding"       : [0.0]*1024,
                    "id_produit"       : id_produit,
                    "id_produit_milvus": id_produit_milvus,
                    "date_ajout"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date_maj"         : "",
                    "origin"           : origin
                })

                output_message = {
                    "database"      : bdd,
                    "collection"    : collection,
                    "data"          : result,
                    "id_produit"    : id_produit,
                    "already_in_bdd": False,
                    "updated"       : False,
                    "origin"        : origin
                }

    # Insérer la correspondance si nécessaire (uniquement pour les insertions, pas les updates)
    # On vérifie également que id_produit_milvus est non vide avant d'insérer
    if len(data_bo_milvus) > 0 and bdd == "milvus":
        # Filtrer uniquement les entrées avec id_produit_milvus non vide
        data_bo_milvus_valid = [
            item for item in data_bo_milvus
            if item.get("id_produit_milvus") and item.get("id_produit_milvus") != ""
        ]

        if len(data_bo_milvus_valid) > 0:
            res_correspondance = correspondance_produit.insert_correpondance_produit(data_bo_milvus_valid)
            logging.info(f"Correspondance insérée pour {len(data_bo_milvus_valid)} produit(s)")
        else:
            logging.warning(f"Aucune correspondance à insérer : id_produit_milvus vide pour le produit ID {id_produit}")

    return output_message
