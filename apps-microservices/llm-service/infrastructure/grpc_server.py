import grpc
import logging
from concurrent import futures

# Import des stubs générés
from grpc_stubs import llm_pb2
from grpc_stubs import llm_pb2_grpc

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
            
    async def Chat(self, request, context):
        """
        Implémentation de la méthode RPC unaire Chat.
        """
        logging.info(f"Nouvelle requête Chat reçue pour le message: '{request.message[:50]}...'")
        try:
            full_message = await self.chat_service.handle_chat_completion(request.message)
            return llm_pb2.FullChatResponse(full_message=full_message)
        except Exception as e:
            logging.error(f"Erreur dans Chat: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Une erreur interne est survenue: {e}")
            return llm_pb2.FullChatResponse()
        
    async def ChatBatch(self, request, context):
        """
        Implémentation de la méthode RPC unaire ChatBatch.
        """
        num_messages = len(request.messages)
        logging.info(f"Nouvelle requête ChatBatch reçue pour {num_messages} messages.")
        try:
            responses = await self.chat_service.handle_chat_batch_completion(list(request.messages))
            return llm_pb2.ChatBatchResponse(full_messages=responses)
        except Exception as e:
            logging.error(f"Erreur dans ChatBatch: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Une erreur interne est survenue: {e}")
            return llm_pb2.ChatBatchResponse()

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
