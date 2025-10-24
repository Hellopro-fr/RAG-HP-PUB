import asyncio
import logging
import uvloop

from infrastructure.grpc_server import serve
from application.chat_service import ChatApplicationService

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def main():
    """
    Point d'entrée principal: initialise les dépendances et démarre le serveur.
    C'est ici que l'injection de dépendances a lieu.
    """
    # 1. Initialisation de la couche d'infrastructure
    # The LLM client is now initialized within ChatApplicationService

    # 2. Initialisation de la couche application avec ses dépendances
    chat_service = ChatApplicationService()

    # 3. Démarrage du serveur gRPC
    await serve(chat_service)

if __name__ == '__main__':
    # uvloop est un remplacement plus rapide de la boucle d'événements par défaut d'asyncio
    uvloop.install()
    asyncio.run(main())
