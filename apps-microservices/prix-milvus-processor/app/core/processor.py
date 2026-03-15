from common_utils.database.MilvusPrixProduitsCrud import MilvusPrixProduitsCrud
from common_utils.autres.CollectionName import CollectionName
import logging


def insertion_data(produits_data: dict) -> dict:
    """
    Prend les résultats de l'embedding puis insère les chunks dans la collection Milvus prix.

    Logique d'insertion :
    - Insertion simple (insert-only) des données de prix dans la collection prix.
    - Pas de logique de déduplication pour le moment.

    Retourne: Un dictionnaire prêt à être publié.
    """
    produits = produits_data.get("data", [])
    collection = produits_data.get("collection", CollectionName.PRIX)
    origin = produits_data.get("origin", "extraction")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        raise ValueError(f"'{collection}' n'est pas un nom de collection valide.")

    if collection_enum != CollectionName.PRIX:
        raise ValueError(
            f"Collection '{collection}' non supportée par le prix-milvus-processor. Seule 'prix' est acceptée."
        )

    base_vectorielle = MilvusPrixProduitsCrud()

    if not produits or len(produits) <= 0:
        raise ValueError("Aucune donnée de prix fournie.")

    id_produit = produits[0].get("id_produit", "ID produit inconnu")
    logging.info(
        f"[PrixProcessor] Produit ID: {id_produit} | Nombre de chunks: {len(produits)}"
    )

    # Ajouter le champ source aux produits avant insertion
    for produit in produits:
        if "source" not in produit or not produit["source"]:
            produit["source"] = origin.upper()

    # Insertion simple
    result = base_vectorielle.insert_prix_produits(produits)

    if not result or result.get("status") != "success":
        error_msg = (
            f"L'insertion a échoué pour id_produit={id_produit}. Résultat: {result}"
        )
        logging.error(f"[PrixProcessor] {error_msg}")
        raise Exception(error_msg)
    else:
        id_produit_milvus = result.get("ids", "")
        logging.info(
            f"[PrixProcessor] ✓ Insertion réussie - ID Milvus: {id_produit_milvus}"
        )

    output_message = {
        "database": "milvus",
        "collection": collection,
        "data": result,
        "id_produit": id_produit,
        "already_in_bdd": False,
        "updated": False,
        "origin": origin,
    }

    logging.info(f"[PrixProcessor] 🏁 FIN TRAITEMENT - Produit ID: {id_produit}")
    return output_message
