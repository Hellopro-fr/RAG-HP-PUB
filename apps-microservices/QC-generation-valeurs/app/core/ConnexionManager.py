# app/router/ConnexionManager.py

import logging
from typing import List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnexionManager:
    """
    Gère les connexions WebSocket actives.
    Chaque client est un "channel" unique.
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accepte une nouvelle connexion et l'ajoute à la liste."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Nouvelle connexion acceptée: {websocket.client}. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Retire une connexion de la liste."""
        self.active_connections.remove(websocket)
        logger.info(f"Client déconnecté: {websocket.client}. Total: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Envoie un message JSON à un client spécifique."""
        await websocket.send_json(message)

# Crée une instance unique du gestionnaire qui sera partagée
manager = ConnexionManager()