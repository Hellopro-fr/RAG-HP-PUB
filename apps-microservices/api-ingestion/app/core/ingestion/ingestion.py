from enum import Enum

class CollectionName(str, Enum):
    """
    Enum for the possible collection names.
    The values correspond to the string that the API will accept.
    """
    PRODUIT = "produit"
    DEVIS = "devis"
    CATEGORIE = "categorie"
    ECHANGE = "echange"
    FOURNISSEUR = "fournisseur"

def routing_key_collection(collection: CollectionName):
    collections = {
        CollectionName.PRODUIT: "new_data.product",
        CollectionName.DEVIS: "new_data.devis",
        CollectionName.CATEGORIE: "new_data.category",
        CollectionName.ECHANGE: "new_data.echange",
        CollectionName.FOURNISSEUR: "new_data.supplier"
    }
    # Use .get() to provide a default value if the key is not found
    return collections.get(collection, "")


