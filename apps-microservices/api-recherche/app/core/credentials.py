import os
from pydantic_settings import BaseSettings
from typing import Dict, List

class Settings(BaseSettings):
    PROJECT_NAME: str = "API-HP-RAG"
    PROJECT_VERSION: str = "0.0.1"

    QDRANT_URL: str
    QDRANT_PORT: str
    QDRANT_API_KEY: str
    OPENAI_API_KEY: str
    DEEPSEEK_API_KEY: str
    MILVUS_URI: str
    MILVUS_PORT: str
    MILVUS_TOKEN: str

    MILVUS_OUTPUT_FIELDS_CONFIG: Dict[str, List[str]] = {
        "devis_poc": [
            "chunk_id", "lead_id", "message", "message_hellopro", "categorie", "id_categorie", "effectif",
            "prof_ou_part", "naf2", "naf5", "departement", "region", "pays", "critere", "societe_acheteur",
            "siren", "siret", "date_du_lead", "liste_frns", "nb_mec", "appreciation_lead", "source", "page_type",
            "id_produit", "text"
        ],
        "siteweb_poc": [
            "chunk_id", "source", "url", "page_type", "domaine", "id_categorie", "categorie", "vf_id_categorie",
            "vf_nom_categorie", "id_fournisseur", "fournisseur", "etat", "affichage", "text"
        ],
        "echanges_poc": [
            "chunk_id", "id_demande", "produit", "id_produit", "categorie", "id_categorie", "fournisseur",
            "id_fournisseur", "etat", "affichage", "acheteur", "id_acheteur", "text", "conversation_id"
        ]
    }

    class Config:
        env_file = ".env"

settings = Settings()
