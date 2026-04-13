from common_utils.database.QdrantProduitCrud import QdrantProduitsCrud
from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud
from common_utils.database.MilvusProduitInserer import MilvusProduitInserer

from common_utils.autres.CollectionName import CollectionName
import logging
from datetime import datetime
import difflib


logger = logging.getLogger(__name__)

# Module-level singletons — persist across messages, reuse cached connections
_milvus_produit_crud = MilvusProduitsCrud()
_qdrant_produit_crud = QdrantProduitsCrud()
_correspondance_produit = MilvusProduitInserer()

# Initialized by main.py at startup
_concurrency_guard = None


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
    produits = produits_data.get("data", [])
    collection = produits_data.get("collection", CollectionName.PRODUIT)
    bdd = produits_data.get("database", "qdrant")
    origin = produits_data.get("origin", "bo")
    mode = produits_data.get("mode", "").lower()

    # print(f"═══════════════════════════════════════════════════════════")
    # print(f"🔄 DÉBUT TRAITEMENT - Database: {bdd}, Collection: {collection}, Origin: {origin}")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        raise ValueError(f"'{collection}' n'est pas un nom de collection valide.")

    if bdd.lower() == "milvus":
        base_vectorielle = _milvus_produit_crud
    else:
        base_vectorielle = _qdrant_produit_crud

    processing_functions = {
        CollectionName.PRODUIT: base_vectorielle.insert_produits,
    }

    func = processing_functions.get(collection_enum)
    result = []

    if not func or len(produits) <= 0:
        raise ValueError(
            "Aucune donnée de produit fournie ou fonction de traitement invalide."
        )

    # Wrap all Milvus operations in concurrency guard
    if _concurrency_guard:
        with _concurrency_guard.slot():
            return _do_milvus_operations(
                produits, bdd, collection, base_vectorielle, func, origin, mode
            )
    return _do_milvus_operations(
        produits, bdd, collection, base_vectorielle, func, origin, mode
    )


