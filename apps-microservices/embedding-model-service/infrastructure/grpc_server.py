import grpc
import logging
from concurrent import futures

import embedding_pb2
import embedding_pb2_grpc

from application.embedding_use_case import EmbeddingUseCase

class EmbeddingServiceImpl(embedding_pb2_grpc.EmbeddingServiceServicer):
    def __init__(self, use_case: EmbeddingUseCase):
        self.use_case = use_case

    async def GetEmbeddings(self, request, context):
        num_texts = len(request.texts)
        logging.info(f"Requête GetEmbeddings reçue pour {num_texts} textes.")
        try:
            # MODIFIÉ: Ajout du mot-clé 'await' car generate_embeddings est maintenant une coroutine.
            list_of_vectors = await self.use_case.generate_embeddings(list(request.texts))
            
            response_embeddings = [
                embedding_pb2.EmbeddingVector(vector=vec) for vec in list_of_vectors
            ]
            
            return embedding_pb2.EmbeddingsResponse(embeddings=response_embeddings)
        except Exception as e:
            logging.error(f"Erreur dans GetEmbeddings: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la génération des embeddings.")
            return embedding_pb2.EmbeddingsResponse()

async def serve(use_case: EmbeddingUseCase):
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=50))
    embedding_pb2_grpc.add_EmbeddingServiceServicer_to_server(EmbeddingServiceImpl(use_case), server)
    server.add_insecure_port('[::]:50052')
    logging.info("Serveur gRPC Embedding démarré sur le port 50052...")
    await server.start()
    await server.wait_for_termination()