import logging
import numpy as np
import os
import collections
from typing import List
import asyncio
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

    async def _execute_task(self, func, args, kwargs, future):
        try:
            # Si le client a timeout pendant l'attente, on annule et on ignore cette requête (Smart Cancellation)
            if not future.cancelled():
                result = await func(*args, **kwargs)
                future.set_result(result)
            else:
                logging.info(
                    "Ignoré par le worker: Requête déjà annulée (Timeout/Disconnect)"
                )
        except Exception as e:
            if not future.cancelled():
                future.set_exception(e)

    async def _high_worker_loop(self, worker_id: str):
        """Voie rapide stricte (Fast Lane): Ne traite QUE la haute priorité, sans exception."""
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
                    f"Erreur inattendue dans le worker {worker_id}: {e}", exc_info=True
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
                    f"Erreur inattendue dans le worker {worker_id}: {e}", exc_info=True
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
                    f"Erreur inattendue dans le worker {worker_id}: {e}", exc_info=True
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

    async def _process_embeddings(self, texts: List[str]) -> List[List[float]]:
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

                # Exécution CPU lourde dans un thread séparé !
                input_ids, attention_mask = await asyncio.to_thread(
                    _sync_tokenize, batch_texts
                )

                inputs = [
                    InferInput("input_ids", input_ids.shape, "INT64"),
                    InferInput("attention_mask", attention_mask.shape, "INT64"),
                ]
                inputs[0].set_data_from_numpy(input_ids)
                inputs[1].set_data_from_numpy(attention_mask)

                outputs = [InferRequestedOutput("last_hidden_state")]

                # GRPc vers Triton
                response = await self.triton_client.infer(
                    model_name=MODEL_NAME, inputs=inputs, outputs=outputs
                )

                last_hidden_state = response.as_numpy("last_hidden_state")

                # Exécution CPU lourde dans un thread séparé !
                sentence_embeddings = await asyncio.to_thread(
                    self.mean_pooling, last_hidden_state, attention_mask
                )

                all_embeddings.extend(sentence_embeddings.tolist())

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
            item = (self._process_embeddings, (texts,), {}, future)
            if priority == 1:
                self.high_queue.append(item)
            elif priority == 2:
                self.medium_queue.append(item)
            else:
                self.low_queue.append(item)

            logging.info(
                f"Requête d'embedding reçue de '{source_service or 'inconnu'}'. Priorité: {priority_label}. [Queues -> H:{len(self.high_queue)}, M:{len(self.medium_queue)}, L:{len(self.low_queue)}]"
            )

            # Réveille tous les workers, les plus appropriés prendront la tâche
            self.queue_cond.notify_all()

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
