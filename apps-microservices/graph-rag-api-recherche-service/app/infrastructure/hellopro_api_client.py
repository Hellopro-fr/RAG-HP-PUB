"""
HelloPro API client for fetching product info and characteristics.
Uses httpx for async HTTP requests.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# API endpoints
HELLOPRO_VIEW_URL = "https://api.hellopro.fr/api/hp/view/index.php"
HELLOPRO_CARAC_URL = "https://api.hellopro.fr/api/v2/index.php"

# Etat societe mapping
ETAT_SOCIETE_MAP = {
    "1": "Client",
    "2": "Pause",
    "3": "Prospects",
}


class HelloProApiClient:
    """Async client for HelloPro external APIs."""

    def __init__(self):
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.HELLOPRO_API_BEARER_TOKEN}",
            "Content-Type": "application/json",
        }

    async def fetch_products_info(
        self, id_categorie: str, id_produits: List[str]
    ) -> Dict[str, Any]:
        """
        Fetch product info from HelloPro API.
        POST https://api.hellopro.fr/api/hp/view/index.php

        Returns dict of product info keyed by id_produit.
        """
        if not id_produits:
            return {}

        payload = {
            "etape": "get_info_produit",
            "scrapping": 1,
            "action": "get",
            "data": {
                "id_categorie": id_categorie,
                "id_produits": id_produits,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    HELLOPRO_VIEW_URL,
                    json=payload,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                # Response format: { "items": { "id_produit": { ... }, ... } }
                return data.get("items", {})
        except Exception as e:
            logger.error(f"HelloPro fetch_products_info error: {e}", exc_info=True)
            return {}

    async def fetch_product_caracteristiques(
        self, id_produit: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch characteristics for a single product.
        POST https://api.hellopro.fr/api/v2/index.php

        Returns list of characteristic dicts.
        """
        payload = {
            "etape": "caracterisation",
            "field": "produit",
            "action": "get",
            "data": {
                "id_produit": str(id_produit),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    HELLOPRO_CARAC_URL,
                    json=payload,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                # Response format: { "code": 200, "response": [ ... ] }
                return data.get("response", [])
        except Exception as e:
            logger.error(
                f"HelloPro fetch_product_caracteristiques error for {id_produit}: {e}",
                exc_info=True,
            )
            return []

    async def fetch_all_product_caracteristiques(
        self, id_produits: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch characteristics for multiple products in parallel.
        Returns dict keyed by id_produit -> list of characteristics.
        """
        if not id_produits:
            return {}

        tasks = [
            self.fetch_product_caracteristiques(id_produit)
            for id_produit in id_produits
        ]
        results = await asyncio.gather(*tasks)

        return {
            id_produit: caracs
            for id_produit, caracs in zip(id_produits, results)
        }
    async def fetch_category_caracteristiques(
        self, id_categorie: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch characteristic definitions for a category.
        POST https://api.hellopro.fr/api/v2/index.php

        Returns list of characteristic definition dicts with id, nom, description,
        unite, type, and valeurs.
        """
        payload = {
            "etape": "caracteristique",
            "field": "final",
            "action": "get",
            "data": {
                "id_categorie": str(id_categorie),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    HELLOPRO_CARAC_URL,
                    json=payload,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                # Response format: { "code": 200, "response": [ { "id_caracteristique": ..., "nom": ..., ... } ] }
                return data.get("response", [])
        except Exception as e:
            logger.error(
                f"HelloPro fetch_category_caracteristiques error for category {id_categorie}: {e}",
                exc_info=True,
            )
            return []


# Singleton instance
hellopro_api_client = HelloProApiClient()
