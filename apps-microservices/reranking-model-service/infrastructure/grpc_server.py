import grpc
import logging
from concurrent import futures

import reranking_pb2
import reranking_pb2_grpc

from application.reranking_use_case import RerankingUseCase

class RerankingServiceImpl(reranking_pb2_grpc.RerankingServiceServicer):
    def __init__(self, use_case: RerankingUseCase):
        self.use_case = use_case

    async def Rerank(self, request, context):
        logging.info(f"Requête Rerank reçue pour la query: '{request.query[:50]}...' avec {len(request.documents)} documents.")
        try:
            # MODIFIÉ: Ajout du mot-clé 'await' car rerank_documents est maintenant une coroutine.
            ranked_docs = await self.use_case.rerank_documents(request.query, list(request.documents))
            return reranking_pb2.RerankResponse(ranked_documents=ranked_docs)
        except Exception as e:
            logging.error(f"Erreur dans Rerank: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors du reranking.")
            return reranking_pb2.RerankResponse()

async def serve(use_case: RerankingUseCase):
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=50))
    reranking_pb2_grpc.add_RerankingServiceServicer_to_server(RerankingServiceImpl(use_case), server)
    server.add_insecure_port('[::]:50053')
    logging.info("Serveur gRPC Reranking démarré sur le port 50053...")
    await server.start()
    await server.wait_for_termination()