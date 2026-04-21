"""
Client Typesense (singleton) + helpers de collection + healthcheck.
"""
import logging
from typing import Dict, Any, Optional

import requests
import typesense

from app.core.credentials import settings

logger = logging.getLogger(__name__)


class TypesenseClient:
    """Singleton wrapper autour du typesense-python client."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = None
        return cls._instance

    @property
    def client(self) -> typesense.Client:
        if self._client is None:
            self._client = typesense.Client({
                "api_key": settings.TYPESENSE_API_KEY,
                "nodes": [{
                    "host": settings.TYPESENSE_HOST,
                    "port": settings.TYPESENSE_PORT,
                    "protocol": settings.TYPESENSE_PROTOCOL,
                }],
                "connection_timeout_seconds": settings.TYPESENSE_CONNECTION_TIMEOUT,
            })
            logger.info(
                "Typesense client initialise -> %s://%s:%s",
                settings.TYPESENSE_PROTOCOL, settings.TYPESENSE_HOST, settings.TYPESENSE_PORT,
            )
        return self._client

    def base_url(self) -> str:
        return f"{settings.TYPESENSE_PROTOCOL}://{settings.TYPESENSE_HOST}:{settings.TYPESENSE_PORT}"

    def healthcheck(self) -> Dict[str, Any]:
        r = requests.get(f"{self.base_url()}/health", timeout=5)
        r.raise_for_status()
        return r.json()

    def collection_exists(self, name: str) -> bool:
        try:
            self.client.collections[name].retrieve()
            return True
        except Exception:
            return False

    def collection_stats(self, name: str) -> Dict[str, Any]:
        return self.client.collections[name].retrieve()

    def multi_search(self, search_body: Dict[str, Any]) -> Dict[str, Any]:
        """Wrap multi_search.perform (utilise pour vecteurs car POST body)."""
        return self.client.multi_search.perform(search_body, {})

    def default_schema(self, collection_name: str) -> Dict[str, Any]:
        """Schema standard opti-moteur-front (1024 dims CamemBERT)."""
        return {
            "name": collection_name,
            "fields": [
                {"name": "id_produit",      "type": "string", "facet": True},
                {"name": "nom_produit",     "type": "string"},
                {"name": "text",            "type": "string"},
                {"name": "categorie",       "type": "string", "facet": True, "optional": True},
                {"name": "id_categorie",    "type": "string", "facet": True, "optional": True},
                {"name": "fournisseur",     "type": "string", "facet": True, "optional": True},
                {"name": "id_fournisseur",  "type": "string", "facet": True, "optional": True},
                {"name": "marque",          "type": "string", "facet": True, "optional": True},
                {"name": "fabricant",       "type": "string", "optional": True},
                {"name": "etat",            "type": "string", "facet": True, "optional": True},
                {"name": "affichage",       "type": "string", "facet": True, "optional": True},
                {"name": "statut",          "type": "string", "facet": True, "optional": True},
                {"name": "prix_ht",         "type": "float",  "optional": True},
                {"name": "prix_ttc",        "type": "float",  "optional": True},
                {"name": "stock",           "type": "string", "optional": True},
                {"name": "delai_livraison", "type": "string", "optional": True},
                {"name": "ean",             "type": "string", "optional": True},
                {"name": "sku",             "type": "string", "optional": True},
                {"name": "reference",       "type": "string", "optional": True},
                {"name": "date_ajout",      "type": "string", "optional": True, "sort": True},
                {"name": "date_maj",        "type": "string", "optional": True, "sort": True},
                {"name": "chunk_number",    "type": "int32"},
                {"name": "total_chunks",    "type": "int32"},
                {"name": "embedding",       "type": "float[]", "num_dim": settings.EMBEDDING_DIMENSION},
            ],
            "token_separators": ["-", "/"],
        }

    def create_collection_if_missing(self, name: Optional[str] = None) -> Dict[str, Any]:
        name = name or settings.TYPESENSE_COLLECTION
        if self.collection_exists(name):
            logger.info("Collection '%s' existe deja", name)
            return self.collection_stats(name)
        schema = self.default_schema(name)
        self.client.collections.create(schema)
        logger.info("Collection '%s' creee (num_dim=%s)", name, settings.EMBEDDING_DIMENSION)
        return self.collection_stats(name)


# Singleton
typesense_client = TypesenseClient()
