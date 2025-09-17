# Dictionnaire centralisé pour toutes les opérations CRUD
MILVUS_COLLECTIONS = {
    "produits": "produits_3",
    "fournisseurs": "fournisseurs",
    "devis": "devis",
    "websites": "websites",
    "categories": "categories",
    "echanges": "echanges"
}

MILVUS_COLLECTIONS_DEFAULT_FIELDS = {
    "produits": [
        "id",
        "id_produit",
        "nom_produit",
        "id_fournisseur",
        "fournisseur",
        "id_categorie",
        "categorie",
        "chunk_id"
    ],
    "fournisseurs": [],
    "devis"       : [],
    "websites"    : [],
    "categories"  : [],
    "echanges"    : [],
}
