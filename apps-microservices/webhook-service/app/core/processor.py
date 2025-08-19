import hashlib
import os
from common_utils.autres.CollectionWebhook import CollectionWebhook
from common_utils.autres.CollectionName import CollectionName as collections
import logging
import requests
import json
import hmac
from dotenv import load_dotenv
load_dotenv()


def send_webhook(payload: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    payload.pop("data")
    collection = payload.get("collection", collections.PRODUIT)

    try:
        url_webhook = CollectionWebhook.get(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return ""

    try:
        # 1. Convertir le payload en une chaîne JSON compacte (sans espaces)
        payload_body = json.dumps(payload, separators=(',', ':')).encode('utf-8')

        # 2. Calculer la signature HMAC-SHA256
        signature = hmac.new(os.environ.get("KEY_WEBHOOK").encode('utf-8'), payload_body, hashlib.sha256).hexdigest()

        # 3. Préparer les en-têtes avec la signature
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature  # Le nom de l'en-tête peut varier
        }

        # 4. Envoyer la requête avec le corps brut (bytes) et les en-têtes
        response = requests.post(url_webhook, data=payload_body, headers=headers, timeout=10)
        
        response.raise_for_status()
        print(f"Webhook envoyé avec succès")
        print(f"Statut : {response.status_code}")
        print(f"URL notifié : {url_webhook}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"ERREUR : L'envoi du webhook a échoué : {e}")
        return False