import grpc
import logging
import os
import collections
import asyncio
import functools
from concurrent import futures
from google.protobuf import struct_pb2
from google.protobuf.json_format import MessageToDict
import json

import redis.asyncio as aioredis

from grpc_stubs import database_pb2
from grpc_stubs import database_pb2_grpc

from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard

from application.search_use_case import SearchUseCase

TOTAL_MAX_CONCURRENT_REQUESTS = int(os.getenv("TOTAL_MAX_CONCURRENT_REQUESTS", "200"))
DB_BATCH_SIZE = int(os.getenv("DB_BATCH_SIZE", "64"))
# Limiteur pour empêcher de saturer Zilliz Cloud avec des requêtes de classification
DB_MAX_CONCURRENT_ZILLIZ_DEFAULT = int(
    os.getenv("DB_MAX_CONCURRENT_ZILLIZ_DEFAULT", "2")
)

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

        # Compteurs de workers pour le notify ciblé (initialisés dans start_workers)
        self._high_workers_count = 0
        self._shared_workers_count = 0

        # Thread pools dédiés pour éviter la famine de threads (thread starvation)
        # Le pool HAUTE est exclusif : les requêtes HAUTE ne sont JAMAIS bloquées
        # par des requêtes MOYENNE/BASSE qui occupent tous les threads.
        self._high_executor = None
        self._default_executor = None

        # Global concurrency guard replaces local Zilliz semaphore
        redis_url = os.environ.get("REDIS_URL")
        _redis_client = None
        if redis_url:
            try:
                _redis_client = aioredis.from_url(
                    redis_url, encoding="utf-8", decode_responses=True
                )
                logging.info(
                    "database-recherche-service: Connected to Redis for concurrency guard."
                )
            except Exception as e:
                logging.warning(
                    "database-recherche-service: Redis unavailable: %s — using fallback",
                    e,
                )

        _guard_config = GuardConfig(
            tier=1,
            service_name="database-recherche-service",
        )
        self._concurrency_guard = MilvusConcurrencyGuard(
            _redis_client, _guard_config
        )

        # Event pour bloquer strictement les priorités inférieures quand HAUTE est actif
        self._lower_priorities_allowed = asyncio.Event()

        logging.info(
            f"Database Priority Queue Config: Total Slots={self.max_concurrent_requests}, Batch Size={DB_BATCH_SIZE}"
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

            # Sauvegarde des compteurs pour le notify ciblé
            self._high_workers_count = high_workers
            self._shared_workers_count = shared_workers

            # Initialisation de l'Event (ouvert par défaut)
            self._lower_priorities_allowed.set()

            # Global concurrency guard is initialized in __init__ (no per-worker setup needed)

            # Création des thread pools dédiés :
            # - _high_executor : exclusif aux workers HAUTE, dimensionné exactement
            #   pour que chaque high worker ait toujours un thread disponible.
            # - _default_executor : pour tous les autres workers (shared + medium + low).
            #   Dimensionné pour couvrir le nombre total de workers non-HAUTE.
            other_workers = shared_workers + medium_workers + low_workers
            self._high_executor = futures.ThreadPoolExecutor(
                max_workers=max(1, high_workers), thread_name_prefix="db-high"
            )
            self._default_executor = futures.ThreadPoolExecutor(
                max_workers=max(1, other_workers), thread_name_prefix="db-default"
            )

            logging.info(
                f"🔧 Thread pools créés: High={max(1, high_workers)} threads, Default={max(1, other_workers)} threads. Global concurrency guard: Tier 1 (search)"
            )

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

    async def _execute_task(self, func, args, kwargs, future, executor=None):
        """Execution standard pour les tâches non-batchables (GetSchema, ClassicSearch)."""
        try:
            # Smart Cancellation : on vérifie que le timeout gRPC client n'a pas annulé la requête
            if not future.cancelled():
                loop = asyncio.get_running_loop()
                # functools.partial est nécessaire car run_in_executor ne supporte pas **kwargs
                callable_with_kwargs = functools.partial(func, *args, **kwargs)
                async with self._concurrency_guard.slot():
                    result = await loop.run_in_executor(
                        executor, callable_with_kwargs
                    )
                future.set_result(result)
            else:
                logging.info(
                    "Ignoré par le DB worker: Requête déjà annulée (Timeout/Disconnect)"
                )
        except Exception as e:
            if not future.cancelled():
                future.set_exception(e)

    async def _process_queue_batch(self, batch, executor):
        """Orchestre l'exécution d'un batch de requêtes dynamiquement groupées avec guard de concurrence global."""
        first_item = batch[0]

        # Si c'est une tâche non-batchable (ClassicSearch, GetSchema), exécuter classiquement
        if callable(first_item[0]):
            func, args, kwargs, future = first_item
            await self._execute_task(func, args, kwargs, future, executor)
            return

        action_type = first_item[0]
        signature = first_item[1]

        # Nettoyer les requêtes annulées par timeout
        active_batch = [(d, f) for _, _, d, f in batch if not f.cancelled()]
        if not active_batch:
            return

        try:
            loop = asyncio.get_running_loop()

            if action_type == "search":
                vectors = [d["vector"] for d, _ in active_batch]
                kwargs = active_batch[0][0]["kwargs"]
                (collection_name, top_k, filter_expression, output_fields, _) = (
                    signature
                )

                if len(active_batch) > 1:
                    logging.info(
                        f"🔄 DB Dynamic Batching: Exécution de {len(active_batch)} requêtes 'search' sur {collection_name}."
                    )

                def _sync_search():
                    return self.use_case.execute_search_batch(
                        collection_name=collection_name,
                        vectors=vectors,
                        top_k=top_k,
                        filter_expression=filter_expression,
                        output_fields=list(output_fields) if output_fields else None,
                        **kwargs,
                    )

                async with self._concurrency_guard.slot():
                    results = await loop.run_in_executor(executor, _sync_search)

                for i, (_, future) in enumerate(active_batch):
                    if not future.cancelled():
                        future.set_result(results[i])

            elif action_type == "hybrid_search":
                dense_vectors = [d["dense_vector"] for d, _ in active_batch]
                query_texts = [d["query_text"] for d, _ in active_batch]
                kwargs = active_batch[0][0]["kwargs"]

                (
                    collection_name,
                    top_k,
                    dense_weight,
                    sparse_weight,
                    filter_expression,
                    output_fields,
                    _,
                ) = signature

                if len(active_batch) > 1:
                    logging.info(
                        f"🔄 DB Dynamic Batching: Exécution de {len(active_batch)} requêtes 'hybrid_search' sur {collection_name}."
                    )

                def _sync_hybrid():
                    return self.use_case.execute_hybrid_search_batch(
                        collection_name=collection_name,
                        dense_vectors=dense_vectors,
                        query_texts=query_texts,
                        top_k=top_k,
                        dense_weight=dense_weight,
                        sparse_weight=sparse_weight,
                        filter_expression=filter_expression,
                        output_fields=list(output_fields) if output_fields else None,
                        **kwargs,
                    )

                async with self._concurrency_guard.slot():
                    results = await loop.run_in_executor(executor, _sync_hybrid)

                for i, (_, future) in enumerate(active_batch):
                    if not future.cancelled():
                        future.set_result(results[i])

        except Exception as e:
            for _, future in active_batch:
                if not future.cancelled():
                    future.set_exception(e)

    def _extract_batch_from_queue(self, queue: collections.deque) -> list:
        """Extrait un lot de requêtes identiques de la queue spécifiée."""
        batch = []
        first_item = queue[0]

        if callable(first_item[0]):
            # Opération non batchable, on prend juste la première
            batch.append(queue.popleft())
        else:
            # Opération batchable, on regroupe par signature
            action_type = first_item[0]
            signature = first_item[1]
            while queue and len(batch) < DB_BATCH_SIZE:
                # Vérifier si l'élément suivant partage la même signature
                if (
                    not callable(queue[0][0])
                    and queue[0][0] == action_type
                    and queue[0][1] == signature
                ):
                    batch.append(queue.popleft())
                else:
                    break
        return batch

    async def _high_worker_loop(self, worker_id: str):
        while True:
            try:
                batch = []
                async with self.queue_cond:
                    while not self.high_queue:
                        await self.queue_cond.wait()
                    batch = self._extract_batch_from_queue(self.high_queue)

                if batch:
                    await self._process_queue_batch(
                        batch, executor=self._high_executor
                    )

                # Si la file HAUTE est complètement vide, on libère l'Event de pause
                # pour permettre aux workers MOYENNE/BASSE de reprendre le travail.
                async with self.queue_cond:
                    if not self.high_queue:
                        if not self._lower_priorities_allowed.is_set():
                            logging.info(
                                "⏸️ File HAUTE vide. Reprise des requêtes DB MOYENNE/BASSE."
                            )
                            self._lower_priorities_allowed.set()
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
                # Pause stricte : on attend que l'Event soit ouvert
                await self._lower_priorities_allowed.wait()

                batch = []
                async with self.queue_cond:
                    while not (self.high_queue or self.medium_queue or self.low_queue):
                        await self.queue_cond.wait()
                    # Si un HAUTE est arrivé entre temps, il faut se re-suspendre.
                    if not self._lower_priorities_allowed.is_set():
                        continue

                    if self.high_queue:
                        batch = self._extract_batch_from_queue(self.high_queue)
                    elif self.medium_queue:
                        batch = self._extract_batch_from_queue(self.medium_queue)
                    elif self.low_queue:
                        batch = self._extract_batch_from_queue(self.low_queue)

                if batch:
                    await self._process_queue_batch(
                        batch,
                        executor=self._default_executor,
                    )
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
                # Pause stricte : on attend que l'Event soit ouvert
                await self._lower_priorities_allowed.wait()

                batch = []
                async with self.queue_cond:
                    while not (self.medium_queue or self.low_queue):
                        await self.queue_cond.wait()
                    # Si un HAUTE est arrivé entre temps, il faut se re-suspendre.
                    if not self._lower_priorities_allowed.is_set():
                        continue

                    if self.medium_queue:
                        batch = self._extract_batch_from_queue(self.medium_queue)
                    elif self.low_queue:
                        batch = self._extract_batch_from_queue(self.low_queue)

                if batch:
                    await self._process_queue_batch(
                        batch,
                        executor=self._default_executor,
                    )
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
                # Pause stricte : on attend que l'Event soit ouvert
                await self._lower_priorities_allowed.wait()

                batch = []
                async with self.queue_cond:
                    while not self.low_queue:
                        await self.queue_cond.wait()
                    # Si un HAUTE est arrivé entre temps, il faut se re-suspendre.
                    if not self._lower_priorities_allowed.is_set():
                        continue

                    if self.low_queue:
                        batch = self._extract_batch_from_queue(self.low_queue)

                if batch:
                    await self._process_queue_batch(
                        batch,
                        executor=self._default_executor,
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le DB worker {worker_id}: {e}",
                    exc_info=True,
                )
                
    async def _execute_with_priority(self, source_service: str, func, *args, **kwargs):
        """Wrapper pour les requêtes classiques non batchables (GetSchema, ClassicSearch)"""
        queue_item = (func, args, kwargs)
        return await self._enqueue_request(source_service, queue_item)

    async def _enqueue_request(self, source_service: str, queue_item: tuple):
        """Place l'élément dans la bonne file selon la priorité du service source."""
        if self.max_concurrent_requests <= 0:
            raise NotImplementedError(
                "Exécution directe non supportée avec la logique de batching"
            )

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

        # Ajout du future à la fin de l'élément (format attendu par les workers)
        full_queue_item = queue_item + (future,)

        async with self.queue_cond:
            if priority == 1:
                # Dès qu'une HAUTE entre, on ferme physiquement la porte aux requêtes inférieures
                if self._lower_priorities_allowed.is_set():
                    logging.info(
                        "⏸️ Requête HAUTE DB reçue. Pause des requêtes MOYENNE/BASSE."
                    )
                    self._lower_priorities_allowed.clear()
                self.high_queue.append(full_queue_item)
            elif priority == 2:
                self.medium_queue.append(full_queue_item)
            else:
                self.low_queue.append(full_queue_item)

            logging.info(
                f"Requête DB reçue de '{source_service}'. Priorité: {priority_label}. [Queues -> H:{len(self.high_queue)}, M:{len(self.medium_queue)}, L:{len(self.low_queue)}]"
            )

            # Notify ciblé pour éviter le thundering herd :
            # - HAUTE: réveille les high workers + shared workers (garantie de pic up immédiat)
            # - MOYENNE/BASSE: réveille 1 seul worker (suffisant, un shared/medium/low prendra la tâche)
            if priority == 1:
                self.queue_cond.notify(
                    self._high_workers_count + self._shared_workers_count
                )
            else:
                self.queue_cond.notify(1)

        try:
            return await future
        except asyncio.CancelledError:
            # Smart Cancellation
            future.cancel()
            logging.warning(
                f"Requête DB annulée par le client (timeout/disconnect). Priority: {priority_label}"
            )
            raise

    async def _execute_batchable(
        self, source_service: str, action_type: str, signature: tuple, data: dict
    ):
        """Wrapper pour les requêtes batchables (Search, HybridSearch)"""
        queue_item = (action_type, signature, data)
        return await self._enqueue_request(source_service, queue_item)

    def _convert_to_proto_results(self, results):
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
                    metadata_struct.update({"error": "Metadata serialization failed"})

            proto_results.append(
                database_pb2.SearchResult(
                    id=str(res.id),
                    score=float(res.score),
                    metadata=metadata_struct,
                    source=str(res.source),
                )
            )
        return proto_results

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

            # Signature de la requête pour grouper le batch
            kwargs_tuple = tuple(sorted(kwargs.items()))
            signature = (
                request.collection_name,
                request.top_k,
                (
                    request.filter_expression
                    if request.HasField("filter_expression")
                    else None
                ),
                tuple(request.output_fields) if request.output_fields else (),
                kwargs_tuple,
            )

            data = {"vector": list(request.query_embedding), "kwargs": kwargs}

            results = await self._execute_batchable(
                source_service, "search", signature, data
            )
            proto_results = self._convert_to_proto_results(results)

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
            proto_results = self._convert_to_proto_results(results)
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

            # Extraire les kwargs depuis options pour la signature
            ef = kwargs.get("ef", None)
            if ef is not None:
                ef = int(ef)
            radius = kwargs.get("radius", None)
            if radius is not None:
                radius = float(radius)
            range_filter = kwargs.get("rangeFilter", kwargs.get("range_filter", None))
            if range_filter is not None:
                range_filter = float(range_filter)
            drop_ratio_search = float(
                kwargs.get("dropRatioSearch", kwargs.get("drop_ratio_search", 0.0))
            )
            dense_limit_multiplier = int(
                kwargs.get(
                    "denseLimitMultiplier", kwargs.get("dense_limit_multiplier", 1)
                )
            )
            ranker_type = str(
                kwargs.get("rankerType", kwargs.get("ranker_type", "weighted"))
            )
            rrf_k = int(kwargs.get("rrfK", kwargs.get("rrf_k", 60)))

            logging.info(
                f"[HybridSearch] Params: ef={ef}, radius={radius}, "
                f"range_filter={range_filter}, drop_ratio_search={drop_ratio_search}, "
                f"dense_limit_multiplier={dense_limit_multiplier}, "
                f"ranker_type={ranker_type}, rrf_k={rrf_k}"
            )
            
            # On laisse les params d'exploration dans kwargs pour le use_case
            kwargs_tuple = tuple(sorted(kwargs.items()))
            signature = (
                request.collection_name,
                request.top_k,
                dense_weight,
                sparse_weight,
                (
                    request.filter_expression
                    if request.HasField("filter_expression")
                    else None
                ),
                tuple(request.output_fields) if request.output_fields else (),
                kwargs_tuple,
            )

            data = {
                "dense_vector": list(request.dense_vector),
                "query_text": request.query_text,
                "kwargs": kwargs,
            }

            results = await self._execute_batchable(
                source_service, "hybrid_search", signature, data
            )
            proto_results = self._convert_to_proto_results(results)

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
