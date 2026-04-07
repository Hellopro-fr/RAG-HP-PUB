import hashlib
import os
import asyncio
from typing import Dict, List, Optional
from common_utils.autres.CollectionWebhook import CollectionWebhook, CollectionWebhookUpdate
from common_utils.autres.CollectionName import CollectionName as collections
import logging
import json
import hmac
import aiohttp

logger = logging.getLogger(__name__)

# Configuration du batching
BATCH_SIZE = int(os.environ.get("WEBHOOK_BATCH_SIZE", "50"))
BATCH_TIMEOUT_S = float(os.environ.get("WEBHOOK_BATCH_TIMEOUT_S", "5.0"))


def get_webhook_key() -> str:
    webhook_key = os.environ.get("KEY_WEBHOOK")
    if not webhook_key:
        logger.critical("KEY_WEBHOOK environment variable is not set")
        raise ValueError("KEY_WEBHOOK environment variable is required.")
    return webhook_key


def resolve_webhook_url(payload: dict) -> Optional[str]:
    """Résout l'URL du webhook selon la collection et le mode."""
    collection = payload.get("collection", collections.PRODUIT)
    mode = payload.get("mode", "")

    if mode == "update":
        url = CollectionWebhookUpdate.get(collection, "")
        if url:
            return url
        logger.warning(f"Aucune URL update pour '{collection}', fallback sur l'URL standard")

    url = CollectionWebhook.get(collection)
    if not url:
        logger.error(f"Aucune URL de webhook configurée pour '{collection}'")
    return url


def sign_payload(payload_body: bytes, webhook_key: str) -> str:
    """Calcule la signature HMAC-SHA256."""
    return hmac.new(
        webhook_key.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()


def build_batch_payload(payloads: List[dict]) -> dict:
    """
    Construit un payload batch à partir d'une liste de payloads individuels.
    """
    if not payloads:
        return {"batch": True, "mode": "update", "collection": "", "count": 0, "products": []}

    products = []
    for p in payloads:
        products.append({
            "id_produit": p.get("id_produit"),
            "chunk_ids": p.get("chunk_ids", ""),
            "origin": p.get("origin", ""),
            "update_reason": p.get("update_reason", ""),
        })

    return {
        "batch": True,
        "mode": "update",
        "collection": payloads[0].get("collection", ""),
        "count": len(products),
        "products": products,
    }


class WebhookSender:
    """Envoi de webhooks avec session HTTP réutilisable (connection pooling)."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        self._webhook_key = get_webhook_key()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Retourne une session HTTP, en la créant si nécessaire (thread-safe)."""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(
                    limit=20,
                    keepalive_timeout=30,
                )
                self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self):
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

    async def send_single(self, payload: dict, max_retries: int = 3, timeout: int = 10) -> bool:
        """Envoie un seul payload webhook."""
        url = resolve_webhook_url(payload)
        if not url:
            return False

        payload_body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        signature = sign_payload(payload_body, self._webhook_key)
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature,
        }

        return await self._post_with_retry(url, payload_body, headers, max_retries, timeout)

    async def send_batch(
        self,
        payloads: List[dict],
        url: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 15,
    ) -> bool:
        """
        Envoie un batch de payloads en un seul appel HTTP.
        Si url est fourni, l'utilise directement (déjà résolu par le consumer).
        """
        if not payloads:
            return True

        if len(payloads) == 1:
            return await self.send_single(payloads[0], max_retries, timeout)

        if not url:
            url = resolve_webhook_url(payloads[0])
        if not url:
            return False

        batch_payload = build_batch_payload(payloads)
        payload_body = json.dumps(batch_payload, separators=(',', ':')).encode('utf-8')
        signature = sign_payload(payload_body, self._webhook_key)
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature,
        }

        logger.info(f"Envoi batch de {len(payloads)} produits vers {url}")
        return await self._post_with_retry(url, payload_body, headers, max_retries, timeout)

    async def _post_with_retry(
        self, url: str, payload_body: bytes, headers: Dict[str, str],
        max_retries: int, timeout: int
    ) -> bool:
        session = await self._get_session()
        client_timeout = aiohttp.ClientTimeout(total=timeout)

        for attempt in range(max_retries):
            try:
                logger.info(f"Tentative {attempt + 1}/{max_retries} d'envoi vers {url}")
                async with session.post(url, data=payload_body, headers=headers, timeout=client_timeout) as resp:
                    if resp.status < 400:
                        logger.info(f"✅ Webhook envoyé (status: {resp.status}, tentative: {attempt + 1})")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"❌ HTTP {resp.status} (tentative {attempt + 1}/{max_retries}): {body[:200]}")

            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout (tentative {attempt + 1}/{max_retries})")
            except aiohttp.ClientError as e:
                logger.error(f"🔌 Erreur connexion (tentative {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"⏳ Attente de {wait_time}s avant la prochaine tentative...")
                await asyncio.sleep(wait_time)

        logger.error(f"❌ Échec après {max_retries} tentatives. URL: {url}")
        return False
