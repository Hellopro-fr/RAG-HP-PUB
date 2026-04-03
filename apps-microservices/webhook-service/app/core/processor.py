import hashlib
import os
import time
from typing import Dict, Optional
from common_utils.autres.CollectionWebhook import CollectionWebhook, CollectionWebhookUpdate
from common_utils.autres.CollectionName import CollectionName as collections
import logging
import requests
import json
import hmac
from dotenv import load_dotenv

load_dotenv()

# Configuration du logging structuré
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def validate_payload(payload: any) -> bool:
    """
    Valide le format et le contenu du payload.

    Args:
        payload: Le payload à valider

    Returns:
        bool: True si valide, False sinon
    """
    # Vérifier que le payload est un dictionnaire
    if not isinstance(payload, dict):
        logger.error(f"Payload invalide : type {type(payload)} au lieu de dict")
        return False

    # Vérifier que le payload n'est pas vide
    if not payload:
        logger.error("Payload vide reçu")
        return False

    # Vérifier que la collection est présente
    if "collection" not in payload:
        logger.warning("Champ 'collection' manquant dans le payload, utilisation de la valeur par défaut")

    return True


def get_webhook_key() -> Optional[str]:
    """
    Récupère la clé webhook depuis les variables d'environnement.

    Returns:
        str: La clé webhook

    Raises:
        ValueError: Si KEY_WEBHOOK n'est pas définie
    """
    webhook_key = os.environ.get("KEY_WEBHOOK")

    if not webhook_key:
        logger.critical("KEY_WEBHOOK environment variable is not set")
        raise ValueError(
            "KEY_WEBHOOK environment variable is required. "
            "Please set it in your .env file or environment variables."
        )

    return webhook_key


def send_webhook_with_retry(
    url: str,
    payload_body: bytes,
    headers: Dict[str, str],
    max_retries: int = 3,
    timeout: int = 10
) -> bool:
    """
    Envoie un webhook avec retry logic et exponential backoff.

    Args:
        url: L'URL du webhook
        payload_body: Le corps de la requête (bytes)
        headers: Les en-têtes HTTP
        max_retries: Nombre maximum de tentatives
        timeout: Timeout en secondes

    Returns:
        bool: True si succès, False sinon
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"Tentative {attempt + 1}/{max_retries} d'envoi du webhook vers {url}")

            response = requests.post(
                url,
                data=payload_body,
                headers=headers,
                timeout=timeout
            )

            # Vérifier le statut de la réponse
            response.raise_for_status()

            logger.info(
                f"✅ Webhook envoyé avec succès à {url} "
                f"(statut: {response.status_code}, tentative: {attempt + 1})"
            )
            return True

        except requests.exceptions.Timeout as e:
            logger.warning(
                f"⏱️ Timeout lors de l'envoi du webhook (tentative {attempt + 1}/{max_retries}): {e}"
            )

        except requests.exceptions.HTTPError as e:
            logger.error(
                f"❌ Erreur HTTP lors de l'envoi du webhook "
                f"(tentative {attempt + 1}/{max_retries}, status: {e.response.status_code}): {e}"
            )

        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"🔌 Erreur de connexion lors de l'envoi du webhook "
                f"(tentative {attempt + 1}/{max_retries}): {e}"
            )

        except requests.exceptions.RequestException as e:
            logger.error(
                f"⚠️ Erreur lors de l'envoi du webhook "
                f"(tentative {attempt + 1}/{max_retries}): {e}"
            )

        # Exponential backoff si ce n'est pas la dernière tentative
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt  # 1s, 2s, 4s, 8s...
            logger.info(f"⏳ Attente de {wait_time}s avant la prochaine tentative...")
            time.sleep(wait_time)
        else:
            logger.error(
                f"❌ Échec de l'envoi du webhook après {max_retries} tentatives. "
                f"URL: {url}"
            )
            # TODO: Envoyer vers Dead Letter Queue ici

    return False


def send_webhook(payload: dict) -> bool:
    """
    Traite et envoie un webhook avec les données fournies.

    Cette fonction :
    1. Valide le payload
    2. Récupère l'URL du webhook selon la collection
    3. Calcule la signature HMAC-SHA256
    4. Envoie le webhook avec retry logic

    Args:
        payload: Dictionnaire contenant les données à envoyer

    Returns:
        bool: True si le webhook a été envoyé avec succès, False sinon
    """
    # Validation du payload
    if not validate_payload(payload):
        logger.error("Validation du payload échouée, webhook non envoyé")
        return False

    # Récupération de la collection
    collection = payload.get("collection", collections.PRODUIT)
    logger.info(f"Traitement du webhook pour la collection: {collection}")

    # Récupération de l'URL du webhook (mode update prioritaire)
    try:
        mode = payload.get("mode", "")
        if mode == "update":
            url_webhook = CollectionWebhookUpdate.get(collection, "")
            if url_webhook:
                logger.info(f"Mode 'update' détecté → utilisation de l'URL update pour '{collection}'")
            else:
                logger.warning(f"Aucune URL update configurée pour '{collection}', fallback sur l'URL standard")
                url_webhook = CollectionWebhook.get(collection)
        else:
            url_webhook = CollectionWebhook.get(collection)

        if not url_webhook:
            logger.error(f"Aucune URL de webhook configurée pour la collection '{collection}'")
            return False

    except (KeyError, AttributeError) as e:
        logger.error(f"Erreur lors de la récupération de l'URL du webhook pour '{collection}': {e}")
        return False

    try:
        # Récupération de la clé webhook (avec validation)
        webhook_key = get_webhook_key()

        # Conversion du payload en JSON compact
        payload_body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        logger.debug(f"Taille du payload: {len(payload_body)} bytes")

        # Calcul de la signature HMAC-SHA256
        signature = hmac.new(
            webhook_key.encode('utf-8'),
            payload_body,
            hashlib.sha256
        ).hexdigest()

        # Préparation des en-têtes
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature
        }

        # Envoi du webhook avec retry logic
        success = send_webhook_with_retry(
            url=url_webhook,
            payload_body=payload_body,
            headers=headers,
            max_retries=3,
            timeout=10
        )

        return success

    except ValueError as e:
        # Erreur de validation (ex: KEY_WEBHOOK manquante)
        logger.critical(f"Erreur de configuration: {e}")
        return False

    except Exception as e:
        # Erreur inattendue
        logger.exception(f"Erreur inattendue lors de l'envoi du webhook: {e}")
        return False
