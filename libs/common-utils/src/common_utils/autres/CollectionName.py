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