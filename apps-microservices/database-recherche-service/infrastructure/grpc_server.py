import grpc
import logging
import os
import collections
import asyncio
from concurrent import futures
from google.protobuf import struct_pb2
from google.protobuf.json_format import MessageToDict
import json

from grpc_stubs import database_pb2
from grpc_stubs import database_pb2_grpc

from application.search_use_case import SearchUseCase

TOTAL_MAX_CONCURRENT_REQUESTS = int(os.getenv("TOTAL_MAX_CONCURRENT_REQUESTS", "100"))

high_priority_services_str = os.getenv(
    "HIGH_PRIORITY_SERVICES", "api-recherche-service, api-chat-llm-service"
)
HIGH_PRIORITY_SERVICES = {
    s.strip() for s in high_priority_services_str.split(",") if s.strip()
}

medium_priority_services_str = os.getenv(
    "MEDIUM_PRIORITY_SERVICES", "api-classification-service"
)
MEDIUM_PRIORITY_SERVICES = {
    s.strip() for s in medium_priority_services_str.split(",") if s.strip()
}


class DatabaseSearchServiceImpl(database_pb2_grpc.DatabaseSearchServiceServicer):
    def __init__(self, use_case: SearchUseCase):
        self.use_case = use_case

        self.max_concurrent_requests = TOTAL_MAX_CONCURRENT_REQUESTS
        self.workers = []

        self.high_queue = collections.deque()
        self.medium_queue = collections.deque()
        self.low_queue = collections.deque()
        self.queue_cond = asyncio.Condition()

        logging.info(
            f"Database Priority Queue Config: Total Slots={self.max_concurrent_requests}"
        )
        logging.info(f"High Priority Services: {HIGH_PRIORITY_SERVICES}")
        logging.info(f"Medium Priority Services: {MEDIUM_PRIORITY_SERVICES}")

    async def start_workers(self):
        """Démarre les workers en arrière-plan pour exécuter les tâches Milvus avec garanties anti-starvation et voie rapide."""
        if not self.workers and self.max_concurrent_requests > 0:
            total = self.max_concurrent_requests

            if total >= 4:
                high_workers = max(1, int(total * 0.2))  # Fast Lane HAUTE (exclusive)
                low_workers = max(1, int(total * 0.1))  # Plancher BASSE
                medium_workers = max(1, int(total * 0.1))  # Plancher MOYENNE
                shared_workers = total - high_workers - low_workers - medium_workers
            else:
                shared_workers = total
                high_workers = 0
                medium_workers = 0
                low_workers = 0

            for i in range(high_workers):
                self.workers.append(
                    asyncio.create_task(self._high_worker_loop(f"high-{i}"))
                )
            for i in range(shared_workers):
                self.workers.append(
                    asyncio.create_task(self._shared_worker_loop(f"shared-{i}"))
                )
            for i in range(medium_workers):
                self.workers.append(
                    asyncio.create_task(self._medium_worker_loop(f"medium-{i}"))
                )
            for i in range(low_workers):
                self.workers.append(
                    asyncio.create_task(self._low_worker_loop(f"low-{i}"))
                )

            logging.info(
                f"✅ {total} workers de base de données démarrés (High: {high_workers}, Shared: {shared_workers}, Medium: {medium_workers}, Low: {low_workers})."
            )

    async def _execute_task(self, func, args, kwargs, future):
        try:
            # Smart Cancellation : on vérifie que le timeout gRPC client n'a pas annulé la requête
            if not future.cancelled():
                result = await asyncio.to_thread(func, *args, **kwargs)
                future.set_result(result)
            else:
                logging.info(
                    "Ignoré par le DB worker: Requête déjà annulée (Timeout/Disconnect)"
                )
        except Exception as e:
            if not future.cancelled():
                future.set_exception(e)

    async def _high_worker_loop(self, worker_id: str):
        while True:
            try:
                async with self.queue_cond:
                    while not self.high_queue:
                        await self.queue_cond.wait()
                    func, args, kwargs, future = self.high_queue.popleft()

                await self._execute_task(func, args, kwargs, future)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le DB worker {worker_id}: {e}",
                    exc_info=True,
                )

    async def _shared_worker_loop(self, worker_id: str):
        while True:
            try:
                async with self.queue_cond:
                    while not (self.high_queue or self.medium_queue or self.low_queue):
                        await self.queue_cond.wait()
                    if self.high_queue:
                        func, args, kwargs, future = self.high_queue.popleft()
                    elif self.medium_queue:
                        func, args, kwargs, future = self.medium_queue.popleft()
                    else:
                        func, args, kwargs, future = self.low_queue.popleft()

                await self._execute_task(func, args, kwargs, future)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le DB worker {worker_id}: {e}",
                    exc_info=True,
                )

    async def _medium_worker_loop(self, worker_id: str):
        while True:
            try:
                async with self.queue_cond:
                    while not (self.medium_queue or self.low_queue):
                        await self.queue_cond.wait()
                    if self.medium_queue:
                        func, args, kwargs, future = self.medium_queue.popleft()
                    else:
                        func, args, kwargs, future = self.low_queue.popleft()

                await self._execute_task(func, args, kwargs, future)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le DB worker {worker_id}: {e}",
                    exc_info=True,
                )

    async def _low_worker_loop(self, worker_id: str):
        while True:
            try:
                async with self.queue_cond:
                    while not self.low_queue:
                        await self.queue_cond.wait()
                    func, args, kwargs, future = self.low_queue.popleft()

                await self._execute_task(func, args, kwargs, future)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le DB worker {worker_id}: {e}",
                    exc_info=True,
                )

    async def _execute_with_priority(self, source_service: str, func, *args, **kwargs):
        """
        Gère la priorité et met en file d'attente la requête Milvus.
        """
        if self.max_concurrent_requests <= 0:
            return await asyncio.to_thread(func, *args, **kwargs)

        is_high_priority = source_service in HIGH_PRIORITY_SERVICES
        is_medium_priority = source_service in MEDIUM_PRIORITY_SERVICES

        if is_high_priority:
            priority = 1
            priority_label = "HAUTE"
        elif is_medium_priority:
            priority = 2
            priority_label = "MOYENNE"
        else:
            priority = 3
            priority_label = "BASSE"

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async with self.queue_cond:
            item = (func, args, kwargs, future)
            if priority == 1:
                self.high_queue.append(item)
            elif priority == 2:
                self.medium_queue.append(item)
            else:
                self.low_queue.append(item)

            logging.info(
                f"Requête DB reçue de '{source_service}'. Priorité: {priority_label}. [Queues -> H:{len(self.high_queue)}, M:{len(self.medium_queue)}, L:{len(self.low_queue)}]"
            )

            self.queue_cond.notify_all()

        try:
            return await future
        except asyncio.CancelledError:
            # Smart Cancellation
            future.cancel()
            logging.warning(
                f"Requête DB annulée par le client (timeout/disconnect). Priority: {priority_label}"
            )
            raise

    async def Search(self, request, context):
        source_service = (
            request.source_service
            if request.HasField("source_service")
            else "unknown-service"
        )
        logging.info(
            f"Requête de recherche reçue de '{source_service}' pour la collection '{request.collection_name}' avec top_k={request.top_k}"
        )
        # TODO: Sécuriser ce flux (authentification, validation des entrées)
        try:
            kwargs = {}
            if request.HasField("options"):
                kwargs = MessageToDict(request.options)

            results = await self._execute_with_priority(
                source_service,
                self.use_case.execute_search,
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
        except asyncio.CancelledError:
            # Si le timeout se produit, gRPC annule la tâche.
            raise
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
        source_service = (
            request.source_service
            if request.HasField("source_service")
            else "unknown-service"
        )
        logging.info(
            f"Requête GetSchema reçue de '{source_service}' pour la collection '{request.collection_name}'"
        )
        try:
            schema_map = await self._execute_with_priority(
                source_service,
                self.use_case.get_collection_schema,
                request.collection_name,
            )
            return database_pb2.GetSchemaResponse(fields=schema_map)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Erreur dans GetSchema: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la récupération du schéma.")
            return database_pb2.GetSchemaResponse()

    async def ClassicSearch(self, request, context):
        source_service = (
            request.source_service
            if request.HasField("source_service")
            else "unknown-service"
        )
        logging.info(
            f"Requête de recherche classique reçue de '{source_service}' pour '{request.collection_name}' avec le filtre '{request.filter_expression}'"
        )
        try:
            results = await self._execute_with_priority(
                source_service,
                self.use_case.execute_classic_search,
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
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Erreur dans ClassicSearch: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la recherche classique.")
            return database_pb2.SearchResponse()

    async def HybridSearch(self, request, context):
        source_service = (
            request.source_service
            if request.HasField("source_service")
            else "unknown-service"
        )
        logging.info(
            f"Requête de recherche hybride reçue de '{source_service}' pour la collection '{request.collection_name}' avec top_k={request.top_k}"
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

            results = await self._execute_with_priority(
                source_service,
                self.use_case.execute_hybrid_search,
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
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Erreur dans HybridSearch: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors de la recherche hybride.")
            return database_pb2.SearchResponse()


async def serve(use_case: SearchUseCase):
    # Nous augmentons le thread pool gRPC pour accepter plus de requêtes, le bottleneck réel est géré par nos workers
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=200))
    servicer = DatabaseSearchServiceImpl(use_case)
    await servicer.start_workers()

    database_pb2_grpc.add_DatabaseSearchServiceServicer_to_server(servicer, server)
    server.add_insecure_port("[::]:50054")
    logging.info("Serveur gRPC Database Search démarré sur le port 50054...")
    await server.start()
    await server.wait_for_termination()