def _do_milvus_operations(produits, bdd, collection, base_vectorielle, func, origin, mode):
    """Execute all Milvus/Qdrant operations for a product insertion."""
    id_produit = produits[0].get("id_produit", "ID produit inconnu")
    # print(f"📦 Produit ID: {id_produit} | Nombre de chunks: {len(produits)}")

    res = base_vectorielle.get_produit(id_produit=id_produit)
    correspondance_produit = _correspondance_produit

    status = res.get("status")
    data = res.get("data", [])
    code = res.get("code", None)
    message = res.get("message", "")
    data_bo_milvus = []
    output_message = {}

    # print(f"🔍 Vérification produit - Status: {status}, Code: {code}, Data count: {len(data)}")

    # CAS 1 : Produit n'existe pas (404)
    if status == "error":
        if code == 404:
            # print(f"✅ CAS 1 - PRODUIT INEXISTANT (404) → INSERTION")
            # Ajouter le champ source aux produits avant insertion
            for produit in produits:
                produit["source"] = origin.upper()
            # print(f"📝 Champ 'source' ajouté aux produits: {origin.upper()}")
            result = func(produits)
            if not result or result.get("status") == "error":
                raise Exception(f"L'insertion a échoué. Résultat: {result}")
            else:
                id_produit_milvus = result.get("ids", "")
                # print(f"✅ Insertion réussie - ID Milvus: {id_produit_milvus}")
            output_message = {
                "database": bdd,
                "collection": collection,
                "data": result,
                "id_produit": id_produit,
                "already_in_bdd": False,
                "updated": False,
                "origin": origin,
            }
            data_bo_milvus.append(
                {
                    "embedding": [0.0] * 1024,
                    "id_produit": id_produit,
                    "id_produit_milvus": result.get("ids", ""),
                    "date_ajout": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date_maj": "",
                    "origin": origin,
                }
            )
        else:
            error_message = (
                f"Erreur lors de la vérification du produit ID {id_produit} : {message}"
            )
            logging.error(f"❌ CAS 1 - ERREUR (Code {code}) {error_message}")
            raise Exception(error_message)

    # CAS 2 : Produit existe déjà
    elif status == "success":
        # print(f"📋 CAS 2 - PRODUIT EXISTE DÉJÀ")
        if len(data) > 0:
            # Récupérer la source du produit existant en base
            existing_sources = [item.get("source", "") for item in data]
            existing_sources_set = set(existing_sources)

            # Normaliser la source à insérer
            source_to_insert = origin.upper()

            # print(f"🔎 Sources existantes: {existing_sources_set} | Source à insérer: {source_to_insert}")

            # SOUS-CAS A : Source DIFFÉRENTE - Insérer nouvelle source
            if source_to_insert not in existing_sources_set:
                # print(f"✅ SOUS-CAS 2A - SOURCE DIFFÉRENTE → INSERTION de nouvelle source {source_to_insert}")
                # Ajouter le champ source aux produits avant insertion
                for produit in produits:
                    produit["source"] = source_to_insert
                # print(f"📝 Champ 'source' ajouté aux produits: {source_to_insert}")
                result = func(produits)
                if not result or result.get("status") == "error":
                    raise Exception(
                        f"L'insertion de la nouvelle source a échoué. Résultat: {result}"
                    )
                else:
                    id_produit_milvus = result.get("ids", "")
                    # print(f"✅ Insertion nouvelle source réussie - ID Milvus: {id_produit_milvus}")

                output_message = {
                    "database": bdd,
                    "collection": collection,
                    "data": result,
                    "id_produit": id_produit,
                    "already_in_bdd": True,
                    "updated": False,
                    "origin": origin,
                }

                data_bo_milvus.append(
                    {
                        "embedding": [0.0] * 1024,
                        "id_produit": id_produit,
                        "id_produit_milvus": id_produit_milvus,
                        "date_ajout": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "date_maj": "",
                        "origin": origin,
                    }
                )

            # SOUS-CAS B : Source IDENTIQUE - Vérifier conditions de mise à jour (Milvus uniquement)
            else:
                # print(f"🔄 SOUS-CAS 2B - SOURCE IDENTIQUE ({source_to_insert})")
                # Trouver le record exact avec la même source
                existing_record = next(
                    (
                        item
                        for item in data
                        if item.get("source", "").upper() == source_to_insert
                    ),
                    None,
                )

                if bdd.lower() == "milvus" and existing_record:
                    should_update = False
                    update_reason = ""

                    # MODE UPDATE : Forcer la mise à jour sans vérification
                    if mode == "update":
                        should_update = True
                        update_reason = "forced_update: mode=update"
                        logging.info(
                            f"Mode 'update' activé pour id_produit={id_produit} → mise à jour forcée"
                        )
                    else:
                        # print(f"🔍 Mode MILVUS - Vérification des conditions de mise à jour")
                        # Définir les 5 champs critiques à comparer
                        critical_fields = [
                            "nom_produit",
                            "id_categorie",
                            "prix_ht",
                            "prix_ttc",
                            "type_produit",
                        ]

                        # Comparer les champs critiques
                        fields_changed = []
                        for field in critical_fields:
                            old_value = existing_record.get(field, "")
                            new_value = produits[0].get(field, "")

                            # Conversion en string pour comparaison uniforme
                            if str(old_value) != str(new_value):
                                fields_changed.append(field)

                        # CONDITION 1 : Au moins un champ critique a changé
                        if len(fields_changed) > 0:
                            should_update = True
                            update_reason = f"field_change: {', '.join(fields_changed)}"
                            # print(f"🔄 CONDITION 1 ACTIVÉE - Champs critiques modifiés: {', '.join(fields_changed)} → UPDATE")

                        # CONDITION 2 : Tous champs identiques, vérifier similarité du texte
                        else:
                            # print(f"✅ CONDITION 1 NON ACTIVÉE - Tous les champs critiques sont identiques")
                            old_text = existing_record.get("text", "")
                            new_text = produits[0].get("text", "")

                            # Calculer la similarité avec difflib
                            similarity_ratio = difflib.SequenceMatcher(
                                None, old_text, new_text
                            ).ratio()
                            # print(f"📊 Calcul similarité textuelle: {similarity_ratio:.4f}")

                            if similarity_ratio < 0.85:
                                should_update = True
                                update_reason = f"text_similarity: {similarity_ratio:.2f}"
                                # print(f"🔄 CONDITION 2 ACTIVÉE - Similarité {similarity_ratio:.2f} < 0.85 → UPDATE")
                            else:
                                pass
                                # print(f"⏭️  CONDITION 2 NON ACTIVÉE - Similarité {similarity_ratio:.2f} >= 0.85 → SKIP")

                    # Exécuter la mise à jour si nécessaire
                    if should_update:
                        # print(f"✅ DÉCISION: UPDATE - Raison: {update_reason}")
                        # Ajouter le champ source aux produits avant update
                        for produit in produits:
                            produit["source"] = source_to_insert
                        # print(f"📝 Champ 'source' ajouté aux produits: {source_to_insert}")
                        result = base_vectorielle.update_produits(
                            produits,
                            id_produit,
                            correspondance_produit,
                            origin,  # Passer l'origin pour la table de correspondance
                        )
                        if not result or result.get("status") == "error":
                            raise Exception(
                                f"La mise à jour a échoué. Résultat: {result}"
                            )

                        output_message = {
                            "database": bdd,
                            "collection": collection,
                            "data": result.get("data"),
                            "id_produit": id_produit,
                            "already_in_bdd": True,
                            "updated": True,
                            "update_reason": update_reason,
                            "origin": origin,
                            "mode": mode if mode else None,
                            "chunk_ids": result.get("data", {}).get("ids", ""),
                        }
                    else:
                        # SKIP - données identiques
                        # print(f"⏭️  DÉCISION: SKIP - Produit ID {id_produit} inchangé (source {source_to_insert})")
                        result = data
                        output_message = {
                            "database": bdd,
                            "collection": collection,
                            "data": result,
                            "id_produit": id_produit,
                            "already_in_bdd": True,
                            "updated": False,
                            "origin": origin,
                        }

                # Qdrant : garder l'ancien comportement (skip)
                else:
                    # print(f"⏭️  Mode QDRANT ou record non trouvé - SKIP (pas de logique de mise à jour)")
                    result = data
                    output_message = {
                        "database": bdd,
                        "collection": collection,
                        "data": result,
                        "id_produit": id_produit,
                        "already_in_bdd": True,
                        "updated": False,
                        "origin": origin,
                    }
        else:
            # Cas où data est vide mais status success (ne devrait pas arriver)
            # print(f"⚠️  CAS ANORMAL - Status success mais data vide → Tentative d'insertion")
            # Ajouter le champ source aux produits avant insertion
            for produit in produits:
                produit["source"] = origin.upper()
            # print(f"📝 Champ 'source' ajouté aux produits: {origin.upper()}")
            result = func(produits)
            if not result or result.get("status") == "error":
                raise Exception(
                    f"L'insertion a échoué dans le cas anormal. Résultat: {result}"
                )
            else:
                id_produit_milvus = result.get("ids", "")
                # print(f"✅ Insertion réussie - ID Milvus: {id_produit_milvus}")
            data_bo_milvus.append(
                {
                    "embedding": [0.0] * 1024,
                    "id_produit": id_produit,
                    "id_produit_milvus": id_produit_milvus,
                    "date_ajout": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date_maj": "",
                    "origin": origin,
                }
            )

            output_message = {
                "database": bdd,
                "collection": collection,
                "data": result,
                "id_produit": id_produit,
                "already_in_bdd": False,
                "updated": False,
                "origin": origin,
            }

    # Insérer la correspondance si nécessaire (uniquement pour les insertions, pas les updates)
    # On vérifie également que id_produit_milvus est non vide avant d'insérer
    if len(data_bo_milvus) > 0 and bdd == "milvus":
        # print(f"📝 Préparation insertion correspondance - {len(data_bo_milvus)} entrée(s) à traiter")
        # Filtrer uniquement les entrées avec id_produit_milvus non vide
        data_bo_milvus_valid = [
            item
            for item in data_bo_milvus
            if item.get("id_produit_milvus") and item.get("id_produit_milvus") != ""
        ]

        if len(data_bo_milvus_valid) > 0:
            # print(f"✅ Insertion correspondance pour {len(data_bo_milvus_valid)} produit(s) avec ID valide")
            res_correspondance = correspondance_produit.insert_correpondance_produit(
                data_bo_milvus_valid
            )
            if not res_correspondance or res_correspondance.get("status") == "error":
                raise Exception(
                    f"L'insertion de la correspondance a échoué. Résultat: {res_correspondance}"
                )

    # print(f"🏁 FIN TRAITEMENT - Produit ID: {id_produit}")
    # print(f"═══════════════════════════════════════════════════════════")
    return output_message
