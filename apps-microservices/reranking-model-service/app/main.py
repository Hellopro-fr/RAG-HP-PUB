import asyncio
import logging
import uvloop

from infrastructure.grpc_server import serve
from application.reranking_use_case import RerankingUseCase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def main():
    use_case = RerankingUseCase()
    await serve(use_case)

if __name__ == '__main__':
    uvloop.install()
    asyncio.run(main())
