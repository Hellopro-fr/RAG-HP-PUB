import grpc
import logging
from concurrent import futures
from google.protobuf import struct_pb2
from google.protobuf.json_format import MessageToDict
import json

from grpc_stubs import database_pb2
from grpc_stubs import database_pb2_grpc

from application.search_use_case import SearchUseCase


class DatabaseSearchServiceImpl(database_pb2_grpc.DatabaseSearchServiceServicer):
    def __init__(self, use_case: SearchUseCase):
        self.use_case = use_case

    async def Search(self, request, context):
        logging.info(
            f"Requête de recherche reçue pour la collection '{request.collection_name}' avec top_k={request.top_k}"
        )
        # TODO: Sécuriser ce flux (authentification, validation des entrées)
        try:
            kwargs = {}
            if request.HasField("options"):
                kwargs = MessageToDict(request.options)

            results = self.use_case.execute_search(
                collection_name=request.collection_name,
                vector=list(request.query_embedding),
                top_k=request.top_k,
                filter_expression=(
                    request.filter_expression
                    if request.HasField("filter_expression")
                    else None
                ),
                output_fields=(
                    list(request.output_fields) if request.output_fields else None
                ),
                **kwargs,
            )

            proto_results = []
            for res in results:
                # Conversion du dictionnaire de métadonnées en Struct protobuf
                metadata_struct = struct_pb2.Struct()
                if res.metadata:
                    try:
                        # --- CORRECTION ---
                        # Cette astuce force la conversion de tous les types non standards
                        # (comme numpy.float32) en types Python de base que Protobuf comprend.
                        # default=str est une sécurité pour convertir les types inconnus (comme datetime) en chaîne.
                        sanitized_metadata = json.loads(
                            json.dumps(res.metadata, default=str)
                        )
                        metadata_struct.update(sanitized_metadata)
                    except TypeError as e:
                        logging.warning(
                            f"Impossible de sérialiser les métadonnées pour l'ID {res.id}: {e}"
                        )
                        metadata_struct.update(
                            {"error": "Metadata serialization failed"}
                        )

                proto_results.append(
                    database_pb2.SearchResult(
                        id=str(res.id),
                        score=float(res.score),
                        metadata=metadata_struct,
                        source=str(res.source),
                    )
                )

            return database_pb2.SearchResponse(results=proto_results)
        except Exception as e:
            logging.error(f"Erreur dans Search: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(
                "Erreur interne lors de la recherche dans la base de données."
            )
            return database_pb2.SearchResponse()

    async def GetSchema(self, request, context):
        """
        Implémentation de la méthode RPC GetSchema.
        """
        logging.info(
            f"Requête GetSchema reçue pour la collection '{request.collection_name}'"
        )
        try:
            schema_map = self.use_case.get_collection_schema(request.collection_name)
            return database_pb2.GetSchemaResponse(fields=schema_map)
        except Exception as e:
            logging.error(f"Erreur dans GetSchema: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la récupération du schéma.")
            return database_pb2.GetSchemaResponse()

    async def ClassicSearch(self, request, context):
        logging.info(
            f"Requête de recherche classique reçue pour '{request.collection_name}' avec le filtre '{request.filter_expression}'"
        )
        try:
            results = self.use_case.execute_classic_search(
                collection_name=request.collection_name,
                filter_expression=request.filter_expression,
                top_k=request.top_k,
                output_fields=(
                    list(request.output_fields) if request.output_fields else None
                ),
            )

            proto_results = []
            for res in results:
                metadata_struct = struct_pb2.Struct()
                if res.metadata:
                    try:
                        sanitized_metadata = json.loads(
                            json.dumps(res.metadata, default=str)
                        )
                        metadata_struct.update(sanitized_metadata)
                    except TypeError as e:
                        logging.warning(
                            f"Impossible de sérialiser les métadonnées pour l'ID {res.id}: {e}"
                        )
                        metadata_struct.update(
                            {"error": "Metadata serialization failed"}
                        )

                proto_results.append(
                    database_pb2.SearchResult(
                        id=str(res.id),
                        score=float(res.score),
                        metadata=metadata_struct,
                        source=str(res.source),
                    )
                )

            return database_pb2.SearchResponse(results=proto_results)
        except Exception as e:
            logging.error(f"Erreur dans ClassicSearch: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la recherche classique.")
            return database_pb2.SearchResponse()

    async def HybridSearch(self, request, context):
        logging.info(
            f"Requête de recherche hybride reçue pour la collection '{request.collection_name}' avec top_k={request.top_k}"
        )
        try:
            kwargs = {}
            if request.HasField("options"):
                kwargs = MessageToDict(request.options)

            # Poids par défaut si non spécifiés
            dense_weight = (
                request.dense_weight if request.HasField("dense_weight") else 0.7
            )
            sparse_weight = (
                request.sparse_weight if request.HasField("sparse_weight") else 0.3
            )

            # Extraction des paramètres d'exploration depuis les options
            ef = kwargs.pop("ef", None)
            if ef is not None:
                ef = int(ef)
            radius = kwargs.pop("radius", None)
            if radius is not None:
                radius = float(radius)
            range_filter = kwargs.pop("rangeFilter", kwargs.pop("range_filter", None))
            if range_filter is not None:
                range_filter = float(range_filter)
            drop_ratio_search = float(
                kwargs.pop("dropRatioSearch", kwargs.pop("drop_ratio_search", 0.0))
            )
            dense_limit_multiplier = int(
                kwargs.pop(
                    "denseLimitMultiplier", kwargs.pop("dense_limit_multiplier", 1)
                )
            )
            ranker_type = str(
                kwargs.pop("rankerType", kwargs.pop("ranker_type", "weighted"))
            )
            rrf_k = int(kwargs.pop("rrfK", kwargs.pop("rrf_k", 60)))

            logging.info(
                f"[HybridSearch] Params: ef={ef}, radius={radius}, "
                f"range_filter={range_filter}, drop_ratio_search={drop_ratio_search}, "
                f"dense_limit_multiplier={dense_limit_multiplier}, "
                f"ranker_type={ranker_type}, rrf_k={rrf_k}"
            )

            results = self.use_case.execute_hybrid_search(
                collection_name=request.collection_name,
                dense_vector=list(request.dense_vector),
                query_text=request.query_text,
                top_k=request.top_k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                filter_expression=(
                    request.filter_expression
                    if request.HasField("filter_expression")
                    else None
                ),
                output_fields=(
                    list(request.output_fields) if request.output_fields else None
                ),
                ef=ef,
                radius=radius,
                range_filter=range_filter,
                drop_ratio_search=drop_ratio_search,
                dense_limit_multiplier=dense_limit_multiplier,
                ranker_type=ranker_type,
                rrf_k=rrf_k,
                **kwargs,
            )

            proto_results = []
            for res in results:
                metadata_struct = struct_pb2.Struct()
                if res.metadata:
                    try:
                        sanitized_metadata = json.loads(
                            json.dumps(res.metadata, default=str)
                        )
                        metadata_struct.update(sanitized_metadata)
                    except TypeError as e:
                        logging.warning(
                            f"Impossible de sérialiser les métadonnées pour l'ID {res.id}: {e}"
                        )
                        metadata_struct.update(
                            {"error": "Metadata serialization failed"}
                        )

                proto_results.append(
                    database_pb2.SearchResult(
                        id=str(res.id),
                        score=float(res.score),
                        metadata=metadata_struct,
                        source=str(res.source),
                    )
                )

            return database_pb2.SearchResponse(results=proto_results)
        except Exception as e:
            logging.error(f"Erreur dans HybridSearch: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la recherche hybride.")
            return database_pb2.SearchResponse()


async def serve(use_case: SearchUseCase):
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=50))
    database_pb2_grpc.add_DatabaseSearchServiceServicer_to_server(
        DatabaseSearchServiceImpl(use_case), server
    )
    server.add_insecure_port("[::]:50054")
    logging.info("Serveur gRPC Database Search démarré sur le port 50054...")
    await server.start()
    await server.wait_for_termination()
