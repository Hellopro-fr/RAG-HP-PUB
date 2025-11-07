import grpc
import logging
from concurrent import futures

from grpc_stubs import embedding_pb2
from grpc_stubs import embedding_pb2_grpc

from application.embedding_use_case import EmbeddingUseCase

class EmbeddingServiceImpl(embedding_pb2_grpc.EmbeddingServiceServicer):
    def __init__(self, use_case: EmbeddingUseCase):
        self.use_case = use_case

    async def GetEmbeddings(self, request, context):
        num_texts = len(request.texts)
        source_service = request.source_service or "non-spécifié"
        logging.info(f"Requête GetEmbeddings reçue de '{source_service}' pour {num_texts} textes.")
        try:
            # On passe le service source à la logique métier pour la priorisation.
            list_of_vectors = await self.use_case.generate_embeddings(
                texts=list(request.texts),
                source_service=request.source_service
            )
            
            response_embeddings = [
                embedding_pb2.EmbeddingVector(vector=vec) for vec in list_of_vectors
            ]
            
            return embedding_pb2.EmbeddingsResponse(embeddings=response_embeddings)
        except Exception as e:
            logging.error(f"Erreur dans GetEmbeddings: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la génération des embeddings.")
            return embedding_pb2.EmbeddingsResponse()

    async def Tokenize(self, request, context):
        """
        Implémentation de la méthode RPC Tokenize.
        """
        num_texts = len(request.texts)
        logging.info(f"Requête Tokenize reçue pour {num_texts} textes.")
        try:
            list_of_token_lists = self.use_case.tokenize_texts(list(request.texts))
            
            response_tokenized = [
                embedding_pb2.TokenizedOutput(tokens=tokens) for tokens in list_of_token_lists
            ]
            
            return embedding_pb2.TokenizeResponse(tokenized_texts=response_tokenized)
        except Exception as e:
            logging.error(f"Erreur dans Tokenize: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la tokenization.")
            return embedding_pb2.TokenizeResponse()
        
    async def Detokenize(self, request, context):
        """
        Implémentation de la méthode RPC Detokenize.
        """
        num_lists = len(request.tokenized_texts)
        logging.info(f"Requête Detokenize reçue pour {num_lists} listes de tokens.")
        try:
            # On reconstruit la liste de listes d'entiers
            list_of_token_lists = [list(t.tokens) for t in request.tokenized_texts]
            
            decoded_texts = self.use_case.detokenize_texts(list_of_token_lists)
            
            return embedding_pb2.DetokenizeResponse(texts=decoded_texts)
        except Exception as e:
            logging.error(f"Erreur dans Detokenize: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la détokenization.")
            return embedding_pb2.DetokenizeResponse()
        
    async def ChunkText(self, request, context):
        """
        Implémentation de la méthode RPC ChunkText.
        """
        logging.info(f"Requête ChunkText reçue.")
        try:
            chunks = self.use_case.chunk_text(
                text=request.text,
                chunk_size=request.chunk_size,
                chunk_overlap=request.chunk_overlap
            )
            return embedding_pb2.ChunkResponse(chunks=chunks)
        except Exception as e:
            logging.error(f"Erreur dans ChunkText: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors du chunking du texte.")
            return embedding_pb2.ChunkResponse()
        
async def serve(use_case: EmbeddingUseCase):
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=50))
    embedding_pb2_grpc.add_EmbeddingServiceServicer_to_server(EmbeddingServiceImpl(use_case), server)
    server.add_insecure_port('[::]:50052')
    logging.info("Serveur gRPC Embedding démarré sur le port 50052...")
    await server.start()
    await server.wait_for_termination()