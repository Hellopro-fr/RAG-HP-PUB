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
    ZILLIZ_URI: str
    ZILLIZ_PORT: str
    ZILLIZ_API_KEY: str
    OPENROUTER_API_KEY: str

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

model_settings = {
    "openai": [
        "gpt-4.1-2025-04-14",
        "gpt-4o-2024-08-06",
        "gpt-4o-2024-11-20",
        "deepseek"
    ],
    "or": [
        "qwen/qwen3-coder:free", 
        "qwen/qwen3-coder", 
        "google/gemini-flash-1.5"
    ]
}

settings = Settings()
