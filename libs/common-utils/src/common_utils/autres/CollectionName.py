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
    DOCUMENT = "document"


RoutingKeys = {
    CollectionName.PRODUIT: "new_data.product",
    CollectionName.DEVIS: "new_data.devis",
    CollectionName.CATEGORIE: "new_data.categories",
    CollectionName.ECHANGE: "new_data.echange",
    CollectionName.FOURNISSEUR: "new_data.fournisseurs",
    CollectionName.SITEWEB: "new_data.website",
    CollectionName.DOCUMENT: "new_data.document",
}


class CollectionNameGraph(str, Enum):
    """
    Enum for the possible collection names.
    The values correspond to the string that the API will accept.
    """

    PRODUIT = "produits"
    CATEGORIE = "categories"
    FOURNISSEUR = "fournisseurs"
    QUESTION = "questions"
    REPONSE = "reponses"
    CARACTERISTIQUE = "caracteristiques"


RoutingKeysGraph = {
    CollectionNameGraph.PRODUIT: "new_data.product",
    CollectionNameGraph.CATEGORIE: "new_data.categories",
    CollectionNameGraph.FOURNISSEUR: "new_data.fournisseurs",
    CollectionNameGraph.QUESTION: "new_data.question",
    CollectionNameGraph.REPONSE: "new_data.reponse",
    CollectionNameGraph.CARACTERISTIQUE: "new_data.caracteristique",
}
