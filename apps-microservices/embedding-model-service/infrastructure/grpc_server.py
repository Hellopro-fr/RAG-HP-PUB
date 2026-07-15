import grpc
import logging
import asyncio
import functools
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
            # Offload : chunk_text est CPU-lourd (tokenizer par split) et bloquerait
            # l'event loop du serveur, gelant toutes les RPC concurrentes. On l'exécute
            # dans le thread pool par défaut (spec 2026-07-03).
            loop = asyncio.get_running_loop()
            chunks = await loop.run_in_executor(
                None,
                functools.partial(
                    self.use_case.chunk_text,
                    request.text,
                    request.chunk_size,
                    request.chunk_overlap,
                ),
            )
            return embedding_pb2.ChunkResponse(chunks=chunks)
        except Exception as e:
            logging.error(f"Erreur dans ChunkText: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors du chunking du texte.")
            return embedding_pb2.ChunkResponse()
        
# 64 Mo : symétrie avec le canal client common-utils — une requête
# ChunkText/GetEmbeddings dont le texte dépasse ~4 Mo serait sinon refusée
# côté serveur par le défaut gRPC de réception (4 Mio). L'envoi est illimité
# par défaut, seul le plafond de réception doit être relevé.
#
# Keepalive : le client (common_utils.grpc_clients.embedding_client) envoie un
# PING toutes les 30s (keepalive_time_ms=30000, keepalive_permit_without_calls=1).
# Par défaut le serveur gRPC n'accepte pas de PING plus fréquent que 300s sans
# frame DATA et coupe la connexion (GOAWAY ENHANCE_YOUR_CALM "too_many_pings")
# au bout de 2 strikes. Pendant un GetEmbeddings long (gros batch, aucune frame
# DATA renvoyée), les PING de liveness du client déclenchaient donc UNAVAILABLE
# ~4 min après le début de l'appel -> retry transitoire en boucle. On aligne le
# serveur sur la cadence du client. min_ping_interval doit rester <= keepalive_time
# client (30000ms). max_ping_strikes=0 = accepter n'importe quel nombre de pings.
_SERVER_OPTIONS = [
    ("grpc.max_receive_message_length", 64 * 1024 * 1024),
    ("grpc.keepalive_permit_without_calls", 1),
    ("grpc.http2.min_ping_interval_without_data_ms", 10000),
    ("grpc.http2.max_ping_strikes", 0),
]


async def serve(use_case: EmbeddingUseCase):
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=50), options=_SERVER_OPTIONS
    )
    embedding_pb2_grpc.add_EmbeddingServiceServicer_to_server(EmbeddingServiceImpl(use_case), server)
    server.add_insecure_port('[::]:50052')
    logging.info("Serveur gRPC Embedding démarré sur le port 50052...")
    await server.start()
    await server.wait_for_termination()