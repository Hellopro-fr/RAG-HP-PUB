import logging
import numpy as np
import os
import collections
from typing import List
import asyncio
import functools
from concurrent import futures
from sentence_transformers import SentenceTransformer
from tritonclient.grpc.aio import (
    InferenceServerClient,
    InferInput,
    InferRequestedOutput,
)
import torch
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer
from common_utils.metrics.prometheus import measure_processing_time

TRITON_URL = os.getenv("TRITON_URL", "localhost:8001")
MODEL_NAME = "camembert-embedding"
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
# Limite stricte globale (remplace les silos séparés)
TOTAL_MAX_CONCURRENT_REQUESTS = int(os.getenv("TOTAL_MAX_CONCURRENT_REQUESTS", "10"))

# Limiteur Triton pour éviter la saturation du GPU par les requêtes non-HAUTE
TRITON_MAX_CONCURRENT_DEFAULT = int(os.getenv("TRITON_MAX_CONCURRENT_DEFAULT", "3"))

high_priority_services_str = os.getenv("HIGH_PRIORITY_SERVICES", "")
HIGH_PRIORITY_SERVICES = {
    s.strip() for s in high_priority_services_str.split(",") if s.strip()
}

medium_priority_services_str = os.getenv("MEDIUM_PRIORITY_SERVICES", "")
MEDIUM_PRIORITY_SERVICES = {
    s.strip() for s in medium_priority_services_str.split(",") if s.strip()
}


