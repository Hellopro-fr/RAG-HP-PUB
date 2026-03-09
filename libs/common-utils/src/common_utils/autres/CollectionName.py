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
    PRIX_PRODUIT = "prix_produits"


RoutingKeys = {
    CollectionName.PRODUIT: "new_data.product",
    CollectionName.DEVIS: "new_data.devis",
    CollectionName.CATEGORIE: "new_data.categories",
    CollectionName.ECHANGE: "new_data.echange",
    CollectionName.FOURNISSEUR: "new_data.fournisseurs",
    CollectionName.SITEWEB: "new_data.website",
    CollectionName.DOCUMENT: "new_data.document",
    CollectionName.PRIX_PRODUIT: "new_data.prix_produit",
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
    CollectionNameGraph.PRODUIT: "graph-new_data.product",
    CollectionNameGraph.CATEGORIE: "graph-new_data.categories",
    CollectionNameGraph.FOURNISSEUR: "graph-new_data.fournisseurs",
    CollectionNameGraph.QUESTION: "graph-new_data.question",
    CollectionNameGraph.REPONSE: "graph-new_data.reponse",
    CollectionNameGraph.CARACTERISTIQUE: "graph-new_data.caracteristique",
}
