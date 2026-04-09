import asyncio
import logging
import uvloop

from infrastructure.grpc_server import serve
from infrastructure.milvus_client import MilvusClient
from application.search_use_case import SearchUseCase
from common_utils.metrics.prometheus import start_metrics_server_in_thread

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def main():
    try:
        # --- Start Prometheus metrics server ---
        start_metrics_server_in_thread(port=8530)

        db_client = MilvusClient()
        use_case = SearchUseCase(db_client)
        await serve(use_case)
    except Exception as e:
        logging.critical(f"Le service n'a pas pu démarrer, vérifiez la connexion à Milvus. Erreur: {e}")

if __name__ == '__main__':
    uvloop.install()
    asyncio.run(main())