class EmbeddingUseCase:
    def __init__(self):
        tokenizer_name = "dangvantuan/sentence-camembert-large"
        logging.info(f"Chargement du tokenizer: {tokenizer_name}")
        self.tokenizer = SentenceTransformer(tokenizer_name).tokenizer
        self.tokenizer_pre = AutoTokenizer.from_pretrained(tokenizer_name)
        self.triton_client = InferenceServerClient(url=TRITON_URL)
        self.batch_size = EMBEDDING_BATCH_SIZE

        # --- File multi-niveaux et pool de workers ---
        self.max_concurrent_requests = TOTAL_MAX_CONCURRENT_REQUESTS
        self.workers = []

        self.high_queue = collections.deque()
        self.medium_queue = collections.deque()
        self.low_queue = collections.deque()
        self.queue_cond = asyncio.Condition()

        # Limiteur pour Triton pour les requêtes MOYENNE/BASSE
        self._triton_limiter = None

        # Thread pools et compteurs
        self._high_executor = None
        self._default_executor = None
        self._high_workers_count = 0
        self._shared_workers_count = 0

        # Event pour bloquer strictement les priorités inférieures quand HAUTE est actif
        self._lower_priorities_allowed = asyncio.Event()

        logging.info(f"Taille de batch pour l'embedding: {self.batch_size}")
        logging.info(
            f"Total des slots d'exécution concurrents: {self.max_concurrent_requests}"
        )
        logging.info(f"Services haute priorité: {HIGH_PRIORITY_SERVICES}")
        logging.info(f"Services moyenne priorité: {MEDIUM_PRIORITY_SERVICES}")

    async def start_workers(self):
        """Démarre les workers en arrière-plan avec des garanties anti-starvation et une voie rapide."""
        if not self.workers and self.max_concurrent_requests > 0:
            total = self.max_concurrent_requests

            # Allocation des workers pour éviter la famine (starvation) et garantir la voie rapide HAUTE
            if total >= 4:
                high_workers = max(1, int(total * 0.2))  # Fast Lane HAUTE (exclusive)
                medium_workers = max(1, int(total * 0.1))  # Plancher MOYENNE
                low_workers = max(1, int(total * 0.1))  # Plancher BASSE
                shared_workers = total - high_workers - medium_workers - low_workers
            else:
                shared_workers = total
                high_workers = 0
                medium_workers = 0
                low_workers = 0

            # Initialisation de l'Event (ouvert par défaut)
            self._lower_priorities_allowed.set()

            # Sauvegarde des compteurs pour le notify ciblé
            self._high_workers_count = high_workers
            self._shared_workers_count = shared_workers

            # Initialisation du limiteur Triton
            self._triton_limiter = asyncio.Semaphore(TRITON_MAX_CONCURRENT_DEFAULT)

            # Création des thread pools dédiés (pour le CPU binding: tokenization/pooling)
            other_workers = shared_workers + medium_workers + low_workers
            self._high_executor = futures.ThreadPoolExecutor(
                max_workers=max(1, high_workers), thread_name_prefix="emb-high"
            )
            self._default_executor = futures.ThreadPoolExecutor(
                max_workers=max(1, other_workers), thread_name_prefix="emb-default"
            )

            logging.info(
                f"🔧 Triton Limiter: {TRITON_MAX_CONCURRENT_DEFAULT}. Thread pools créés: High={max(1, high_workers)}, Default={max(1, other_workers)}."
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
                f"✅ {total} workers d'embedding démarrés (High: {high_workers}, Shared: {shared_workers}, Medium: {medium_workers}, Low: {low_workers})."
            )

    async def _process_batch(self, batch, executor=None, limiter=None):
        """Prend un ensemble de requêtes (Dynamic Batching), les exécute sur le GPU et distribue les résultats."""
        # 1. Ignorer les requêtes annulées (Timeout)
        active_batch = [
            (texts, future) for texts, future in batch if not future.cancelled()
        ]
        if not active_batch:
            return

        # 2. Agréger les textes
        all_texts = []
        for texts, future in active_batch:
            all_texts.extend(texts)

        if len(active_batch) > 1:
            logging.info(
                f"🔄 Dynamic Batching: Agrégation de {len(active_batch)} requêtes en un seul batch de {len(all_texts)} textes."
            )

        # 3. Traiter le batch massif
        try:
            results = await self._process_embeddings(
                all_texts, executor=executor, limiter=limiter
            )

            # 4. Redistribuer les résultats aux bons futures
            current_idx = 0
            for texts, future in active_batch:
                if not future.cancelled():
                    req_len = len(texts)
                    req_results = results[current_idx : current_idx + req_len]
                    future.set_result(req_results)
                current_idx += len(texts)

        except Exception as e:
            for texts, future in active_batch:
                if not future.cancelled():
                    future.set_exception(e)

    async def _high_worker_loop(self, worker_id: str):
        """Voie rapide stricte (Fast Lane): Ne traite QUE la haute priorité, avec Dynamic Batching."""
        while True:
            try:
                batch = []
                async with self.queue_cond:
                    while not self.high_queue:
                        await self.queue_cond.wait()

                    # Draine la queue jusqu'à atteindre la taille optimale du batch
                    current_texts = 0
                    while self.high_queue and current_texts < self.batch_size:
                        texts, future = self.high_queue[0]  # Peek
                        if (
                            current_texts > 0
                            and current_texts + len(texts) > self.batch_size
                        ):
                            break  # On dépasse la capacité optimale, on laisse pour le prochain worker
                        texts, future = self.high_queue.popleft()
                        batch.append((texts, future))
                        current_texts += len(texts)

                if batch:
                    await self._process_batch(
                        batch, executor=self._high_executor, limiter=None
                    )

                # Si la file HAUTE est complètement vide, on libère l'Event de pause
                # pour permettre aux workers MOYENNE/BASSE de reprendre le travail.
                async with self.queue_cond:
                    if not self.high_queue:
                        if not self._lower_priorities_allowed.is_set():
                            logging.info(
                                "⏸️ File HAUTE vide. Reprise des requêtes MOYENNE/BASSE."
                            )
                            self._lower_priorities_allowed.set()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le worker {worker_id}: {e}", exc_info=True
                )

    async def _shared_worker_loop(self, worker_id: str):
        while True:
            try:
                # Pause stricte : on attend que l'Event soit ouvert (pas de requêtes HAUTE en cours)
                await self._lower_priorities_allowed.wait()

                batch = []
                async with self.queue_cond:
                    while not (self.high_queue or self.medium_queue or self.low_queue):
                        await self.queue_cond.wait()

                    # Si un HAUTE est arrivé entre temps, il faut se re-suspendre.
                    if not self._lower_priorities_allowed.is_set():
                        continue

                    # Draine la queue en respectant les priorités
                    current_texts = 0
                    for q in [self.high_queue, self.medium_queue, self.low_queue]:
                        while q and current_texts < self.batch_size:
                            texts, future = q[0]
                            if (
                                current_texts > 0
                                and current_texts + len(texts) > self.batch_size
                            ):
                                break
                            texts, future = q.popleft()
                            batch.append((texts, future))
                            current_texts += len(texts)
                        if current_texts >= self.batch_size:
                            break

                if batch:
                    # Shared worker : limité par le semaphore Triton, utilise le pool par défaut
                    await self._process_batch(
                        batch,
                        executor=self._default_executor,
                        limiter=self._triton_limiter,
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le worker {worker_id}: {e}", exc_info=True
                )

    async def _medium_worker_loop(self, worker_id: str):
        while True:
            try:
                await self._lower_priorities_allowed.wait()

                batch = []
                async with self.queue_cond:
                    while not (self.medium_queue or self.low_queue):
                        await self.queue_cond.wait()

                    if not self._lower_priorities_allowed.is_set():
                        continue

                    current_texts = 0
                    for q in [self.medium_queue, self.low_queue]:
                        while q and current_texts < self.batch_size:
                            texts, future = q[0]
                            if (
                                current_texts > 0
                                and current_texts + len(texts) > self.batch_size
                            ):
                                break
                            texts, future = q.popleft()
                            batch.append((texts, future))
                            current_texts += len(texts)
                        if current_texts >= self.batch_size:
                            break

                if batch:
                    await self._process_batch(
                        batch,
                        executor=self._default_executor,
                        limiter=self._triton_limiter,
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le worker {worker_id}: {e}", exc_info=True
                )

    async def _low_worker_loop(self, worker_id: str):
        while True:
            try:
                await self._lower_priorities_allowed.wait()

                batch = []
                async with self.queue_cond:
                    while not self.low_queue:
                        await self.queue_cond.wait()

                    if not self._lower_priorities_allowed.is_set():
                        continue

                    current_texts = 0
                    while self.low_queue and current_texts < self.batch_size:
                        texts, future = self.low_queue[0]
                        if (
                            current_texts > 0
                            and current_texts + len(texts) > self.batch_size
                        ):
                            break
                        texts, future = self.low_queue.popleft()
                        batch.append((texts, future))
                        current_texts += len(texts)

                if batch:
                    await self._process_batch(
                        batch,
                        executor=self._default_executor,
                        limiter=self._triton_limiter,
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(
                    f"Erreur inattendue dans le worker {worker_id}: {e}", exc_info=True
                )

    def tokenize_texts(self, texts: List[str]) -> List[List[int]]:
        """
        Tokenize une liste de textes en utilisant le tokenizer du service.
        """
        if not texts:
            return []
        try:
            return self.tokenizer(texts, add_special_tokens=False).input_ids
        except Exception as e:
            logging.error(f"Erreur lors de la tokenization: {e}", exc_info=True)
            return [[] for _ in texts]

    def detokenize_texts(self, token_lists: List[List[int]]) -> List[str]:
        """
        Décode une liste de listes de tokens en chaînes de caractères.
        """
        if not token_lists:
            return []
        try:
            return self.tokenizer.batch_decode(token_lists, skip_special_tokens=True)
        except Exception as e:
            logging.error(f"Erreur lors de la détokenization: {e}", exc_info=True)
            return ["" for _ in token_lists]

    def mean_pooling(self, model_output, attention_mask):
        token_embeddings = torch.from_numpy(model_output)
        attention_mask = torch.from_numpy(attention_mask)
        input_mask_expanded = (
            attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        )
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        return (sum_embeddings / sum_mask).numpy()

    async def _process_embeddings(
        self, texts: List[str], executor=None, limiter=None
    ) -> List[List[float]]:
        """La vraie logique métier, exécutée de façon isolée par les workers."""
        all_embeddings = []

        # Fonction synchrone isolée pour libérer l'Event Loop
        def _sync_tokenize(batch):
            encoded = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                return_tensors="np",
                max_length=512,
            )
            return encoded["input_ids"].astype(np.int64), encoded[
                "attention_mask"
            ].astype(np.int64)

        try:
            for i in range(0, len(texts), self.batch_size):
                batch_texts = texts[i : i + self.batch_size]
                logging.info(
                    f"Traitement du batch d'embedding {i // self.batch_size + 1}/{(len(texts) + self.batch_size - 1) // self.batch_size} avec {len(batch_texts)} textes."
                )

                # Exécution CPU lourde dans le thread pool dédié !
                loop = asyncio.get_running_loop()
                callable_tokenize = functools.partial(_sync_tokenize, batch_texts)
                input_ids, attention_mask = await loop.run_in_executor(
                    executor, callable_tokenize
                )

                inputs = [
                    InferInput("input_ids", input_ids.shape, "INT64"),
                    InferInput("attention_mask", attention_mask.shape, "INT64"),
                ]
                inputs[0].set_data_from_numpy(input_ids)
                inputs[1].set_data_from_numpy(attention_mask)

                outputs = [InferRequestedOutput("last_hidden_state")]

                # GRPc vers Triton : on limite via le semaphore si fourni (sauf pour HAUTE)
                async def _call_triton():
                    return await self.triton_client.infer(
                        model_name=MODEL_NAME, inputs=inputs, outputs=outputs
                    )

                if limiter:
                    async with limiter:
                        response = await _call_triton()
                else:
                    response = await _call_triton()

                last_hidden_state = response.as_numpy("last_hidden_state")

                # Exécution CPU lourde dans le thread pool dédié !
                callable_pooling = functools.partial(
                    self.mean_pooling, last_hidden_state, attention_mask
                )
                sentence_embeddings = await loop.run_in_executor(
                    executor, callable_pooling
                )

                all_embeddings.extend(sentence_embeddings.tolist())

            logging.info(
                f"✅ [_process_embeddings] Génération terminée avec succès pour {len(texts)} textes."
            )

            return all_embeddings
        except Exception as e:
            logging.error(
                f"Erreur lors de l'appel à Triton pour l'embedding: {e}", exc_info=True
            )
            raise e

    @measure_processing_time(
        service_name="embedding-model-service", label_arg_name="source_service"
    )
    async def generate_embeddings(
        self, texts: List[str], source_service: str | None = None
    ) -> List[List[float]]:
        if not texts:
            return []

        is_high_priority = source_service in HIGH_PRIORITY_SERVICES
        is_medium_priority = source_service in MEDIUM_PRIORITY_SERVICES

        # 1 = Plus haute priorité pour asyncio.PriorityQueue
        if is_high_priority:
            priority = 1
            priority_label = "HAUTE"
        elif is_medium_priority:
            priority = 2
            priority_label = "MOYENNE"
        else:
            priority = 3
            priority_label = "BASSE"

        if self.max_concurrent_requests <= 0:
            logging.info(
                f"Requête d'embedding reçue de '{source_service or 'inconnu'}'. Priorité: {priority_label}."
            )
            return await self._process_embeddings(texts)

        # Création d'un futur pour attendre la fin du worker
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async with self.queue_cond:
            item = (
                texts,
                future,
            )  # Stocke uniquement les arguments pour le dynamic batching
            if priority == 1:
                # Dès qu'une HAUTE entre, on ferme physiquement la porte aux requêtes inférieures
                if self._lower_priorities_allowed.is_set():
                    logging.info(
                        "⏸️ Requête HAUTE reçue. Pause des requêtes MOYENNE/BASSE."
                    )
                    self._lower_priorities_allowed.clear()
                self.high_queue.append(item)
            elif priority == 2:
                self.medium_queue.append(item)
            else:
                self.low_queue.append(item)

            logging.info(
                f"Requête d'embedding reçue de '{source_service or 'inconnu'}'. Priorité: {priority_label}. [Queues -> H:{len(self.high_queue)}, M:{len(self.medium_queue)}, L:{len(self.low_queue)}]"
            )

            # Notify ciblé pour éviter le thundering herd :
            # - HAUTE: réveille les high workers + shared workers
            # - MOYENNE/BASSE: réveille 1 seul worker
            if priority == 1:
                self.queue_cond.notify(
                    self._high_workers_count + self._shared_workers_count
                )
            else:
                self.queue_cond.notify(1)

        try:
            return await future
        except asyncio.CancelledError:
            # Smart Cancellation : Le client a timeout, on annule la tâche.
            future.cancel()
            logging.warning(
                f"Requête d'embedding annulée par le client (timeout/disconnect). Priority: {priority_label}"
            )
            raise

    def chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """
        Découpe un texte en chunks en utilisant le tokenizer du modèle.
        C'est la logique de chunking centralisée.
        """
        if not text:
            return []

        # La fonction de longueur utilise le tokenizer interne au service.
        def hf_length_function(text_to_count: str) -> int:
            return len(
                self.tokenizer_pre.encode(text_to_count, add_special_tokens=False)
            )

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=hf_length_function,
        )
        return text_splitter.split_text(text)
