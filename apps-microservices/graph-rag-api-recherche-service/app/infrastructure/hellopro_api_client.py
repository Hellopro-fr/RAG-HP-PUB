"""
HelloPro API client for fetching product info and characteristics.
Uses httpx for async HTTP requests.
"""

import os
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# TTL cache: 2 hours in seconds
CACHE_TTL = 2 * 60 * 60

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
        # In-memory TTL caches: key -> (timestamp, value)
        self._prompt_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._carac_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    def _get_cached(self, cache: dict, key: str):
        """Return cached value if present and not expired, else None."""
        entry = cache.get(key)
        if entry is not None:
            ts, value = entry
            if time.monotonic() - ts < CACHE_TTL:
                return value
            del cache[key]
        return None

    def _set_cached(self, cache: dict, key: str, value):
        """Store value in cache with current timestamp."""
        cache[key] = (time.monotonic(), value)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        token = settings.HELLOPRO_API_BEARER_TOKEN
        if not token:
            token = os.environ.get("HELLOPRO_API_BEARER_TOKEN", "")

        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning("HELLOPRO_API_BEARER_TOKEN is not set, requests may fail")
        return headers

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

        Returns list of characteristic dicts. Cached with 2h TTL.
        """
        cache_key = str(id_produit)
        cached = self._get_cached(self._carac_cache, cache_key)
        if cached is not None:
            return cached

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
                result = data.get("response", [])
                self._set_cached(self._carac_cache, cache_key, result)
                return result
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

        return {id_produit: caracs for id_produit, caracs in zip(id_produits, results)}

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

    async def fetch_prompt(
        self, id_prompt: str
    ) -> Dict[str, Any]:
        """
        Fetch a prompt content and temperature from HelloPro API.
        POST https://api.hellopro.fr/api/v2/index.php

        Returns dict with 'contenu_prompt' and 'temperature', or empty dict on error.
        Cached with 2h TTL.
        """
        cache_key = str(id_prompt)
        cached = self._get_cached(self._prompt_cache, cache_key)
        if cached is not None:
            logger.info("[CACHE] Prompt id_prompt=%s served from cache", cache_key)
            return cached

        payload = {
            "etape": "prompt",
            "field": "info",
            "action": "get",
            "data": {
                "id_prompt": str(id_prompt),
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
                # Response format: { "code": 200, "response": { "id_prompt": "...", "contenu_prompt": "...", "temperature": "..." } }
                result = data.get("response", {})
                if result:
                    self._set_cached(self._prompt_cache, cache_key, result)
                return result
        except Exception as e:
            logger.error(
                f"HelloPro fetch_prompt error for id_prompt {id_prompt}: {e}",
                exc_info=True,
            )
            return {}


# Singleton instance
hellopro_api_client = HelloProApiClient()
