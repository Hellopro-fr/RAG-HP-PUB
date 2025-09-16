import grpc
import logging
from concurrent import futures

# Import des stubs générés
import llm_pb2
import llm_pb2_grpc

from application.chat_service import ChatApplicationService

class LLMServiceImpl(llm_pb2_grpc.LLMServiceServicer):
    """
    Implémentation du service gRPC.
    Elle délègue la logique métier à la couche application.
    """
    def __init__(self, chat_service: ChatApplicationService):
        self.chat_service = chat_service

    async def ChatStream(self, request_iterator, context):
        """
        Implémentation de la méthode RPC de streaming.
        """
        logging.info("Nouvelle connexion ChatStream initiée.")
        # TODO: Sécuriser ce flux (authentification, validation des entrées pour éviter les injections)
        try:
            async for chunk in self.chat_service.handle_chat_stream(request_iterator):
                yield llm_pb2.ChatResponse(chunk=chunk)
        except Exception as e:
            logging.error(f"Erreur dans ChatStream: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Une erreur interne est survenue: {e}")

async def serve(chat_service: ChatApplicationService):
    """
    Démarre le serveur gRPC asynchrone.
    """
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=100))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceImpl(chat_service), server)
    server.add_insecure_port('[::]:50051')
    logging.info("Serveur gRPC LLM démarré sur le port 50051...")
    await server.start()
    await server.wait_for_termination()
