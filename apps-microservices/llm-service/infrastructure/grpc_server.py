import grpc
import logging
from concurrent import futures
from grpc_stubs import llm_pb2, llm_pb2_grpc
from application.chat_service import ChatApplicationService
from google.protobuf import struct_pb2


class LLMServiceImpl(llm_pb2_grpc.LLMServiceServicer):
    def __init__(self, chat_service: ChatApplicationService):
        self.chat_service = chat_service

    async def ChatStream(self, request_iterator, context):
        logging.info("Nouvelle connexion ChatStream initiée.")
        try:
            async for chunk in self.chat_service.handle_chat_stream(request_iterator):
                yield llm_pb2.ChatResponse(chunk=chunk)
        except Exception as e:
            logging.error(f"Erreur dans ChatStream: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Une erreur interne est survenue: {e}")

    async def Chat(self, request, context):
        logging.info(f"Nouvelle requête Chat reçue.")
        try:
            temperature = (
                request.temperature if request.HasField("temperature") else 0.7
            )
            max_tokens = request.max_tokens if request.HasField("max_tokens") else 1024
            enable_thinking = (
                request.enable_thinking
                if request.HasField("enable_thinking")
                else False
            )
            options = request.options if request.HasField("options") else {}

            full_message_dict = await self.chat_service.handle_chat_completion(
                request.message,
                temperature,
                max_tokens,
                enable_thinking,
                options=options,
            )
            
            # Convert the Python dictionary to a Protobuf Struct
            response_struct = struct_pb2.Struct()
            response_struct.update(full_message_dict)

            return llm_pb2.FullChatResponse(full_message=response_struct)
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
            temperature = (
                request.temperature if request.HasField("temperature") else 0.7
            )
            max_tokens = request.max_tokens if request.HasField("max_tokens") else 1024
            enable_thinking = (
                request.enable_thinking
                if request.HasField("enable_thinking")
                else False
            )
            options = request.options if request.HasField("options") else {}

            responses_list_of_dicts = await self.chat_service.handle_chat_batch_completion(
                list(request.messages),
                temperature,
                max_tokens,
                enable_thinking,
                options=options,
            )

            # Convert each Python dictionary in the list to a Protobuf Struct
            response_structs = []
            for resp_dict in responses_list_of_dicts:
                struct = struct_pb2.Struct()
                struct.update(resp_dict)
                response_structs.append(struct)

            return llm_pb2.ChatBatchResponse(full_messages=response_structs)
        except Exception as e:
            logging.error(f"Erreur dans ChatBatch: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Une erreur interne est survenue: {e}")
            return llm_pb2.ChatBatchResponse()


async def serve(chat_service: ChatApplicationService):
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=100))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceImpl(chat_service), server)
    server.add_insecure_port("[::]:50051")
    logging.info("Serveur gRPC LLM démarré sur le port 50051...")
    await server.start()
    await server.wait_for_termination()
