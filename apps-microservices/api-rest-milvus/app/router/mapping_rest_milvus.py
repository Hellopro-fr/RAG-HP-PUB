# common_utils/database/milvus_router_registry.py

from common_utils.database import (
    MilvusProduitCrud,
    MilvusFournisseursCrud,
    MilvusDevisCrud,
    MilvusWebsiteCrud,
    MilvusCategoriesCrud,
    MilvusEchangeCrud
)

# Dictionnaire centralisé pour toutes les opérations CRUD
MILVUS_CRUD_REGISTRY = {
    "produits": MilvusProduitCrud.MilvusProduitsCrud,
    "fournisseurs": MilvusFournisseursCrud.MilvusFournisseursCrud,
    "devis": MilvusDevisCrud.MilvusDevisCrud,
    "websites": MilvusWebsiteCrud.MilvusWebsiteCrud,
    "categories": MilvusCategoriesCrud.MilvusCategoriesCrud,
    "echanges": MilvusEchangeCrud.MilvusEchangeCrud
}
