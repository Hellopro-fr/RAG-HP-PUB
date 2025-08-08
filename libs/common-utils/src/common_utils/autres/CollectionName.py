from enum import Enum

class CollectionName(str, Enum):
    """
    Enum for the possible collection names.
    The values correspond to the string that the API will accept.
    """
    PRODUIT = "produits"
    DEVIS = "devis"
    CATEGORIE = "categories"
    ECHANGE = "echanges"
    FOURNISSEUR = "fournisseurs"