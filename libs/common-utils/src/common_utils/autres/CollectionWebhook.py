from enum import Enum

# TODO:
# modification url à notifier / à confirmer si à mettre dans .env
class CollectionName(str, Enum):
    """
    Enum for the possible collection names.
    The values correspond to the string that the API will accept.
    """
    PRODUIT = "https://webhook.site/2d6200d4-bd42-4b96-8cd7-396ecbcb1f20"
    DEVIS = "https://webhook.site/2d6200d4-bd42-4b96-8cd7-396ecbcb1f20"
    CATEGORIE = "https://webhook.site/2d6200d4-bd42-4b96-8cd7-396ecbcb1f20"
    ECHANGE = "https://webhook.site/2d6200d4-bd42-4b96-8cd7-396ecbcb1f20"
    FOURNISSEUR = "https://webhook.site/2d6200d4-bd42-4b96-8cd7-396ecbcb1f20"