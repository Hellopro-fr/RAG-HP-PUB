# Dictionnaire centralisé pour toutes les opérations CRUD
MILVUS_COLLECTIONS = {
    "produits": "produits",
    "fournisseurs": "fournisseurs",
    "devis": "devis",
    "siteweb": "siteweb",
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
    "fournisseurs": [

    ],
    "devis"       : [
        "id",
        "lead_id",
        "message",
        "id_categorie",
        "societe_acheteur",
        "date_du_lead",
        "liste_frns"
    ],
    "siteweb"    : [
        "id",
        "url",
        "page_type",
        "domaine",
        "text",
        "source",
        "chunk_id",
        "total_chunks"
    ],
    "categories"  : [
        "id",
        "id_categorie",
        "categorie",
        "text"
    ],
    "echanges"    : [
        "id",
        "conversation_id",
        "text"
    ],
}

MILVUS_COLLECTIONS_UNIQUE_FIELD  = {
    "produits": "id_produit",
    "devis": "lead_id",
    "categories": "id_categorie",
    "echanges": "conversation_id"
}
