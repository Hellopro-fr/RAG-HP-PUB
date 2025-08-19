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
    SITEWEB = "siteweb"
    
RoutingKeys = {
    CollectionName.PRODUIT: "new_data.product",
    CollectionName.DEVIS: "new_data.devis",
    CollectionName.CATEGORIE: "new_data.category",
    CollectionName.ECHANGE: "new_data.echange",
    CollectionName.FOURNISSEUR: "new_data.supplier",
    CollectionName.SITEWEB: "new_data.website"
}