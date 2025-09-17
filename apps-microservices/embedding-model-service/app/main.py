import asyncio
import logging
import uvloop

from infrastructure.grpc_server import serve
from application.embedding_use_case import EmbeddingUseCase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def main():
    # L'initialisation est beaucoup plus simple.
    # Plus de chargement de modèle lourd, juste le tokenizer.
    use_case = EmbeddingUseCase()
    await serve(use_case)

if __name__ == '__main__':
    uvloop.install()
    asyncio.run(main())
