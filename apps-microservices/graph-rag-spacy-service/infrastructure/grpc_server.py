import grpc
import logging
from concurrent import futures

from grpc_stubs import spacy_pb2
from grpc_stubs import spacy_pb2_grpc

from application.spacy_use_case import SpacyUseCase
from app.config import settings


class GraphSpacyServiceServicer(spacy_pb2_grpc.GraphSpacyServiceServicer):
    def __init__(self, use_case: SpacyUseCase):
        self.use_case = use_case

    def Lemmatize(self, request, context):
        try:
            tokens_data = self.use_case.lemmatize(request.text)
            pb_tokens = [
                spacy_pb2.Token(
                    text=t["text"], lemma=t["lemma"], pos=t["pos"], is_stop=t["is_stop"]
                )
                for t in tokens_data
            ]
            return spacy_pb2.LemmatizeResponse(tokens=pb_tokens)
        except Exception as e:
            logging.error(f"Error in Lemmatize: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return spacy_pb2.LemmatizeResponse()

    def ExtractEntities(self, request, context):
        try:
            ents_data = self.use_case.extract_entities(request.text)
            pb_ents = [
                spacy_pb2.Entity(
                    text=e["text"],
                    label=e["label"],
                    start_char=e["start_char"],
                    end_char=e["end_char"],
                )
                for e in ents_data
            ]
            return spacy_pb2.ExtractEntitiesResponse(entities=pb_ents)
        except Exception as e:
            logging.error(f"Error in ExtractEntities: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return spacy_pb2.ExtractEntitiesResponse()


async def serve(use_case: SpacyUseCase):
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    spacy_pb2_grpc.add_GraphSpacyServiceServicer_to_server(
        GraphSpacyServiceServicer(use_case), server
    )
    server.add_insecure_port(f"[::]:{settings.GRPC_PORT}")
    logging.info(f"Graph Spacy Service started on port {settings.GRPC_PORT}")
    await server.start()
    await server.wait_for_termination()
