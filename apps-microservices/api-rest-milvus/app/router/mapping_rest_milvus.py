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

# Mapping des collections principales vers leurs collections de correspondance
# Utilisé pour la suppression en cascade
MILVUS_COLLECTIONS_CASCADE_MAPPING = {
    "produits": "correspondance_produits_bo_milvus",
    "produits_2": "correspondance_produits_bo_milvus_2",
    "produits_3": "correspondance_produits_bo_milvus_3",
    "devis": "correspondance_devis_bo_milvus",
    "categories": "correspondance_categories_bo_milvus",
    "echanges": "correspondance_echanges_bo_milvus"
}
